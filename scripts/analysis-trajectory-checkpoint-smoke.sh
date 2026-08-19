#!/usr/bin/env bash
# Opt-in TG05 checkpoint-only live smoke. This script is never called by the
# public Story Start path or the normal zero-token acceptance suite.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
checkpoint="$root/scripts/lib/analysis-trajectory-checkpoint.py"
response_schema="$root/contracts/analysis-trajectory/trajectory-checkpoint-response-v1.schema.json"
config="$root/tests/fixtures/analysis-trajectory-guard/tg05-checkpoint-governor-shadow-v1.json"

usage() {
  echo 'Usage: MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_LIVE=true MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_CREDENTIALS_READY=true MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_PROVIDER=<codex|claude|opencode> scripts/analysis-trajectory-checkpoint-smoke.sh <synthetic-request.json> <artifact-directory>' >&2
}

[ "$#" -eq 2 ] || { usage; exit 2; }
[ "${MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_LIVE:-false}" = true ] || {
  echo 'ERROR: live checkpoint smoke requires MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_LIVE=true' >&2
  exit 2
}
[ "${MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_CREDENTIALS_READY:-false}" = true ] || {
  echo 'ERROR: live checkpoint smoke requires preconfigured credentials and MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_CREDENTIALS_READY=true' >&2
  exit 2
}

request="$1"
artifact_dir="$2"
provider="${MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_PROVIDER:-}"
case "$provider" in codex|claude|opencode) ;; *) usage; exit 2 ;; esac
[ -f "$request" ] || { echo "ERROR: missing synthetic checkpoint request: $request" >&2; exit 2; }
[ ! -L "$artifact_dir" ] || { echo "ERROR: unsafe smoke artifact-directory symlink: $artifact_dir" >&2; exit 2; }
timeout="${MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_TIMEOUT_SECONDS:-120}"
if ! [[ "$timeout" =~ ^[1-9][0-9]*$ ]] || [ "$timeout" -gt 300 ]; then
  echo 'ERROR: checkpoint smoke timeout must be 1..300 seconds' >&2
  exit 2
fi

# A live smoke is intentionally restricted to the committed synthetic contract
# shape. It cannot be repurposed with a real story or proprietary input refs.
jq -e '
  .schemaVersion == "mana.analysis-trajectory.trajectory-checkpoint-request/v1" and
  .mode == "SHADOW" and .advisory == true and
  (.checkpointEnvelope.missionContract.storyRef | startswith("story-synthetic-")) and
  all(.checkpointEnvelope.missionContract.authoritativeInputRefs[]; startswith("fixture:"))
' "$request" >/dev/null || {
  echo 'ERROR: live checkpoint smoke accepts only a synthetic compact request' >&2
  exit 2
}

# shellcheck disable=SC1091
. "$root/scripts/lib/story-start-stage-routing.sh"
# shellcheck disable=SC1091
. "$root/scripts/lib/provider-dispatch.sh"
mana_story_start_stage_resolve "$provider" trajectory-checkpoint '' '' false false '' '' || {
  echo 'ERROR: TG01 trajectory-checkpoint route could not be resolved' >&2
  exit 2
}
model="$MANA_STORY_START_ROUTE_MODEL"
effort="$MANA_STORY_START_ROUTE_EFFORT"
echo "Trajectory checkpoint live smoke: provider=$provider model=$model effort=$effort max_calls=2 mode=SHADOW"

mkdir -p "$artifact_dir"
for output in request.json route.json primary-validation.json repair-validation.json accepted-response.json run.json; do
  [ ! -L "$artifact_dir/$output" ] || { echo "ERROR: unsafe smoke artifact symlink: $artifact_dir/$output" >&2; exit 2; }
done
cp "$request" "$artifact_dir/request.json"
jq -n --arg provider "$provider" --arg model "$model" --arg effort "$effort" '{provider:$provider,model:$model,effort:$effort,stage:"trajectory-checkpoint",mode:"SHADOW",maxCalls:2}' >"$artifact_dir/route.json"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-tg05-live-smoke.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/empty"
python3 "$checkpoint" render-prompt "$request" "$scratch/primary-prompt.txt"

invoke_provider() {
  local prompt_file="$1" candidate="$2" status_file="$3" code timed_out descendants
  MANA_PROVIDER_PROGRAM="$provider"
  mana_provider_synthesis_args "$provider" "$scratch/empty" "$model" host-disposable-non-git "$response_schema" "$effort" || return 1
  local program="${MANA_PROVIDER_PROGRAM:-$provider}"
  command -v "$program" >/dev/null 2>&1 || return 1
  perl "$root/scripts/lib/verification-exec.pl" --timeout "$timeout" --output-cap 131072 --stderr-cap 4096 --stdout "$candidate" --stderr "$scratch/provider.stderr" --status "$status_file" -- "$program" "${MANA_PROVIDER_ARGS[@]}" "$(<"$prompt_file")" || true
  [ -f "$status_file" ] || return 1
  IFS=$'\t' read -r code _ timed_out descendants _ <"$status_file" || return 1
  [ "$code" -eq 0 ] && [ "$timed_out" = 0 ] && [ "$descendants" = 0 ]
}

primary_candidate="$scratch/primary-candidate.json"
primary_validation="$artifact_dir/primary-validation.json"
repair_validation="-"
accepted_response="-"
if invoke_provider "$scratch/primary-prompt.txt" "$primary_candidate" "$scratch/primary-status.tsv"; then
  set +e
  python3 "$checkpoint" assess-response "$request" "$primary_candidate" "$primary_validation" --calls-used 1
  primary_assessment=$?
  set -e
else
  python3 "$checkpoint" provider-failed "$request" "$primary_validation"
  primary_assessment=5
fi

if [ "$primary_assessment" -eq 0 ]; then
  cp "$primary_candidate" "$artifact_dir/accepted-response.json"
  accepted_response="$artifact_dir/accepted-response.json"
elif [ "$primary_assessment" -eq 3 ] && jq -e '.repairPermitted == true' "$primary_validation" >/dev/null; then
  python3 "$checkpoint" render-repair-prompt "$request" "$primary_validation" "$scratch/repair-prompt.txt"
  repair_candidate="$scratch/repair-candidate.json"
  repair_validation="$artifact_dir/repair-validation.json"
  if invoke_provider "$scratch/repair-prompt.txt" "$repair_candidate" "$scratch/repair-status.tsv"; then
    set +e
    python3 "$checkpoint" assess-response "$request" "$repair_candidate" "$repair_validation" --calls-used 2
    repair_assessment=$?
    set -e
    if [ "$repair_assessment" -eq 0 ]; then
      cp "$repair_candidate" "$artifact_dir/accepted-response.json"
      accepted_response="$artifact_dir/accepted-response.json"
    fi
  else
    python3 "$checkpoint" provider-failed "$request" "$repair_validation"
  fi
fi

python3 "$checkpoint" record-run "$config" "$request" "$provider" "$model" "$effort" "$primary_validation" "$repair_validation" "$accepted_response" "$artifact_dir/run.json"
jq -r --arg artifacts "$artifact_dir" '"Trajectory checkpoint result: status=\(.status) outcome=\(.outcome // "none") calls=\(.callCounts.total) usage=unavailable artifacts=\($artifacts)"' "$artifact_dir/run.json"
[ "$(jq -r '.status' "$artifact_dir/run.json")" = ACCEPTED ]
