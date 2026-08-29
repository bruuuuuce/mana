#!/usr/bin/env bash
# CTX-04 deterministic profile compilation and activation regressions.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd -P)"
compiler="$root/scripts/mana-compile-profile.sh"
validator="$root/scripts/lib/context-runtime.sh"
# shellcheck source=scripts/lib/profile-metadata.sh
. "$root/scripts/lib/profile-metadata.sh"
. "$root/scripts/lib/execution-plan.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-profile-compiler.XXXXXX")"
tmp="$(cd "$tmp" && pwd -P)"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
rejects() { if "$@" >/dev/null 2>&1; then fail "expected rejection: $*"; fi; }
auth_validate() {
  local candidate="$1" profile_id="$2" execution_id="$3"; shift 3
  python3 "$root/scripts/lib/context-runtime.py" authoritative-validate-context-manifest \
    "$candidate" "$root" "$profile_id" "$execution_id" "$@"
}
schema_valid() {
  python3 "$root/tests/lib/json_schema_subset.py" \
    "$root/contracts/context-runtime/context-manifest-v1.schema.json" "$1" >/dev/null
}
tamper_rejected() {
  local name="$1" source="$2" filter="$3" profile_id="$4" execution_id="$5" output; shift 5
  output="$tmp/tamper-$name.json"
  jq "$filter" "$source" > "$output"
  schema_valid "$output" || fail "$name tamper is not schema-valid"
  rejects auth_validate "$output" "$profile_id" "$execution_id" "$@"
}

# Every current profile graph compiles, validates, and is stable for unchanged
# inputs. Declarative graphs partition candidates; legacy profiles warn and
# preserve the historical all-candidates activation.
profile_count=0
for profile_file in "$root"/profiles/*.yaml; do
  profile="${profile_file##*/}"; profile="${profile%.yaml}"
  profile_count=$((profile_count + 1))
  first="$tmp/$profile.first.json"
  second="$tmp/$profile.second.json"
  "$compiler" "$profile" --execution-id "execution-$profile" > "$first" 2> "$tmp/$profile.first.err"
  "$compiler" "$profile" --execution-id "execution-$profile" > "$second" 2> "$tmp/$profile.second.err"
  cmp -s "$first" "$second" || fail "$profile manifest is not deterministic"
  "$validator" validate-structure context-manifest "$first" || fail "$profile manifest failed structural schema validation"
  "$validator" validate-model context-manifest "$first" || fail "$profile manifest failed host validation"
  python3 "$root/scripts/lib/context-runtime.py" authoritative-validate-context-manifest \
    "$first" "$root" "$profile" "execution-$profile" || fail "$profile manifest failed authoritative validation"
  python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/context-runtime/context-manifest-v1.schema.json" "$first" || fail "$profile manifest failed offline schema validation"
  jq -e '([.activatedSkills[].id] + .inactiveSkills | sort) == (.declaredCandidateSkills | sort)' "$first" >/dev/null || fail "$profile candidate partition is incomplete"
  jq -e '([.activatedSkills[].id] | unique | length) == ([.activatedSkills[].id] | length)' "$first" >/dev/null || fail "$profile activates a skill more than once"
  if grep -q '^skill_activation:' "$profile_file"; then
    [ ! -s "$tmp/$profile.first.err" ] || fail "$profile declarative compilation emitted a legacy warning"
    jq -e '.activationMode == "declarative" and .warnings == []' "$first" >/dev/null || fail "$profile did not compile as declarative"
    while IFS='|' read -r signal skill; do
      [ -n "$signal" ] || continue
      edge="$tmp/$profile.$signal.json"
      "$compiler" "$profile" --execution-id "execution-$profile-$signal" --static-signal "$signal" > "$edge"
      jq -e --arg signal "$signal" --arg skill "$skill" '
        (.staticallyActivatedSkills | index({signal:$signal,skill:$skill})) != null and
        ([.activatedSkills[].id] | index($skill)) != null and
        ([.availableConditionalSkills[] | select(.signal == $signal)] | length) == 0
      ' "$edge" >/dev/null || fail "$profile conditional edge $signal -> $skill did not activate authoritatively"
    done <<EOF
$(mana_profile_conditional_activations "$profile_file")
EOF
  else
    grep -Fxq 'WARNING: Legacy activation fallback: profile has no skill_activation block; all candidate skills are active until migration.' "$tmp/$profile.first.err" || fail "$profile legacy warning missing from stderr"
    jq -e '.activationMode == "legacy-fallback" and (.warnings | length) == 1 and .inactiveSkills == [] and ([.activatedSkills[].reason] | all(. == "legacy-fallback"))' "$first" >/dev/null || fail "$profile legacy fallback is not explicit and compatible"
  fi
done
[ "$profile_count" -gt 0 ] || fail 'no profiles were compiled'

# Compact requested-pr-review starts with baseline work only. Inactive database,
# security, and full-tier candidates cannot create a pre-run escalation.
compact="$tmp/requested-compact.json"
"$compiler" requested-pr-review --execution-id execution-requested-compact > "$compact"
jq -e '
  .baselineSkills == ["changed-files-risk-classifier","pre-review-defect"] and
  .modelEscalationSkills == [] and
  .deepLoadedSkills == [] and
  (.inactiveSkills | index("liquibase-production-risk")) != null and
  (.inactiveSkills | index("dependency-security-evidence")) != null and
  ([.activatedSkills[].id] | index("liquibase-production-risk")) == null and
  ([.activatedSkills[].id] | index("dependency-security-evidence")) == null
' "$compact" >/dev/null || fail 'compact requested-pr-review advertises inactive specialist work'
[ "$(wc -c < "$compact" | tr -d ' ')" -le 8192 ] || fail 'ordinary compiled manifest exceeds the 8 KiB starting budget'
if grep -Fq 'skills/index.yaml' "$compact"; then fail 'compiled manifest leaks the full skill-index location into model context'; fi

# Schema-valid tampering is still rejected at the host boundary: list
# relationships, activation provenance, and deep-load membership are semantic
# invariants rather than model assertions.
jq '.activatedSkills += [{id:"undeclared-specialist",reason:"baseline",activationSignal:null,modelTier:"full",riskLevel:"high",executionMode:"read",delegationGroup:"security",parallelSafe:true}]' "$compact" > "$tmp/undeclared-active.json"
rejects "$validator" validate-model context-manifest "$tmp/undeclared-active.json"
jq '.deepLoadedSkills += [{id:"liquibase-production-risk",instructionPath:"skills/liquibase-production-risk/SKILL.md"}]' "$compact" > "$tmp/inactive-deep-load.json"
rejects "$validator" validate-model context-manifest "$tmp/inactive-deep-load.json"
jq '.modelEscalationSkills += ["liquibase-production-risk"]' "$compact" > "$tmp/inactive-escalation.json"
rejects "$validator" validate-model context-manifest "$tmp/inactive-escalation.json"

mkdir -p "$tmp/bin" "$tmp/render-project"
ln -s "$root/tests/fixtures/context-runtime/codex-prompt-stub.sh" "$tmp/bin/codex"
rendered="$tmp/requested-rendered.txt"
MANA_TEST_CODEX_PROMPT="$rendered" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" requested-pr-review --project-root "$tmp/render-project" --codex --no-codex-subagents > "$tmp/render.out" 2> "$tmp/render.err"
grep -Fq 'active full-tier skills=none; escalation warning=none' "$rendered" || fail 'legacy renderer still escalates on inactive requested-pr-review candidates'
if grep -Fq 'skills/index.yaml' "$rendered"; then fail 'legacy renderer prompt still requires the full skill index'; fi
if grep -Fq 'active full-tier skills=liquibase-production-risk' "$rendered" || grep -Fq 'active full-tier skills=dependency-security-evidence' "$rendered"; then
  fail 'compact requested-pr-review prompt advertises inactive database/security specialist work'
fi
grep -Fq 'Compiled context manifest (authoritative for activation and routing)' "$rendered" || fail 'run-profile prompt does not declare manifest authority'
grep -Fq 'Candidate and inactive skills are catalog entries only, never selected work.' "$rendered" || fail 'run-profile prompt does not separate catalog from selected work'
if grep -Fq 'begin with baseline skills' "$rendered"; then fail 'run-profile still asks the model to reconstruct activation'; fi

rendered_high="$tmp/requested-rendered-high.txt"
MANA_TEST_CODEX_PROMPT="$rendered_high" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" requested-pr-review --project-root "$tmp/render-project" --codex --no-codex-subagents \
  --static-signal migration_or_schema_change > "$tmp/render-high.out" 2> "$tmp/render-high.err"
grep -Fq 'active full-tier skills=liquibase-production-risk' "$rendered_high" || fail 'run-profile did not route activated high-risk work from the manifest'
grep -Fq '"activationSignal":"migration_or_schema_change"' "$rendered_high" || fail 'run-profile prompt omitted authoritative activation reason'
grep -Fq '"id":"liquibase-production-risk","modelTier":"full"' "$rendered_high" || fail 'run-profile prompt omitted active authoritative metadata'
if grep -Fq '"id":"dependency-security-evidence","modelTier":"full"' "$rendered_high"; then
  fail 'run-profile prompt imported metadata for an inactive full candidate'
fi

# Authoritative materialization returns the exact in-memory value that passed
# comparison. Replacing the caller-owned pathname after that boundary cannot
# change execution-plan or prompt routing.
materialized="$tmp/requested-materialized.json"
python3 "$root/scripts/lib/context-runtime.py" authoritative-materialize-context-manifest \
  "$compact" "$root" requested-pr-review execution-requested-compact > "$materialized"
cmp -s "$compact" "$materialized" || fail 'authoritative materialization changed genuine canonical bytes'

toctou_manifest="$tmp/requested-toctou.json"
cp "$compact" "$toctou_manifest"
toctou_bin="$tmp/toctou-bin"
mkdir -p "$toctou_bin"
ln -s "$root/tests/fixtures/context-runtime/codex-prompt-stub.sh" "$toctou_bin/codex"
real_python="$(command -v python3)"
cat > "$toctou_bin/python3" <<'PYTHON_WRAPPER'
#!/usr/bin/env bash
"$MANA_TEST_REAL_PYTHON" "$@"
status=$?
if [ "$status" -eq 0 ] &&
   [ "${2:-}" = authoritative-materialize-context-manifest ] &&
   [ "${3:-}" = "$MANA_TEST_MUTABLE_MANIFEST" ]; then
  jq '(.activatedSkills |= map(if .id=="changed-files-risk-classifier" then .modelTier="full" | .riskLevel="high" else . end)) |
      .modelEscalationSkills=["changed-files-risk-classifier"]' \
    "$MANA_TEST_MUTABLE_MANIFEST" > "$MANA_TEST_MUTABLE_MANIFEST.swap"
  mv "$MANA_TEST_MUTABLE_MANIFEST.swap" "$MANA_TEST_MUTABLE_MANIFEST"
fi
exit "$status"
PYTHON_WRAPPER
chmod 700 "$toctou_bin/python3"
rendered_toctou="$tmp/requested-rendered-toctou.txt"
MANA_TEST_REAL_PYTHON="$real_python" \
MANA_TEST_MUTABLE_MANIFEST="$toctou_manifest" \
MANA_TEST_CODEX_PROMPT="$rendered_toctou" \
MANA_UPDATE_CHECK=off PATH="$toctou_bin:$PATH" \
  "$root/scripts/run-profile.sh" requested-pr-review --project-root "$tmp/render-project" \
    --codex --no-codex-subagents --context-manifest "$toctou_manifest" \
    --manifest-execution-id execution-requested-compact \
    > "$tmp/toctou.out" 2> "$tmp/toctou.err"
jq -e '.modelEscalationSkills == ["changed-files-risk-classifier"]' "$toctou_manifest" >/dev/null || fail 'TOCTOU fixture did not replace the caller manifest after validation'
grep -Fq 'active full-tier skills=none' "$rendered_toctou" || fail 'run-profile consumed routing bytes replaced after authoritative materialization'
if grep -Fq 'active full-tier skills=changed-files-risk-classifier' "$rendered_toctou" ||
   grep -Fq 'mana_orchestrator,mana_explorer,mana_full_specialist' "$rendered_toctou"; then
  fail 'post-validation manifest replacement changed runner selection'
fi

# A directly invoked runner compiles into an immutable shell value. Provider
# trap handling therefore cannot strand a mana-run-profile-manifest directory.
run_profile_tmp="$tmp/run-profile-tmp"
mkdir -p "$run_profile_tmp"
MANA_TEST_CODEX_PROMPT="$tmp/requested-rendered-no-residue.txt" \
MANA_UPDATE_CHECK=off TMPDIR="$run_profile_tmp" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" requested-pr-review --project-root "$tmp/render-project" \
    --codex --no-codex-subagents > "$tmp/no-residue.out" 2> "$tmp/no-residue.err"
if find "$run_profile_tmp" -mindepth 1 -print -quit | grep -q .; then
  fail 'run-profile left temporary manifest or provider residue behind'
fi

# Host signals and classifier requests activate only declared conditional work,
# compile complete lightweight routing metadata, and expose instruction paths
# only for explicitly deep-loaded active skills.
active="$tmp/requested-active.json"
"$compiler" requested-pr-review --execution-id execution-requested-active \
  --static-signal migration_or_schema_change \
  --request-skill dependency-security-evidence \
  --deep-load-skill liquibase-production-risk \
  --deep-load-skill dependency-security-evidence > "$active"
jq -e '
  (.staticallyActivatedSkills | index({signal:"migration_or_schema_change",skill:"liquibase-production-risk"})) != null and
  (.semanticallyRequestedSkills | index({skill:"dependency-security-evidence",signal:"dependency_manifest_or_lockfile_change"})) != null and
  ([.modelEscalationSkills[]] | sort) == ["dependency-security-evidence","liquibase-production-risk"] and
  ([.deepLoadedSkills[].id] | sort) == ["dependency-security-evidence","liquibase-production-risk"] and
  ([.activatedSkills[] | select(.id == "liquibase-production-risk")][0] |
    .reason == "static-signal" and .modelTier == "full" and .riskLevel == "high" and
    .executionMode == "read" and .delegationGroup == "database" and .parallelSafe == true)
' "$active" >/dev/null || fail 'activated specialist metadata or provenance is incomplete'

rejects "$compiler" requested-pr-review --execution-id execution-invalid --static-signal undeclared_signal
rejects "$compiler" requested-pr-review --execution-id execution-invalid --request-skill database-read-verification
rejects "$compiler" requested-pr-review --execution-id execution-invalid --deep-load-skill liquibase-production-risk

# Every requested-pr-review conditional mapping already declared by the
# current profile activates exactly its mapped skill plus the unchanged two
# baselines. application_code_change / pre-review-defect migration is deferred
# to PRC-02 and is deliberately absent from this CTX-04 matrix.
requested_edges=0
while IFS='|' read -r signal expected_skill; do
  [ -n "$signal" ] || continue
  requested_edges=$((requested_edges + 1))
  edge="$tmp/requested-edge-$signal.json"
  "$compiler" requested-pr-review --execution-id "execution-requested-$signal" \
    --static-signal "$signal" > "$edge"
  auth_validate "$edge" requested-pr-review "execution-requested-$signal" --static-signal "$signal" || fail "authoritative validation rejected genuine $signal edge"
  jq -e --arg signal "$signal" --arg expected "$expected_skill" '
    .staticallyActivatedSkills == [{signal:$signal,skill:$expected}] and
    ([.activatedSkills[].id] | sort) == (["changed-files-risk-classifier","pre-review-defect",$expected] | sort) and
    ([.activatedSkills[] | select(.id == $expected)] | length) == 1
  ' "$edge" >/dev/null || fail "requested-pr-review signal $signal activated unrelated work"
done <<EOF
$(mana_profile_conditional_activations "$root/profiles/requested-pr-review.yaml")
EOF
[ "$requested_edges" = 9 ] || fail "requested-pr-review CTX-04 matrix must contain exactly nine existing signals"
! grep -Fq 'application_code_change' "$root/profiles/requested-pr-review.yaml" || fail 'CTX-04 introduced PRC-02 application_code_change'
grep -Fq '    - pre-review-defect' "$root/profiles/requested-pr-review.yaml" || fail 'CTX-04 moved pre-review-defect out of the current baseline'

# Permanent cast regressors consume the same canonical manifest projection.
cast_project="$tmp/cast project with spaces"
mkdir -p "$cast_project/.mana/global"
for context_file in service-mission.md architecture.md engineering-guards.md; do
  printf 'fixture context\n' > "$cast_project/.mana/global/$context_file"
done
MANA_UPDATE_CHECK=off "$root/scripts/cast.sh" requested-pr-review --project-root "$cast_project" --dry-run --json > "$tmp/cast-compact.json"
jq -e '
  (.candidateSkills | length) == 11 and
  .skills == ["changed-files-risk-classifier","pre-review-defect"] and
  (.inactiveSkills | length) == 9 and .deepLoadedSkills == [] and
  .runnerClasses == ["mana_orchestrator","mana_explorer"] and
  (.runnerClasses | index("mana_full_specialist")) == null and
  .contextManifest.modelEscalationSkills == []
' "$tmp/cast-compact.json" >/dev/null || fail 'cast compact path selected inactive candidate work'

MANA_UPDATE_CHECK=off "$root/scripts/cast.sh" requested-pr-review --project-root "$cast_project" --dry-run --json \
  --static-signal migration_or_schema_change > "$tmp/cast-high.json"
jq -e '
  .skills == ["changed-files-risk-classifier","liquibase-production-risk","pre-review-defect"] and
  (.runnerClasses | index("mana_full_specialist")) != null and
  .contextManifest.modelEscalationSkills == ["liquibase-production-risk"] and
  ([.contextManifest.activatedSkills[] | select(.id == "liquibase-production-risk")][0] |
    .activationSignal == "migration_or_schema_change" and .modelTier == "full" and
    .riskLevel == "high" and .delegationGroup == "database") and
  ([.skills[] | select(. == "dependency-security-evidence")] | length) == 0
' "$tmp/cast-high.json" >/dev/null || fail 'cast conditional high-risk routing is not active-only'

# Multiple active full skills in one delegation group still select one stable
# specialist class. Unspecified tiers are never promoted solely for being
# candidates; legacy fallback remains explicitly all-candidate.
composite="$tmp/dev-assist-composite.json"
"$compiler" dev-assist --execution-id execution-composite \
  --static-signal shared_state_async_or_transaction_change \
  --static-signal architecture_boundary_change > "$composite"
mana_execution_plan "$root" "$composite" || fail "$MANA_PLAN_ERROR"
[ "$(printf '%s\n' "$MANA_PLAN_RUNNERS" | grep -c '^mana_full_specialist$')" = 1 ] || fail 'composite full work selected a nondeterministic number of specialists'
legacy_plan="$tmp/legacy-plan.json"
"$compiler" architecture-review --execution-id execution-legacy-plan > "$legacy_plan" 2> "$tmp/legacy-plan.err"
mana_execution_plan "$root" "$legacy_plan" || fail "$MANA_PLAN_ERROR"
grep -Fxq mana_full_specialist <<<"$MANA_PLAN_RUNNERS" || fail 'legacy fallback did not preserve explicit all-candidate escalation behavior'

# Authoritative anti-tampering: every mutation remains JSON-schema-valid, but
# is rejected because the expected value is reconstructed from framework root,
# profile id, catalogs, and host-declared activation inputs.
high="$tmp/high-simple.json"
"$compiler" requested-pr-review --execution-id execution-high --static-signal migration_or_schema_change > "$high"
economy="$tmp/economy-simple.json"
"$compiler" story-start --execution-id execution-economy > "$economy"
legacy="$tmp/legacy-simple.json"
"$compiler" architecture-review --execution-id execution-legacy > "$legacy" 2> "$tmp/legacy-simple.err"
architecture_active="$tmp/architecture-active.json"
"$compiler" requested-pr-review --execution-id execution-architecture --static-signal architecture_boundary_change > "$architecture_active"

tamper_rejected profile-a-skill-b "$compact" '.profileId="pr-ready"' requested-pr-review execution-requested-compact
tamper_rejected nonexistent-catalog-skill "$compact" '.declaredCandidateSkills[0]="nonexistent-skill" | .inactiveSkills[0]="nonexistent-skill"' requested-pr-review execution-requested-compact
tamper_rejected activated-not-candidate "$compact" '.activatedSkills += [{id:"undeclared-specialist",reason:"baseline",activationSignal:null,modelTier:"full",riskLevel:"high",executionMode:"read",delegationGroup:"security",parallelSafe:true}]' requested-pr-review execution-requested-compact
tamper_rejected invented-signal-activation "$architecture_active" '.staticallyActivatedSkills[0].signal="invented_signal" | .activatedSkills |= map(if .id=="architecture-risk" then .activationSignal="invented_signal" else . end)' requested-pr-review execution-architecture --static-signal architecture_boundary_change
tamper_rejected wrong-signal-skill "$high" '.staticallyActivatedSkills[0].signal="architecture_boundary_change" | .activatedSkills |= map(if .id=="liquibase-production-risk" then .activationSignal="architecture_boundary_change" else . end)' requested-pr-review execution-high --static-signal migration_or_schema_change
tamper_rejected invented-reason "$compact" '.activatedSkills |= map(if .id=="changed-files-risk-classifier" then .reason="static-signal" | .activationSignal="invented_signal" else . end) | .staticallyActivatedSkills += [{signal:"invented_signal",skill:"changed-files-risk-classifier"}]' requested-pr-review execution-requested-compact
tamper_rejected economy-to-full "$economy" '.activatedSkills |= map(if .id=="acceptance-criteria-testability" then .modelTier="full" else . end) | .modelEscalationSkills += ["acceptance-criteria-testability"]' story-start execution-economy
tamper_rejected full-to-economy "$high" '.activatedSkills |= map(if .id=="liquibase-production-risk" then .modelTier="economy" else . end)' requested-pr-review execution-high --static-signal migration_or_schema_change
tamper_rejected risk-low-to-high "$compact" '.activatedSkills |= map(if .id=="changed-files-risk-classifier" then .riskLevel="high" else . end) | .modelEscalationSkills += ["changed-files-risk-classifier"]' requested-pr-review execution-requested-compact
tamper_rejected risk-high-to-low "$high" '.activatedSkills |= map(if .id=="liquibase-production-risk" then .riskLevel="low" else . end)' requested-pr-review execution-high --static-signal migration_or_schema_change
tamper_rejected execution-read-to-write "$high" '.activatedSkills |= map(if .id=="liquibase-production-risk" then .executionMode="write" else . end) | .writePermissionRequirements += ["liquibase-production-risk"]' requested-pr-review execution-high --static-signal migration_or_schema_change
tamper_rejected delegation-group "$high" '.activatedSkills |= map(if .id=="liquibase-production-risk" then .delegationGroup="security" else . end)' requested-pr-review execution-high --static-signal migration_or_schema_change
tamper_rejected parallel-safety "$high" '.activatedSkills |= map(if .id=="liquibase-production-risk" then .parallelSafe=false else . end)' requested-pr-review execution-high --static-signal migration_or_schema_change
tamper_rejected artifact-added "$compact" '.requiredArtifacts += ["arbitrary-report.md"]' requested-pr-review execution-requested-compact
tamper_rejected artifact-removed "$compact" '.requiredArtifacts = .requiredArtifacts[1:]' requested-pr-review execution-requested-compact
tamper_rejected semantic-agent-added "$compact" '.semanticAgents += ["bug-hunter-agent"]' requested-pr-review execution-requested-compact
tamper_rejected semantic-agent-removed "$compact" '.semanticAgents=[]' requested-pr-review execution-requested-compact
tamper_rejected baseline-to-inactive "$compact" '.baselineSkills -= ["changed-files-risk-classifier"] | (.activatedSkills |= map(select(.id!="changed-files-risk-classifier"))) | .inactiveSkills += ["changed-files-risk-classifier"] | (.inactiveSkills |= sort)' requested-pr-review execution-requested-compact
tamper_rejected inactive-to-baseline "$architecture_active" '.staticallyActivatedSkills=[] | .baselineSkills += ["architecture-risk"] | .activatedSkills |= map(if .id=="architecture-risk" then .reason="baseline" | .activationSignal=null else . end)' requested-pr-review execution-architecture --static-signal architecture_boundary_change
tamper_rejected duplicate-active "$compact" '.activatedSkills += [.activatedSkills[0]]' requested-pr-review execution-requested-compact
tamper_rejected fallback-on-modern "$compact" '.activationMode="legacy-fallback"' requested-pr-review execution-requested-compact
tamper_rejected declarative-on-legacy "$legacy" '.activationMode="declarative" | .warnings=[]' architecture-review execution-legacy
tamper_rejected invented-conditional-map "$compact" '.availableConditionalSkills[0].signal="invented_signal"' requested-pr-review execution-requested-compact
tamper_rejected inactive-deep-load-authoritative "$compact" '.deepLoadedSkills += [{id:"liquibase-production-risk",instructionPath:"skills/liquibase-production-risk/SKILL.md"}]' requested-pr-review execution-requested-compact

# A genuine manifest is accepted by the same authoritative boundary.
auth_validate "$compact" requested-pr-review execution-requested-compact || fail 'genuine framework manifest was rejected'

# skill_activation parsing is tri-state. Only an absent key enters legacy;
# every present malformed or ambiguous block is a hard failure with no JSON.
fixture_root="$tmp/framework root with spaces"
mkdir -p "$fixture_root/profiles"
ln -s "$root/skills" "$fixture_root/skills"
ln -s "$root/agents" "$fixture_root/agents"
write_fixture_profile() {
  local activation="$1"
  {
    printf '%s\n' 'name: fixture-profile' 'agents:' '  - requested-pr-review-agent' 'skills:' '  - changed-files-risk-classifier' '  - architecture-risk'
    [ -z "$activation" ] || printf '%b\n' "$activation"
  } > "$fixture_root/profiles/fixture-profile.yaml"
}
fixture_compile() {
  python3 "$root/scripts/lib/context-runtime.py" compile-context-manifest \
    "$fixture_root" fixture-profile execution-fixture
}

write_fixture_profile ''
fixture_compile > "$tmp/fixture-legacy.json" 2> "$tmp/fixture-legacy.err" || fail 'absent activation key did not enter legacy fallback'
jq -e '.activationMode=="legacy-fallback" and (.warnings|length)==1' "$tmp/fixture-legacy.json" >/dev/null || fail 'legacy manifest warning missing'
grep -Fxq 'WARNING: Legacy activation fallback: profile has no skill_activation block; all candidate skills are active until migration.' "$tmp/fixture-legacy.err" || fail 'legacy stderr warning is missing or nondeterministic'

malformed_blocks=(
  'skill_activation: malformed'
  $'skill_activation:\n  baseline: changed-files-risk-classifier\n  conditional:\n    architecture_boundary_change: architecture-risk'
  $'skill_activation:\n  baseline:\n    - changed-files-risk-classifier\n  conditional: malformed'
  $'skill_activation:\n  baseline:\n    changed-files-risk-classifier\n  conditional:\n    architecture_boundary_change: architecture-risk'
  $'skill_activation:\n  baseline:\n    - changed-files-risk-classifier\n  conditional:\n    : architecture-risk'
  $'skill_activation:\n  baseline:\n    - changed-files-risk-classifier\n  conditional:\n    architecture_boundary_change:'
  $'skill_activation:\n  baseline:\n    - changed-files-risk-classifier\n  conditional:\n    architecture_boundary_change: architecture-risk\n    architecture_boundary_change: architecture-risk'
  $'skill_activation:\n  baseline:\n    - changed-files-risk-classifier\n    - architecture-risk\n  conditional:\n    architecture_boundary_change: architecture-risk'
  $'skill_activation:\n  baseline:\n    - changed-files-risk-classifier\n  conditional:\n    architecture_boundary_change: architecture-risk\n  unknown: value'
  $'skill_activation:\n  baseline:\n    - changed-files-risk-classifier'
  $'skill_activation:\n  baseline:\n    - changed-files-risk-classifier\n  conditional:\n    signal_one: architecture-risk\n    signal_two: architecture-risk'
)
malformed_index=0
for malformed in "${malformed_blocks[@]}"; do
  malformed_index=$((malformed_index + 1))
  write_fixture_profile "$malformed"
  if fixture_compile > "$tmp/malformed-$malformed_index.out" 2> "$tmp/malformed-$malformed_index.err"; then
    fail "malformed modern activation case $malformed_index fell back to legacy"
  fi
  [ ! -s "$tmp/malformed-$malformed_index.out" ] || fail "malformed modern activation case $malformed_index emitted a manifest"
  ! grep -Fq 'Legacy activation fallback' "$tmp/malformed-$malformed_index.err" || fail "malformed modern activation case $malformed_index emitted a fallback warning"
done

# Canonical bytes do not depend on locale, and canonical values contain no
# timestamp/random identity beyond the explicit execution id.
LC_ALL=C "$compiler" requested-pr-review --execution-id execution-locale > "$tmp/locale-c.json"
available_locale="$(locale -a 2>/dev/null | awk 'tolower($0) ~ /^c\.utf-?8$/ && !found {print; found=1}')"
if [ -n "$available_locale" ]; then
  LC_ALL="$available_locale" "$compiler" requested-pr-review --execution-id execution-locale > "$tmp/locale-utf8.json"
  cmp -s "$tmp/locale-c.json" "$tmp/locale-utf8.json" || fail 'canonical JSON differs across available C locales'
fi
jq -e '(has("timestamp")|not) and (has("generatedAt")|not) and (has("randomId")|not)' "$tmp/locale-c.json" >/dev/null || fail 'compiled manifest contains nondeterministic fields'

# An active write skill reports a permission requirement, but the model-owned
# manifest has no authority field and therefore cannot grant repository writes.
write_manifest="$tmp/write-profile.json"
"$compiler" api-test-validation --execution-id execution-write-profile > "$write_manifest"
jq -e '
  (.writePermissionRequirements | length) > 0 and
  ([.activatedSkills[] | select(.executionMode == "write")] | length) > 0 and
  (has("permissions") | not) and (has("repositoryWrite") | not) and
  (has("effectivePermissions") | not)
' "$write_manifest" >/dev/null || fail 'write-skill activation created authority or omitted its permission requirement'

# Explicit run-directory publication uses the CTX-03 contained writer and
# works with spaces. Merely naming a project root remains read-only.
project="$tmp/project with spaces"
mkdir -p "$project"
"$compiler" requested-pr-review --execution-id execution-read-only --project-root "$project" > /dev/null
[ ! -e "$project/.mana" ] || fail 'compiler created project state without an explicit run directory'
written="$("$compiler" requested-pr-review --execution-id execution-written --project-root "$project" --run-directory '.mana/runtime/runs/execution-written')"
expected="$project/.mana/runtime/runs/execution-written/context-manifest-v1.json"
[ "$written" = "$expected" ] || fail "compiler returned unexpected manifest path: $written"
[ -f "$expected" ] || fail 'compiled manifest was not written under the explicit run directory'
"$validator" validate-model context-manifest "$expected" || fail 'published manifest failed validation'
mode="$(stat -f '%Lp' "$expected" 2>/dev/null || stat -c '%a' "$expected")"
[ "$mode" = 600 ] || fail 'published manifest permissions are not restrictive'
rejects "$compiler" requested-pr-review --execution-id execution-unsafe --project-root "$project" --run-directory '../outside'

if rg -n '^[[:space:]]*(codex|claude|opencode|curl|wget|gh)([[:space:]]|$)' "$compiler" >/dev/null; then
  fail 'profile compiler contains a provider or network invocation'
fi

echo "Context Runtime CTX-04 profile compiler tests passed ($profile_count profile activation graphs; deterministic, zero-token)"
