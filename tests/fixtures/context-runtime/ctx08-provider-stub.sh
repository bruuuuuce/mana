#!/usr/bin/env bash
# Local-only CTX-08 regression provider, with exact argv/prompt capture.
set -euo pipefail
fixture_root="${CTX08_FIXTURE_ROOT:?}"
provider="$(basename "$0")"
capability_set="$provider-supported"
case "${1:-}" in
  --version) cat "$fixture_root/provider-capabilities/$capability_set/version.txt"; exit 0 ;;
  --help)
    if [ "$provider" = claude ] && [ "${CTX08_COMPACTION_STATUS:-supported}" = unknown ]; then
      sed '/--autocompact/d' "$fixture_root/provider-capabilities/$capability_set/root-help.txt"
    elif [ "$provider" = claude ] && [ "${CTX08_COMPACTION_STATUS:-supported}" = unsupported ]; then
      sed 's/Auto-compact window size.*/Unsupported; ignored at runtime/' "$fixture_root/provider-capabilities/$capability_set/root-help.txt"
    else
      cat "$fixture_root/provider-capabilities/$capability_set/root-help.txt"
    fi
    exit 0 ;;
  exec) if [ "${2:-}" = --help ]; then cat "$fixture_root/provider-capabilities/$capability_set/run-help.txt"; exit 0; fi ;;
  features) cat "$fixture_root/provider-capabilities/$capability_set/features.txt"; exit 0 ;;
esac
state="${CTX08_STATE_DIR:?}"
mkdir -p "$state"
count=1
[ ! -f "$state/count" ] || count=$(( $(<"$state/count") + 1 ))
printf '%s\n' "$count" > "$state/count"
printf '%s\n' "$@" > "$state/argv.$count"
prompt="${!#}"
printf '%s\n' "$prompt" > "$state/prompt.$count"
phase_input="$(sed -n 's/^phaseInput=//p' <<<"$prompt")"
context_manifest="$(sed -n 's/^contextManifest=//p' <<<"$prompt")"
phase="$(jq -r .phaseId <<<"$phase_input")"
kind=stop
target=null
if [ "$phase" = classify ]; then kind=next-declared-phase; target=synthesize; fi
checkpoint="$(jq -cn --arg execution "$(jq -r .executionId <<<"$phase_input")" --arg profile "$(jq -r .profileId <<<"$context_manifest")" --arg phase "$phase" --arg count "$count" --arg kind "$kind" --arg target "$target" '{schemaVersion:"mana.context-runtime.phase-checkpoint/v1",checkpointId:("C-budget-"+$count),executionId:$execution,executionVersion:1,profileId:$profile,phaseId:$phase,status:"complete",verifiedFacts:[],assumptions:[],inferences:[],openQuestions:[],closedHypotheses:[],candidateFindings:[],approvalRequests:[],activatedSkills:[],evidenceRefs:[],nextActionRequest:{kind:$kind,targetId:(if $target=="null" then null else $target end),reason:"local budget fixture"}}')"
if [ "$provider" = claude ]; then
  jq -cn --argjson checkpoint "$checkpoint" '{structured_output:$checkpoint}'
else
  final=""
  previous=""
  for argument in "$@"; do
    [ "$previous" != --output-last-message ] || final="$argument"
    previous="$argument"
  done
  [ -n "$final" ] || exit 9
  printf '%s\n' "$checkpoint" > "$final"
  printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":2,"uncached_input_tokens":8,"output_tokens":3,"reasoning_tokens":1}}'
fi
