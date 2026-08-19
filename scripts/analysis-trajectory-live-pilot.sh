#!/usr/bin/env bash
# Explicit, bounded TG07 live A/B/C harness. Never called by normal CI.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat >&2 <<'USAGE'
Usage:
  MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT=true \
  MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT_CREDENTIALS_READY=true \
  scripts/analysis-trajectory-live-pilot.sh \
    --project-root <repo> --context <project-relative-json> \
    --provider <codex|claude|opencode> --output-dir <project-relative-new-dir>

Checkpoint-only first step:
  ... scripts/analysis-trajectory-live-pilot.sh \
    --project-root <repo> --provider <codex|claude|opencode> \
    --output-dir <project-relative-new-dir> --checkpoint-only <synthetic-request.json>
USAGE
}

project_root=""
context=""
provider=""
output_dir=""
checkpoint_only=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) [ "$#" -ge 2 ] || { usage; exit 2; }; project_root="$2"; shift 2 ;;
    --context) [ "$#" -ge 2 ] || { usage; exit 2; }; context="$2"; shift 2 ;;
    --provider) [ "$#" -ge 2 ] || { usage; exit 2; }; provider="$2"; shift 2 ;;
    --output-dir) [ "$#" -ge 2 ] || { usage; exit 2; }; output_dir="$2"; shift 2 ;;
    --checkpoint-only) [ "$#" -ge 2 ] || { usage; exit 2; }; checkpoint_only="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown TG07 live-pilot option: $1" >&2; usage; exit 2 ;;
  esac
done

[ "${MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT:-false}" = true ] || {
  echo 'ERROR: live pilot requires MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT=true' >&2
  exit 2
}
[ "${MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT_CREDENTIALS_READY:-false}" = true ] || {
  echo 'ERROR: live pilot requires existing credentials and MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT_CREDENTIALS_READY=true' >&2
  exit 2
}
case "${CI:-false}" in false|FALSE|0|'') ;; *) echo 'ERROR: TG07 live pilot must never run in CI' >&2; exit 2 ;; esac
if [ -z "$project_root" ] || [ -z "$provider" ] || [ -z "$output_dir" ]; then usage; exit 2; fi
case "$provider" in codex|claude|opencode) ;; *) usage; exit 2 ;; esac
if [ ! -d "$project_root" ] || [ -L "$project_root" ]; then echo 'ERROR: unsafe or missing project root' >&2; exit 2; fi
project_root="$(cd "$project_root" && pwd -P)"
git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo 'ERROR: live pilot project root must be a Git worktree' >&2
  exit 2
}
case "$output_dir" in /*|../*|*/../*|*/..|..|'') echo 'ERROR: output directory must be a contained project-relative path' >&2; exit 2 ;; esac
pilot_dir="$project_root/$output_dir"
if [ -e "$pilot_dir" ] || [ -L "$pilot_dir" ]; then echo 'ERROR: live-pilot output directory must not already exist' >&2; exit 2; fi
mkdir -p "$pilot_dir"

revision="$(git -C "$project_root" rev-parse HEAD)"

if [ -n "$checkpoint_only" ]; then
  if [ ! -f "$checkpoint_only" ] || [ -L "$checkpoint_only" ]; then echo 'ERROR: unsafe or missing checkpoint-only request' >&2; exit 2; fi
  echo "TG07 checkpoint-only pilot: provider=$provider repository_revision=$revision max_calls=2"
  MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_LIVE=true \
  MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_CREDENTIALS_READY=true \
  MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_PROVIDER="$provider" \
    "$root/scripts/analysis-trajectory-checkpoint-smoke.sh" "$checkpoint_only" "$pilot_dir/checkpoint-only"
  exit 0
fi

[ -n "$context" ] || { usage; exit 2; }
case "$context" in /*|../*|*/../*|*/..|..|'') echo 'ERROR: context must be a contained project-relative path' >&2; exit 2 ;; esac
context_path="$project_root/$context"
if [ ! -f "$context_path" ] || [ -L "$context_path" ]; then echo 'ERROR: unsafe or missing live-pilot context' >&2; exit 2; fi
context_parent="$(cd "$(dirname "$context_path")" && pwd -P)"
case "$context_parent/$(basename "$context_path")" in "$project_root"/*) ;; *) echo 'ERROR: context resolves outside the project' >&2; exit 2 ;; esac
context_hash="sha256:$(shasum -a 256 "$context_path" | awk '{print $1}')"

# The route helper prints the same effective stage selections before any call.
# shellcheck disable=SC1091
. "$root/scripts/lib/story-start-stage-routing.sh"
route_file="$pilot_dir/routes.json"
printf '%s\n' '[]' > "$route_file"
for stage in discovery triage planner correction trajectory-checkpoint; do
  mana_story_start_stage_resolve "$provider" "$stage" '' '' false false '' ''
  echo "TG07 live route: stage=$stage provider=$provider model=$MANA_STORY_START_ROUTE_MODEL effort=$MANA_STORY_START_ROUTE_EFFORT effort_dispatch=$MANA_STORY_START_ROUTE_EFFORT_DISPATCH"
  jq --arg stage "$stage" --arg provider "$provider" \
    --arg model "$MANA_STORY_START_ROUTE_MODEL" --arg effort "$MANA_STORY_START_ROUTE_EFFORT" \
    --arg dispatch "$MANA_STORY_START_ROUTE_EFFORT_DISPATCH" \
    '. + [{stage:$stage,provider:$provider,model:$model,effort:$effort,effortDispatch:$dispatch}]' \
    "$route_file" > "$route_file.next"
  mv "$route_file.next" "$route_file"
done

case "$provider" in
  codex) provider_flag=--codex ;;
  claude) provider_flag=--claude ;;
  opencode) provider_flag=--opencode ;;
esac

total_calls=0
total_checkpoints=0
for mode in off shadow enforce; do
  current_revision="$(git -C "$project_root" rev-parse HEAD)"
  [ "$current_revision" = "$revision" ] || { echo 'ERROR: repository revision changed during comparable pilot' >&2; exit 1; }
  current_hash="sha256:$(shasum -a 256 "$context_path" | awk '{print $1}')"
  [ "$current_hash" = "$context_hash" ] || { echo 'ERROR: story context changed during comparable pilot' >&2; exit 1; }
  echo "TG07 live pilot start: mode=$mode provider=$provider repository_revision=$revision context_hash=$context_hash max_story_calls=4 max_checkpoint_calls=$([ "$mode" = enforce ] && echo 2 || echo 0)"
  MANA_UPDATE_CHECK=off \
  MANA_STORY_START_SCOPE_VERSION=v2 \
  MANA_STORY_START_CONTEXT="$context" \
  MANA_ANALYSIS_TRAJECTORY_MODE="$mode" \
  MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true \
    "$root/scripts/run-profile.sh" story-start --project-root "$project_root" "$provider_flag"
  active_rel="$(sed -n '1p' "$project_root/.mana/active-workspace")"
  active="$project_root/$active_rel"
  if [ ! -d "$active" ] || [ -L "$active" ]; then echo 'ERROR: live pilot did not publish a safe active workspace' >&2; exit 1; fi
  summary="$active/validation/analysis-trajectory-summary-v1.json"
  events="$active/evidence/analysis-trajectory-events-v1.jsonl"
  if [ ! -f "$summary" ] || [ ! -f "$events" ]; then echo 'ERROR: live pilot lacks sanitized trajectory telemetry' >&2; exit 1; fi
  mode_dir="$pilot_dir/$mode"
  mkdir -p "$mode_dir"
  cp "$summary" "$mode_dir/analysis-trajectory-summary-v1.json"
  cp "$events" "$mode_dir/analysis-trajectory-events-v1.jsonl"
  if [ -f "$active/validation/analysis-trajectory-integration-run-v1.json" ]; then
    cp "$active/validation/analysis-trajectory-integration-run-v1.json" "$mode_dir/analysis-trajectory-integration-run-v1.json"
  fi
  if [ -f "$active/evidence/analysis-trajectory-evidence-package-v1.json" ]; then
    cp "$active/evidence/analysis-trajectory-evidence-package-v1.json" "$mode_dir/analysis-trajectory-evidence-package-v1.json"
  fi
  calls="$(jq -r '.providerIterationCount' "$summary")"
  checkpoints="$(jq -r '.totalCheckpoints' "$summary")"
  if [ "$calls" -gt 6 ] || [ "$checkpoints" -gt 2 ]; then echo 'ERROR: live pilot exceeded per-run call bounds' >&2; exit 1; fi
  total_calls=$((total_calls + calls))
  total_checkpoints=$((total_checkpoints + checkpoints))
  jq -n --arg mode "$mode" --arg provider "$provider" --arg revision "$revision" \
    --arg contextRef "$context" --arg contextHash "$context_hash" --arg workspaceRef "$active_rel" \
    --argjson calls "$calls" --argjson checkpoints "$checkpoints" \
    '{mode:$mode,provider:$provider,repositoryRevision:$revision,storyContextRef:$contextRef,storyContextHash:$contextHash,workspaceRef:$workspaceRef,providerCalls:$calls,checkpointCalls:$checkpoints,tokenUsage:{availability:"UNAVAILABLE",value:null},nonDeterminismLimitations:["Provider sampling and remote service state may vary even with identical routing and input.","Provider-neutral transport may not expose exact token usage."]}' \
    > "$mode_dir/manifest.json"
done

if [ "$total_calls" -gt 14 ] || [ "$total_checkpoints" -gt 2 ]; then
  echo 'ERROR: live A/B/C pilot exceeded total bounded-call policy' >&2
  exit 1
fi
jq -n --arg provider "$provider" --arg revision "$revision" --arg contextHash "$context_hash" \
  --argjson totalCalls "$total_calls" --argjson totalCheckpoints "$total_checkpoints" \
  '{schemaVersion:"mana.analysis-trajectory.live-pilot-summary/v1",provider:$provider,repositoryRevision:$revision,storyContextHash:$contextHash,modes:["off","shadow","enforce"],totalProviderCalls:$totalCalls,totalCheckpointCalls:$totalCheckpoints,maximumProviderCalls:14,maximumCheckpointCalls:2,tokenUsage:{availability:"UNAVAILABLE",value:null},humanReviewRequired:true}' \
  > "$pilot_dir/summary.json"
echo "TG07 live pilot complete: provider=$provider calls=$total_calls checkpoints=$total_checkpoints artifacts=$pilot_dir"
