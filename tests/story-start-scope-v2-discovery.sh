#!/usr/bin/env bash
# SS02 zero-token acceptance for the internal, schema-bound discovery phase.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
raw="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json"
package="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
schema="$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json"
normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-discovery-v2.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-scope-v2.sh"

"$root/scripts/validate-story-start-scope-v2-contract.sh"
mana_story_start_scope_v2_validate_discovery "$raw"

# Focused prompt assertions prevent discovery from becoming implicit planning.
prompt="$(mana_story_start_scope_v2_discovery_prompt "$package")"
for boundary in \
  'Do not decide implementation scope.' \
  'Do not produce implementation tasks.' \
  'Do not estimate remediation work.' \
  'Do not choose between unresolved architectures.' \
  'Do not assume a discovered defect belongs to' \
  'Do not turn missing evidence into a fabricated requirement.'; do
  grep -Fq "$boundary" <<<"$prompt" || fail "missing Discovery v2 prompt boundary: $boundary"
done
grep -Fq 'This is discovery, not planning.' "$root/skills/story-start-discovery-v2/SKILL.md" || fail 'skill does not state its role boundary'
grep -Fq 'Do not produce implementation tasks.' "$root/skills/story-start-discovery-v2/SKILL.md" || fail 'skill allows tasks'

# 1-8. The captured inventory is neutral evidence, never an implementation plan.
jq -e '
  any(.evidence[]; .kind == "configuration" and .capabilityState == "already_exists") and
  any(.findings[]; .findingKind == "existing_configuration" and (.summary | contains("does not request adding configuration"))) and
  any(.findings[]; .findingKind == "readiness" and (.summary | contains("Branch alignment"))) and
  any(.findings[]; .findingKind == "defect" and .storyCausality == "pre_existing_independent" and (.acceptanceCriterionRefs | length) == 0) and
  any(.findings[]; .findingKind == "ambiguity" and (.acceptanceCriterionRefs | length) > 0 and (.summary | contains("Direct/SSO"))) and
  any(.decisions[]; (.question | contains("federated")) and .status == "open" and .selectedOptionId == null) and
  any(.decisions[]; .status == "open" and .selectedOptionId == null and (.options | map(.label) | sort) == ["Best effort", "Durable recovery"]) and
  any(.findings[]; .findingKind == "readiness" and .suggestedOwner == "Product Owner" and (.summary | contains("not developer effort"))) and
  any(.findings[]; .findingKind == "ambiguity" and (.summary | contains("Null-semantics"))) and
  any(.decisions[]; (.question | contains("missing synthetic legacy enabled flag")) and .selectedOptionId == null) and
  ([.. | objects | keys[]] | index("tasks") | not) and
  ([.. | objects | keys[]] | index("effort") | not) and
  ([.. | objects | keys[]] | index("estimate") | not)
' "$raw" >/dev/null || fail 'captured discovery lost a required neutral regression condition'

# 9. Equivalent entity order generates byte-identical canonical output and IDs.
python3 "$normalizer" normalize-discovery "$schema" "$raw" "$tmp/normalized-a.json"
jq '
  .acceptanceCriteria |= reverse | .mandatoryConstraints |= reverse |
  .evidence |= reverse | .findings |= reverse | .decisions |= reverse |
  .openQuestions |= reverse | .provenance |= reverse |
  .decisions[].options |= reverse
' "$raw" > "$tmp/reordered.json"
python3 "$normalizer" normalize-discovery "$schema" "$tmp/reordered.json" "$tmp/normalized-b.json"
cmp -s "$tmp/normalized-a.json" "$tmp/normalized-b.json" || fail 'normalization changes for equivalent input ordering'
mana_story_start_scope_v2_validate_discovery "$tmp/normalized-a.json"
jq -e '
  (.artifactId | test("^discovery_[0-9a-f]{64}$")) and
  ([.evidence[].id] == ([.evidence[].id] | sort)) and
  ([.findings[].id] == ([.findings[].id] | sort))
' "$tmp/normalized-a.json" >/dev/null || fail 'normalization did not derive deterministic IDs and ordering'

# Provider dispatch stays isolated and uses the host-owned schema path.
stub="$tmp/discovery-provider-stub"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$*" > "$DISCOVERY_STUB_ARGS"' 'cat "$DISCOVERY_STUB_OUTPUT"' > "$stub"
chmod +x "$stub"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
DISCOVERY_STUB_OUTPUT="$raw" \
DISCOVERY_STUB_ARGS="$tmp/provider-args" \
mana_story_start_scope_v2_discover stub deterministic "$package" "$tmp/discovered.json"
cmp -s "$tmp/normalized-a.json" "$tmp/discovered.json" || fail 'internal phase did not publish normalized discovery output'
grep -Fq 'COMPACT_DISCOVERY_PACKAGE' "$tmp/provider-args" || fail 'Discovery v2 did not supply its compact package to the provider'
mana_provider_synthesis_args codex "$tmp" deterministic host-disposable-non-git "$schema"
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/codex-args"
grep -Fq -- '--output-schema' "$tmp/codex-args" || fail 'Discovery v2 cannot use provider schema dispatch'
grep -Fq -- "$schema" "$tmp/codex-args" || fail 'Discovery v2 did not bind the host-owned schema'
grep -Fq -- '--skip-git-repo-check' "$tmp/codex-args" || fail 'Discovery v2 did not use its isolated workspace contract'

# Normalization keeps provenance bounded and cannot publish an absolute host path.
jq '.provenance[0].sourceRef = "/private/synthetic/forbidden"' "$raw" > "$tmp/unsafe-provenance.json"
python3 "$normalizer" normalize-discovery "$schema" "$tmp/unsafe-provenance.json" "$tmp/unsafe.json" >/dev/null 2>&1 && fail 'unsafe provenance was normalized'

# 10. Malformed provider data is rejected before publication through the schema path.
jq '.artifactVersion = 3' "$raw" > "$tmp/malformed.json"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
DISCOVERY_STUB_OUTPUT="$tmp/malformed.json" \
DISCOVERY_STUB_ARGS="$tmp/malformed-args" \
mana_story_start_scope_v2_discover stub deterministic "$package" "$tmp/malformed-published.json" >/dev/null 2>&1 && fail 'malformed provider output was accepted'
[ ! -e "$tmp/malformed-published.json" ] || fail 'malformed provider output was published'

# SS06 may call this phase publicly, but its original isolated compact-package
# boundary and zero-task semantics above remain unchanged.

echo 'Story Start Scope v2 Discovery tests passed (zero provider/network calls)'
