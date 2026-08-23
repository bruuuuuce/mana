#!/usr/bin/env bash
# CTX-02-R3 deterministic provider capability and hard-isolation coverage.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cli="$root/scripts/mana-provider-capabilities.sh"
schema="$root/contracts/context-runtime/provider-capabilities-v1.schema.json"
fixtures="$root/tests/fixtures/context-runtime/provider-capabilities"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-provider-capabilities-test.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# Exercise the one authoritative resolver directly before any adapter. This is
# the contract every provider evidence map must pass through.
# shellcheck disable=SC1091
. "$root/scripts/lib/provider-capabilities.sh"

assert_resolver_state() {
  local positive="$1" negative="$2" expected="$3" actual
  actual="$(jq -nc --argjson positive "$positive" --argjson negative "$negative" '
    {
      capability: {
        positiveEvidence:(if $positive then ["help:positive"] else [] end),
        negativeEvidence:(if $negative then ["help:negative"] else [] end),
        unknownEvidence:["probe:unknown"]
      }
    }
  ' | mana_provider_capabilities_resolve_evidence_map | jq -r '.capability.status')"
  [ "$actual" = "$expected" ] || fail "resolver truth table $positive/$negative returned $actual"
}

assert_resolver_state false false unknown
assert_resolver_state true false supported
assert_resolver_state false true unsupported
assert_resolver_state true true unknown

assert_ambiguous_resolver_state() {
  local positive="$1" negative="$2" actual
  actual="$(jq -nc --argjson positive "$positive" --argjson negative "$negative" '
    {
      capability: {
        positiveEvidence:(if $positive then ["help:positive"] else [] end),
        negativeEvidence:(if $negative then ["help:negative"] else [] end),
        ambiguousEvidence:["help:ambiguous"],
        unknownEvidence:["probe:unknown"]
      }
    }
  ' | mana_provider_capabilities_resolve_evidence_map | jq -r '.capability.status')"
  [ "$actual" = unknown ] || fail "ambiguous resolver $positive/$negative returned $actual"
}

# Ambiguous evidence is authoritative uncertainty: it forces unknown before
# positive/negative evidence is interpreted, for every polarity combination.
assert_ambiguous_resolver_state false false
assert_ambiguous_resolver_state true false
assert_ambiguous_resolver_state false true
assert_ambiguous_resolver_state true true

assert_composite_state() {
  local expected="$1" actual
  shift
  actual="$(mana_provider_capabilities_resolve_required_states "$@")" ||
    fail "composite resolver rejected valid states: $*"
  [ "$actual" = "$expected" ] || fail "composite resolver returned $actual for [$*], expected $expected"
}

# Required-prerequisite composition consumes resolved states only.
assert_composite_state supported supported
assert_composite_state unknown unknown
assert_composite_state unsupported unsupported
assert_composite_state supported supported supported
assert_composite_state unknown supported unknown
assert_composite_state unknown unknown supported
assert_composite_state unknown unknown unknown
assert_composite_state unsupported supported unsupported
assert_composite_state unsupported unsupported unknown
assert_composite_state unsupported unsupported supported

# An atomic conflict is resolved before composition. The composite API cannot
# accept the original evidence booleans or evidence-map records.
conflicted_atomic_state="$(jq -nc '{prerequisite:{positiveEvidence:["help:positive"],negativeEvidence:["help:negative"]}}' |
  mana_provider_capabilities_resolve_evidence_map | jq -r '.prerequisite.status')"
[ "$conflicted_atomic_state" = unknown ] || fail 'atomic conflict did not resolve before composition'
assert_composite_state unknown supported "$conflicted_atomic_state"
if mana_provider_capabilities_resolve_required_states supported true >/dev/null 2>&1; then
  fail 'composite resolver accepted a raw positive-evidence boolean'
fi
if mana_provider_capabilities_resolve_required_states supported '{"negativeEvidence":["help:negative"]}' >/dev/null 2>&1; then
  fail 'composite resolver accepted a raw evidence map'
fi

# Optional direct composite evidence is separately resolved. It cannot override
# derived support with an authoritative negative, while a direct authoritative
# negative can prove an otherwise unknown composite unsupported.
[ "$(mana_provider_capabilities_combine_composite_states supported unsupported)" = unknown ] ||
  fail 'direct negative evidence overrode derived composite support'
[ "$(mana_provider_capabilities_combine_composite_states unknown unsupported)" = unsupported ] ||
  fail 'direct authoritative negative did not remain distinguishable from uncertainty'

# The acceptance test must not inherit optional local Jira integration. This
# keeps the actual provider argc deterministic without weakening production
# discovery behavior.
unset MANA_JIRA_MCP_ENV JIRA_URL JIRA_PERSONAL_TOKEN JIRA_USERNAME JIRA_API_TOKEN

assert_element() {
  local file="$1" expected="$2"
  grep -Fxq -- "$expected" "$file" || fail "missing exact argv element: $expected"
}

assert_no_element() {
  local file="$1" unexpected="$2"
  ! grep -Fxq -- "$unexpected" "$file" || fail "unexpected exact argv element: $unexpected"
}

assert_adjacent_pair() {
  local file="$1" first="$2" second="$3"
  awk -v first="$first" -v second="$second" 'previous == first && $0 == second { found=1 } { previous=$0 } END { exit(found ? 0 : 1) }' "$file" ||
    fail "missing adjacent argv pair: $first / $second"
}

assert_argv_exact() {
  local file="$1" index=1 actual expected_count
  shift
  expected_count="$#"
  for expected in "$@"; do
    actual="$(sed -n "${index}p" "$file")"
    [ "$actual" = "$expected" ] || fail "argv element $index changed: expected '$expected', got '$actual'"
    index=$((index + 1))
  done
  [ "$(wc -l < "$file" | tr -d ' ')" = "$expected_count" ] || fail "argv count changed for $file"
}

materialize_adversarial_fixture() {
  local provider="$1" case_name="$2" destination="$3" corpus
  corpus="$fixtures/$provider-adversarial-cases.json"
  mkdir -p "$destination"
  jq -jr --arg caseName "$case_name" '.[$caseName].version' "$corpus" > "$destination/version.txt"
  jq -jr --arg caseName "$case_name" '.[$caseName].rootHelp' "$corpus" > "$destination/root-help.txt"
  case "$provider" in
    codex)
      jq -jr --arg caseName "$case_name" '.[$caseName].runHelp' "$corpus" > "$destination/run-help.txt"
      jq -jr --arg caseName "$case_name" '.[$caseName].features' "$corpus" > "$destination/features.txt"
      ;;
    claude) ;;
    opencode)
      jq -jr --arg caseName "$case_name" '.[$caseName].runHelp' "$corpus" > "$destination/run-help.txt"
      jq -c --arg caseName "$case_name" '.[$caseName].configProbe' "$corpus" > "$destination/config-probe.json"
      ;;
  esac
}

before="$(git -C "$root" status --porcelain=v1)"
for provider in codex claude opencode; do
  "$cli" "$provider" --fixture "$fixtures/$provider-supported" > "$tmp/$provider-one.json"
  "$cli" "$provider" --fixture "$fixtures/$provider-supported" > "$tmp/$provider-two.json"
  cmp -s "$tmp/$provider-one.json" "$tmp/$provider-two.json" || fail "$provider fixture output is not deterministic"
  python3 "$root/tests/lib/json_schema_subset.py" "$schema" "$tmp/$provider-one.json" || fail "$provider report violates schema"
  jq -e --arg provider "$provider" '
    .schemaVersion == "mana.context-runtime.provider-capabilities/v1" and
    .provider == $provider and (.providerVersion | length > 0) and
    ([.capabilities[].status] | all(. == "supported" or . == "unsupported" or . == "unknown"))
  ' "$tmp/$provider-one.json" >/dev/null || fail "$provider report metadata/status contract failed"
done

jq -e '
  .capabilities.structuredEventStream.status == "supported" and
  .capabilities.hardSubagentDisable.status == "supported" and
  .capabilities.childContextInheritanceControl.status == "unknown" and
  .capabilities.childContextInheritanceControl.status != "unsupported"
' "$tmp/codex-one.json" >/dev/null || fail 'Codex supported/unknown distinction failed'
jq -e '
  .capabilities.structuredOutputSchema.status == "supported" and
  .capabilities.separateFinalOutputFile.status == "unknown" and
  .capabilities.automaticCompactionThreshold.status == "supported" and
  .capabilities.userConfigurationIsolation.status == "unknown"
' "$tmp/claude-one.json" >/dev/null || fail 'Claude capability matrix failed'
jq -e '
  .capabilities.structuredOutputSchema.status == "unknown" and
  .capabilities.hardSubagentDisable.status == "unknown" and
  .capabilities.userConfigurationIsolation.status == "unknown" and
  .capabilities.recursiveDelegationPrevention.status == "unknown" and
  .capabilities.childModelRouting.status == "unknown"
' "$tmp/opencode-one.json" >/dev/null || fail 'OpenCode capability matrix failed'

"$cli" claude --fixture "$fixtures/claude-limited" > "$tmp/claude-limited.json"
jq -e '
  .capabilities.structuredOutputSchema.status == "unsupported" and
  .capabilities.automaticCompactionThreshold.status == "unsupported" and
  .capabilities.childContextInheritanceControl.status == "unknown"
' "$tmp/claude-limited.json" >/dev/null || fail 'unsupported structured output/compaction fixture failed'
"$cli" opencode --fixture "$fixtures/opencode-limited" > "$tmp/opencode-limited.json"
jq -e '
  .capabilities.hardSubagentDisable.status == "unknown" and
  .capabilities.userConfigurationIsolation.status == "unknown" and
  .capabilities.structuredEventStream.status == "unknown" and
  .capabilities.separateFinalOutputFile.status == "unsupported"
' "$tmp/opencode-limited.json" >/dev/null || fail 'failed OpenCode config probe was not conservative'

# Provider-specific adversarial help fixtures. Flag names in negative prose do
# not prove support; partial/unexpected surfaces preserve unknown; only explicit
# authoritative negatives produce unsupported.
for provider in codex claude opencode; do
  for case_name in negativeTokens partial unexpected explicitNegative positiveNegative absence unknownVersion; do
    case_dir="$tmp/$provider-$case_name"
    materialize_adversarial_fixture "$provider" "$case_name" "$case_dir"
    "$cli" "$provider" --fixture "$case_dir" > "$tmp/$provider-$case_name.json"
    python3 "$root/tests/lib/json_schema_subset.py" "$schema" "$tmp/$provider-$case_name.json" || fail "$provider $case_name report violates schema"
  done
done

# Claude declarations are parsed as complete semantic blocks. A recognized
# positive prefix followed by a same-line or continuation-line refutation must
# retain both evidence sides and can never become supported.
for case_name in purePositive safeIgnoredSameLine safeUnsupported safeNoEffect safeUnavailable safeIgnoredNextLine disallowedIgnored; do
  case_dir="$tmp/claude-$case_name"
  materialize_adversarial_fixture claude "$case_name" "$case_dir"
  "$cli" claude --fixture "$case_dir" > "$tmp/claude-$case_name.json"
done
jq -e '
  .capabilities.hardSubagentDisable.status == "supported" and
  .capabilities.userConfigurationIsolation.status == "unknown"
' "$tmp/claude-purePositive.json" >/dev/null || fail 'Claude pure positive declarations were not resolved conservatively'
for case_name in safeIgnoredSameLine safeUnsupported safeNoEffect safeUnavailable safeIgnoredNextLine disallowedIgnored; do
  jq -e '
    .capabilities.hardSubagentDisable.status == "unknown" and
    .capabilities.hardSubagentDisable.status != "supported" and
    .capabilities.userConfigurationIsolation.status == "unknown"
  ' "$tmp/claude-$case_name.json" >/dev/null || fail "Claude negative suffix produced support: $case_name"
done

# A conflicted safe-mode prerequisite plus an incomplete Agent-deny
# prerequisite must remain unknown. The hard-disable composite may consume only
# those resolved states, never safe-mode's raw negative evidence.
case_dir="$tmp/claude-compositeConflictIncomplete"
materialize_adversarial_fixture claude compositeConflictIncomplete "$case_dir"
"$cli" claude --fixture "$case_dir" > "$tmp/claude-compositeConflictIncomplete.json"
jq -e '
  .capabilities.hardSubagentDisable.status == "unknown" and
  .capabilities.hardSubagentDisable.status != "unsupported" and
  .capabilities.providerManagedSubagents.status == "unknown" and
  .capabilities.userConfigurationIsolation.status == "unknown"
' "$tmp/claude-compositeConflictIncomplete.json" >/dev/null ||
  fail 'Claude conflicted/incomplete prerequisites did not propagate unknown'

# Positive and authoritative negative evidence are collected independently;
# neither side wins by branch order.
jq -e '
  .capabilities.structuredOutputSchema.status == "unknown" and
  (.capabilities.structuredOutputSchema.evidence | length) == 2 and
  .capabilities.providerManagedSubagents.status == "unknown" and
  (.capabilities.providerManagedSubagents.evidence | length) == 2 and
  .capabilities.hardSubagentDisable.status == "unknown"
' "$tmp/codex-positiveNegative.json" >/dev/null || fail 'Codex positive/negative conflict did not resolve to unknown'
jq -e '
  .capabilities.userConfigurationIsolation.status == "unknown" and
  (.capabilities.userConfigurationIsolation.evidence | length) == 2 and
  .capabilities.hardSubagentDisable.status == "unknown" and
  (.capabilities.hardSubagentDisable.evidence | length) == 2
' "$tmp/claude-positiveNegative.json" >/dev/null || fail 'Claude positive/negative conflict did not resolve to unknown'
jq -e '
  .capabilities.structuredEventStream.status == "unknown" and
  (.capabilities.structuredEventStream.evidence | length) == 2
' "$tmp/opencode-positiveNegative.json" >/dev/null || fail 'OpenCode positive/negative conflict did not resolve to unknown'

jq -e '.capabilities.structuredOutputSchema.status == "unknown" and .capabilities.providerManagedSubagents.status == "unknown"' "$tmp/codex-absence.json" >/dev/null || fail 'Codex absence did not remain unknown'
jq -e '[.capabilities[].status] | all(. == "unknown")' "$tmp/claude-absence.json" >/dev/null || fail 'Claude absence did not remain unknown'
jq -e '.capabilities.structuredOutputSchema.status == "unknown" and .capabilities.providerManagedSubagents.status == "unknown"' "$tmp/opencode-absence.json" >/dev/null || fail 'OpenCode absence did not remain unknown'

# Structurally well-typed OpenCode fixtures are rejected when probeStatus=ok
# contradicts the complete experiment invariants. In particular, child deny
# alone and a failed inline collision cannot prove any capability.
for case_name in semanticCollisionFalse semanticChildDenyOnly semanticOkIncomplete; do
  case_dir="$tmp/opencode-$case_name"
  materialize_adversarial_fixture opencode "$case_name" "$case_dir"
  set +e
  "$cli" opencode --fixture "$case_dir" > "$tmp/opencode-$case_name.out" 2> "$tmp/opencode-$case_name.err"
  semantic_fixture_rc=$?
  set -e
  [ "$semantic_fixture_rc" -eq 2 ] || fail "OpenCode semantic fixture was accepted: $case_name"
  grep -Fq 'semantically invalid config-probe.json' "$tmp/opencode-$case_name.err" || fail "OpenCode semantic fixture error unclear: $case_name"
  ! grep -Fq '"status":"supported"' "$tmp/opencode-$case_name.out" || fail "OpenCode semantic fixture produced support: $case_name"
done

jq -e '
  .capabilities.structuredEventStream.status == "unknown" and
  .capabilities.ephemeralSession.status == "unknown" and
  .capabilities.hardSubagentDisable.status == "unknown"
' "$tmp/codex-negativeTokens.json" >/dev/null || fail 'Codex negative-token prose invented support'
jq -e '[.capabilities[].status] | all(. != "supported")' "$tmp/claude-negativeTokens.json" >/dev/null || fail 'Claude negative-token prose invented support'
jq -e '
  .capabilities.freshInvocation.status == "supported" and
  ([.capabilities | to_entries[] | select(.key != "freshInvocation") | .value.status] | all(. == "unknown"))
' "$tmp/opencode-negativeTokens.json" >/dev/null || fail 'OpenCode negative-token prose invented support'

jq -e '.capabilities.freshInvocation.status == "supported" and .capabilities.explicitModelSelection.status == "supported" and .capabilities.structuredEventStream.status == "unknown" and .capabilities.hardSubagentDisable.status == "unknown"' "$tmp/codex-partial.json" >/dev/null || fail 'Codex partial help was not conservative'
jq -e '.capabilities.explicitModelSelection.status == "supported" and ([.capabilities | to_entries[] | select(.key != "explicitModelSelection") | .value.status] | all(. == "unknown"))' "$tmp/claude-partial.json" >/dev/null || fail 'Claude partial help was not conservative'
jq -e '.capabilities.freshInvocation.status == "supported" and .capabilities.explicitModelSelection.status == "supported" and ([.capabilities | to_entries[] | select(.key != "freshInvocation" and .key != "explicitModelSelection") | .value.status] | all(. == "unknown"))' "$tmp/opencode-partial.json" >/dev/null || fail 'OpenCode partial help was not conservative'

for provider in codex claude opencode; do
  jq -e '[.capabilities[].status] | all(. == "unknown")' "$tmp/$provider-unexpected.json" >/dev/null || fail "$provider unexpected help invented a capability"
done
jq -e '.capabilities.structuredOutputSchema.status == "unsupported" and .capabilities.providerManagedSubagents.status == "unsupported" and .capabilities.hardSubagentDisable.status == "unsupported"' "$tmp/codex-explicitNegative.json" >/dev/null || fail 'Codex explicit negative evidence was not preserved'
jq -e '.capabilities.separateFinalOutputFile.status == "unsupported" and .capabilities.structuredOutputSchema.status == "unsupported" and .capabilities.automaticCompactionThreshold.status == "unsupported"' "$tmp/claude-explicitNegative.json" >/dev/null || fail 'Claude explicit negative evidence was not preserved'
jq -e '.capabilities.separateFinalOutputFile.status == "unsupported" and .capabilities.structuredOutputSchema.status == "unsupported" and .capabilities.hardSubagentDisable.status == "unknown"' "$tmp/opencode-explicitNegative.json" >/dev/null || fail 'OpenCode explicit negative evidence was not preserved'

for provider in codex claude opencode; do
  jq -S .capabilities "$tmp/$provider-partial.json" > "$tmp/$provider-partial-caps.json"
  jq -S .capabilities "$tmp/$provider-unknownVersion.json" > "$tmp/$provider-unknown-caps.json"
  cmp -s "$tmp/$provider-partial-caps.json" "$tmp/$provider-unknown-caps.json" || fail "$provider unknown version inherited capabilities"
  jq -e '.providerVersion == "99.99.99"' "$tmp/$provider-unknownVersion.json" >/dev/null || fail "$provider unknown valid version was not reported"
done

# A version change is reflected without cache reuse; identical evidence keeps
# the capability matrix identical. An unrecognized but well-formed version is
# never used as a reason to invent support.
cp -R "$fixtures/codex-limited" "$tmp/codex-version-a"
cp -R "$fixtures/codex-limited" "$tmp/codex-version-b"
printf '%s\n' 'codex-cli 0.90.1' > "$tmp/codex-version-b/version.txt"
"$cli" codex --fixture "$tmp/codex-version-a" > "$tmp/version-a.json"
"$cli" codex --fixture "$tmp/codex-version-b" > "$tmp/version-b.json"
[ "$(jq -r .providerVersion "$tmp/version-a.json")" != "$(jq -r .providerVersion "$tmp/version-b.json")" ] || fail 'version change was hidden'
jq -S .capabilities "$tmp/version-a.json" > "$tmp/caps-a.json"
jq -S .capabilities "$tmp/version-b.json" > "$tmp/caps-b.json"
cmp -s "$tmp/caps-a.json" "$tmp/caps-b.json" || fail 'capabilities changed without probe evidence changing'
printf '%s\n' 'codex-cli 99.99.99' > "$tmp/codex-version-b/version.txt"
"$cli" codex --fixture "$tmp/codex-version-b" > "$tmp/unknown-version.json"
jq -e '.providerVersion == "99.99.99" and .capabilities.hardSubagentDisable.status == "unsupported"' "$tmp/unknown-version.json" >/dev/null || fail 'unknown version produced false support'

cp -R "$fixtures/codex-supported" "$tmp/malformed-version"
printf '%s\n' 'codex version surprise secret=leak' > "$tmp/malformed-version/version.txt"
if "$cli" codex --fixture "$tmp/malformed-version" > "$tmp/malformed.out" 2> "$tmp/malformed.err"; then fail 'malformed version output succeeded'; fi
grep -Fq 'unexpected codex --version output' "$tmp/malformed.err" || fail 'malformed version error unclear'

cp -R "$fixtures/codex-supported" "$tmp/malformed-features"
printf '%s\n' 'not structured feature output' > "$tmp/malformed-features/features.txt"
"$cli" codex --fixture "$tmp/malformed-features" > "$tmp/malformed-features.json"
jq -e '.capabilities.providerManagedSubagents.status == "unknown" and .capabilities.hardSubagentDisable.status == "unknown"' "$tmp/malformed-features.json" >/dev/null || fail 'malformed feature output invented support'

cp -R "$fixtures/claude-limited" "$tmp/unexpected-help"
printf '%s\n' 'unexpected provider help payload' > "$tmp/unexpected-help/root-help.txt"
"$cli" claude --fixture "$tmp/unexpected-help" > "$tmp/unexpected-help.json"
jq -e '
  .capabilities.structuredEventStream.status == "unknown" and
  .capabilities.structuredOutputSchema.status == "unknown" and
  .capabilities.hardSubagentDisable.status == "unknown"
' "$tmp/unexpected-help.json" >/dev/null || fail 'unexpected help output invented support'

cp -R "$fixtures/opencode-supported" "$tmp/malformed-fixture"
printf '%s\n' '{malformed' > "$tmp/malformed-fixture/config-probe.json"
if "$cli" opencode --fixture "$tmp/malformed-fixture" >/dev/null 2> "$tmp/fixture.err"; then fail 'malformed fixture succeeded'; fi
grep -Fq 'capability fixture is malformed' "$tmp/fixture.err" || fail 'malformed fixture error unclear'
if "$cli" imaginary --fixture "$fixtures/codex-supported" >/dev/null 2> "$tmp/adapter.err"; then fail 'missing adapter succeeded'; fi
grep -Fq 'provider adapter does not exist' "$tmp/adapter.err" || fail 'missing adapter error unclear'
if "$cli" codex --binary "$tmp/no-such-provider" >/dev/null 2> "$tmp/missing.err"; then fail 'missing binary succeeded'; fi
grep -Fq 'provider binary is missing' "$tmp/missing.err" || fail 'missing binary error unclear'

mkdir -p "$tmp/bin"
printf '%s\n' '#!/usr/bin/env bash' 'exit 7' > "$tmp/bin/version-failure"
printf '%s\n' '#!/usr/bin/env bash' 'if [ "${1:-}" = --version ]; then echo "codex-cli 1.2.3"; exit 0; fi' 'exit 8' > "$tmp/bin/help-failure"
chmod +x "$tmp/bin/version-failure" "$tmp/bin/help-failure"
if "$cli" codex --binary "$tmp/bin/version-failure" >/dev/null 2> "$tmp/version-failure.err"; then fail 'version failure succeeded'; fi
grep -Fq 'codex --version failed' "$tmp/version-failure.err" || fail 'version failure error unclear'
if "$cli" codex --binary "$tmp/bin/help-failure" >/dev/null 2> "$tmp/help-failure.err"; then fail 'help failure succeeded'; fi
grep -Fq 'codex --help failed' "$tmp/help-failure.err" || fail 'help failure error unclear'

set +e
"$cli" codex --binary "$tmp/no-such-provider" >/dev/null 2>/dev/null; missing_binary_rc=$?
"$cli" codex --binary "$tmp/bin/version-failure" >/dev/null 2>/dev/null; version_failure_rc=$?
"$cli" codex --binary "$tmp/bin/help-failure" >/dev/null 2>/dev/null; help_failure_rc=$?
"$cli" codex --fixture "$tmp/malformed-version" >/dev/null 2>/dev/null; malformed_version_rc=$?
"$cli" opencode --fixture "$tmp/malformed-fixture" >/dev/null 2>/dev/null; malformed_fixture_rc=$?
"$cli" imaginary --fixture "$fixtures/codex-supported" >/dev/null 2>/dev/null; missing_adapter_rc=$?
set -e
[ "$missing_binary_rc" -eq 3 ] || fail "binary missing exit changed: $missing_binary_rc"
[ "$version_failure_rc" -eq 4 ] || fail "version failure exit changed: $version_failure_rc"
[ "$help_failure_rc" -eq 5 ] || fail "help failure exit changed: $help_failure_rc"
[ "$malformed_version_rc" -eq 6 ] || fail "malformed version exit changed: $malformed_version_rc"
[ "$malformed_fixture_rc" -eq 2 ] || fail "malformed fixture exit changed: $malformed_fixture_rc"
[ "$missing_adapter_rc" -eq 2 ] || fail "missing adapter exit changed: $missing_adapter_rc"

# The OpenCode probe creates isolated user/project configs, observes their
# merge, and proves inline collision precedence without claiming full config
# isolation.
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'if [ "${1:-}" = --version ]; then printf "%s\n" "1.18.18"; exit 0; fi' \
  'if [ "${1:-}" = --help ]; then cat "$MANA_CTX02_ROOT_HELP"; exit 0; fi' \
  'if [ "${1:-}" = run ] && [ "${2:-}" = --help ]; then cat "$MANA_CTX02_RUN_HELP"; exit 0; fi' \
  'if [ "${1:-}" = debug ] && [ "${2:-}" = config ] && [ "${3:-}" = --pure ]; then' \
  '  [ "${MANA_CTX02_CONFIG_FAIL:-false}" = false ] || exit 9' \
  '  jq -s --argjson inline "$OPENCODE_CONFIG_CONTENT" ".[0] * .[1] * \$inline" "$XDG_CONFIG_HOME/opencode/opencode.json" "$PWD/opencode.json"' \
  '  exit $?' \
  'fi' \
  'exit 8' > "$tmp/bin/opencode-config-probe"
chmod +x "$tmp/bin/opencode-config-probe"
MANA_CTX02_ROOT_HELP="$fixtures/opencode-supported/root-help.txt" MANA_CTX02_RUN_HELP="$fixtures/opencode-supported/run-help.txt" \
  "$cli" opencode --binary "$tmp/bin/opencode-config-probe" > "$tmp/opencode-config-precedence.json"
jq -e '
  .probeEvidence == ["version:ok","help:root","help:run","config:ok"] and
  .capabilities.providerManagedSubagents.status == "supported" and
  .capabilities.recursiveDelegationPrevention.status == "unknown" and
  .capabilities.hardSubagentDisable.status == "unknown" and
  .capabilities.userConfigurationIsolation.status == "unknown"
' "$tmp/opencode-config-precedence.json" >/dev/null || fail 'OpenCode config precedence was overstated'
set +e
MANA_CTX02_CONFIG_FAIL=true MANA_CTX02_ROOT_HELP="$fixtures/opencode-supported/root-help.txt" MANA_CTX02_RUN_HELP="$fixtures/opencode-supported/run-help.txt" \
  "$cli" opencode --binary "$tmp/bin/opencode-config-probe" >/dev/null 2> "$tmp/opencode-probe-failure.err"
opencode_probe_failure_rc=$?
set -e
[ "$opencode_probe_failure_rc" -eq 5 ] || fail "OpenCode probe failure exit changed: $opencode_probe_failure_rc"
grep -Fq 'opencode config probe failed' "$tmp/opencode-probe-failure.err" || fail 'OpenCode probe failure error unclear'

# Exact provider argv/config contract, element by element.
# shellcheck source=../scripts/lib/provider-dispatch.sh
. "$root/scripts/lib/provider-dispatch.sh"
mana_provider_profile_args codex '/repo path' model 3 1 true
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/codex-enabled.args"
assert_argv_exact "$tmp/codex-enabled.args" --ask-for-approval on-request exec --model model --cd '/repo path' --sandbox workspace-write -c agents.max_threads=3 -c agents.max_depth=1 -c agents.interrupt_message=false
assert_adjacent_pair "$tmp/codex-enabled.args" '-c' 'agents.max_threads=3'
assert_adjacent_pair "$tmp/codex-enabled.args" '-c' 'agents.max_depth=1'
assert_no_element "$tmp/codex-enabled.args" '--disable'
mana_provider_profile_args codex '/repo path' model 3 1 false
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/codex-disabled.args"
assert_argv_exact "$tmp/codex-disabled.args" --ask-for-approval on-request exec --model model --cd '/repo path' --sandbox workspace-write --ephemeral --ignore-user-config --disable multi_agent --disable multi_agent_v2 -c agents.max_threads=1 -c agents.max_depth=0 -c agents.interrupt_message=false
assert_adjacent_pair "$tmp/codex-disabled.args" '--disable' 'multi_agent'
assert_element "$tmp/codex-disabled.args" 'multi_agent_v2'
assert_adjacent_pair "$tmp/codex-disabled.args" '-c' 'agents.max_threads=1'
assert_adjacent_pair "$tmp/codex-disabled.args" '-c' 'agents.max_depth=0'
assert_element "$tmp/codex-disabled.args" '--ignore-user-config'

mana_provider_profile_args claude '/repo path' model 3 1 true
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/claude-enabled.args"
assert_argv_exact "$tmp/claude-enabled.args" -p --agent mana-orchestrator --model model --permission-mode default
assert_adjacent_pair "$tmp/claude-enabled.args" '--agent' 'mana-orchestrator'
mana_provider_profile_args claude '/repo path' model 3 1 false
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/claude-disabled.args"
assert_argv_exact "$tmp/claude-disabled.args" -p --model model --permission-mode default --safe-mode --no-session-persistence --disable-slash-commands --disallowedTools Agent
assert_element "$tmp/claude-disabled.args" '--safe-mode'
assert_adjacent_pair "$tmp/claude-disabled.args" '--disallowedTools' 'Agent'
assert_no_element "$tmp/claude-disabled.args" '--agent'

mana_provider_profile_args opencode '/repo path' 'provider/model' 3 1 true
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/opencode-enabled.args"
assert_argv_exact "$tmp/opencode-enabled.args" run --dir '/repo path' --model provider/model --agent mana_orchestrator
assert_adjacent_pair "$tmp/opencode-enabled.args" '--agent' 'mana_orchestrator'
mana_provider_profile_args opencode '/repo path' 'provider/model' 3 1 false
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/opencode-disabled.args"
assert_argv_exact "$tmp/opencode-disabled.args" run --dir '/repo path' --model provider/model --agent mana_ctx02_no_children --pure
assert_adjacent_pair "$tmp/opencode-disabled.args" '--agent' 'mana_ctx02_no_children'
assert_element "$tmp/opencode-disabled.args" '--pure'
jq -e '.agent.mana_ctx02_no_children.permission.task == "deny" and .agent.mana_ctx02_no_children.model == "provider/model"' <<<"$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" >/dev/null || fail 'OpenCode hard-disable config is not exact'

# Stale managed/user agent files cannot bypass the invocation controls.
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$#" > "$MANA_CTX02_ARGC"' 'printf "%s\n" "$@" > "$MANA_CTX02_ARGS"' 'printf "%s" "${OPENCODE_CONFIG_CONTENT:-}" > "$MANA_CTX02_CONFIG"' 'exit 0' > "$tmp/bin/provider-stub"
chmod +x "$tmp/bin/provider-stub"
for provider in codex claude opencode; do
  cp "$tmp/bin/provider-stub" "$tmp/bin/$provider"
done

codex_project="$tmp/stale codex"
mkdir -p "$codex_project/.codex/agents"
printf '%s\n' '# stale managed child' > "$codex_project/.codex/agents/mana-full-specialist.toml"
MANA_CTX02_ARGC="$tmp/stale-codex.argc" MANA_CTX02_ARGS="$tmp/stale-codex.args" MANA_CTX02_CONFIG="$tmp/stale-codex.config" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" story-start --project-root "$codex_project" --codex --no-codex-subagents > "$tmp/stale-codex.out" 2> "$tmp/stale-codex.err"
assert_adjacent_pair "$tmp/stale-codex.args" '--disable' 'multi_agent'
assert_element "$tmp/stale-codex.args" '--ignore-user-config'
grep -Fq 'Effective child limits: Codex=0/0' "$tmp/stale-codex.args" || fail 'Codex prompt lacks effective zero child state'
[ "$(< "$tmp/stale-codex.argc")" -eq 25 ] || fail "Codex actual disabled argc changed: $(< "$tmp/stale-codex.argc")"

claude_project="$tmp/stale claude"
mkdir -p "$claude_project/.claude/agents"
printf '%s\n' '# user stale agent' 'tools: Agent,Read' > "$claude_project/.claude/agents/mana-orchestrator.md"
cp "$claude_project/.claude/agents/mana-orchestrator.md" "$tmp/stale-claude-agent.before"
MANA_CTX02_ARGC="$tmp/stale-claude.argc" MANA_CTX02_ARGS="$tmp/stale-claude.args" MANA_CTX02_CONFIG="$tmp/stale-claude.config" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" story-start --project-root "$claude_project" --claude --no-claude-subagents > "$tmp/stale-claude.out" 2> "$tmp/stale-claude.err"
assert_element "$tmp/stale-claude.args" '--safe-mode'
assert_adjacent_pair "$tmp/stale-claude.args" '--disallowedTools' 'Agent'
assert_no_element "$tmp/stale-claude.args" 'mana-orchestrator'
grep -Fq 'Effective child limits: Codex=3/1; Claude=0/0' "$tmp/stale-claude.args" || fail 'Claude prompt lacks effective zero child state'
[ "$(< "$tmp/stale-claude.argc")" -eq 11 ] || fail "Claude actual disabled argc changed: $(< "$tmp/stale-claude.argc")"
cmp -s "$tmp/stale-claude-agent.before" "$claude_project/.claude/agents/mana-orchestrator.md" || fail 'Claude disabled path modified a user-owned orchestrator'

opencode_project="$tmp/stale opencode"
mkdir -p "$opencode_project/.opencode/agents"
printf '%s\n' '# user stale agent' 'mode: primary' 'permission:' '  task: allow' > "$opencode_project/.opencode/agents/mana_orchestrator.md"
cp "$opencode_project/.opencode/agents/mana_orchestrator.md" "$tmp/stale-opencode-agent.before"
MANA_CTX02_ARGC="$tmp/stale-opencode.argc" MANA_CTX02_ARGS="$tmp/stale-opencode.args" MANA_CTX02_CONFIG="$tmp/stale-opencode.config" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" story-start --project-root "$opencode_project" --opencode --no-opencode-subagents > "$tmp/stale-opencode.out" 2> "$tmp/stale-opencode.err"
assert_adjacent_pair "$tmp/stale-opencode.args" '--agent' 'mana_ctx02_no_children'
jq -e '.agent.mana_ctx02_no_children.permission.task == "deny"' "$tmp/stale-opencode.config" >/dev/null || fail 'OpenCode invocation-local task deny missing'
grep -Fq 'Effective child limits: Codex=3/1; Claude=3/1; OpenCode=0/0' "$tmp/stale-opencode.args" || fail 'OpenCode prompt lacks effective zero child state'
[ "$(< "$tmp/stale-opencode.argc")" -eq 9 ] || fail "OpenCode actual disabled argc changed: $(< "$tmp/stale-opencode.argc")"
cmp -s "$tmp/stale-opencode-agent.before" "$opencode_project/.opencode/agents/mana_orchestrator.md" || fail 'OpenCode disabled path modified a user-owned orchestrator'

# Clean and pre-existing Mana-managed orchestrators are also unchanged. The
# disabled paths need no persistent custom-agent artifact.
clean_claude_project="$tmp/clean claude"
mkdir -p "$clean_claude_project"
MANA_CTX02_ARGC="$tmp/clean-claude.argc" MANA_CTX02_ARGS="$tmp/clean-claude.args" MANA_CTX02_CONFIG="$tmp/clean-claude.config" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" story-start --project-root "$clean_claude_project" --claude --no-claude-subagents > "$tmp/clean-claude.out" 2> "$tmp/clean-claude.err"
[ ! -e "$clean_claude_project/.claude/agents/mana-orchestrator.md" ] || fail 'Claude disabled path created a managed orchestrator'

managed_claude_project="$tmp/managed claude"
mkdir -p "$managed_claude_project/.claude/agents"
printf '%s\n' '# Mana-managed Claude Code subagent.' 'tools: Agent,Read' > "$managed_claude_project/.claude/agents/mana-orchestrator.md"
cp "$managed_claude_project/.claude/agents/mana-orchestrator.md" "$tmp/managed-claude-agent.before"
MANA_CTX02_ARGC="$tmp/managed-claude.argc" MANA_CTX02_ARGS="$tmp/managed-claude.args" MANA_CTX02_CONFIG="$tmp/managed-claude.config" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" story-start --project-root "$managed_claude_project" --claude --no-claude-subagents > "$tmp/managed-claude.out" 2> "$tmp/managed-claude.err"
cmp -s "$tmp/managed-claude-agent.before" "$managed_claude_project/.claude/agents/mana-orchestrator.md" || fail 'Claude disabled path modified a Mana-managed orchestrator'

clean_opencode_project="$tmp/clean opencode"
mkdir -p "$clean_opencode_project"
MANA_CTX02_ARGC="$tmp/clean-opencode.argc" MANA_CTX02_ARGS="$tmp/clean-opencode.args" MANA_CTX02_CONFIG="$tmp/clean-opencode.config" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" story-start --project-root "$clean_opencode_project" --opencode --no-opencode-subagents > "$tmp/clean-opencode.out" 2> "$tmp/clean-opencode.err"
[ ! -e "$clean_opencode_project/.opencode/agents/mana_orchestrator.md" ] || fail 'OpenCode disabled path created a managed orchestrator'

managed_opencode_project="$tmp/managed opencode"
mkdir -p "$managed_opencode_project/.opencode/agents"
printf '%s\n' '# Mana-managed OpenCode agent.' 'mode: primary' 'permission:' '  task: allow' > "$managed_opencode_project/.opencode/agents/mana_orchestrator.md"
cp "$managed_opencode_project/.opencode/agents/mana_orchestrator.md" "$tmp/managed-opencode-agent.before"
MANA_CTX02_ARGC="$tmp/managed-opencode.argc" MANA_CTX02_ARGS="$tmp/managed-opencode.args" MANA_CTX02_CONFIG="$tmp/managed-opencode.config" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" story-start --project-root "$managed_opencode_project" --opencode --no-opencode-subagents > "$tmp/managed-opencode.out" 2> "$tmp/managed-opencode.err"
cmp -s "$tmp/managed-opencode-agent.before" "$managed_opencode_project/.opencode/agents/mana_orchestrator.md" || fail 'OpenCode disabled path modified a Mana-managed orchestrator'

# Inspection is read-only and privacy-safe.
inspect_cwd="$tmp/inspection cwd"
mkdir -p "$inspect_cwd"
(cd "$inspect_cwd" && MANA_SECRET_SENTINEL='do-not-leak-ctx02' "$cli" codex --fixture "$fixtures/codex-supported" > "$tmp/privacy.json")
[ ! -e "$inspect_cwd/.mana" ] || fail 'capability inspection created .mana'
! grep -Fq 'do-not-leak-ctx02' "$tmp/privacy.json" || fail 'arbitrary environment leaked'
jq -e '
  ([paths(scalars) as $p | $p[-1] | strings] | all(. != "prompt" and . != "response" and . != "source" and . != "reasoning" and . != "credentials" and . != "environment" and . != "toolPayload"))
' "$tmp/privacy.json" >/dev/null || fail 'privacy-forbidden field found'
after="$(git -C "$root" status --porcelain=v1)"
[ "$before" = "$after" ] || fail 'capability inspection or tests mutated tracked repository state'

echo 'Provider capability CTX-02-R3 tests passed (resolved-state composites, adversarial conflicts, and semantic probes; deterministic, zero-token)'
