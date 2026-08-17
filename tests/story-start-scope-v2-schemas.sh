#!/usr/bin/env bash
# SS01 zero-token acceptance: strict v2 schemas, examples, and v1 isolation.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

"$root/scripts/validate-story-start-scope-v2-contract.sh"

copy="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-scope-v2.XXXXXX")"
trap 'rm -rf "$copy"' EXIT
cp -R "$root/contracts/story-start/scope-v2/." "$copy/"
"$root/scripts/validate-story-start-scope-v2-contract.sh" --bundle "$copy"

# The pre-v2 agent schemas remain the permissive Markdown metadata contracts.
jq -e '
  .title == "story-implementation-planner-agent inputs" and
  .additionalProperties == true and
  (.properties.schemaVersion == null)
' "$root/agents/story-implementation-planner/inputs.schema.json" >/dev/null
jq -e '
  .title == "story-implementation-planner-agent outputs" and
  .additionalProperties == true and
  (.properties."02_implementation_plan".type == "string") and
  (.properties.schemaVersion == null)
' "$root/agents/story-implementation-planner/outputs.schema.json" >/dev/null

# SS01 is contract-only: neither public path nor the current profile/agent opts in.
if rg -q \
  'contracts/story-start/scope-v2|mana\.story-start\.[^[:space:]]*/v2' \
  "$root/scripts/run-profile.sh" \
  "$root/scripts/cast.sh" \
  "$root/profiles/story-start.yaml" \
  "$root/agents/story-implementation-planner"; then
  echo 'ERROR: Story Start Scope v2 was wired into current public runtime behavior' >&2
  exit 1
fi

grep -Fq 'During SS01-SS05' "$root/contracts/story-start/scope-v2/COMPATIBILITY.md"
grep -Fq 'SS05' "$root/contracts/story-start/scope-v2/SEMANTIC-CONTRACT.md"

echo 'Story Start Scope v2 schema clean-room tests passed (zero model/provider calls)'
