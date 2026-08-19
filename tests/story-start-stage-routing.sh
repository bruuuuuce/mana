#!/usr/bin/env bash
# TG01 zero-token routing and transport coverage.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-stage-routing.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-stage-routing.sh"

assert_route() {
  local provider="$1" stage="$2" root_model="$3" root_effort="$4" root_model_explicit="$5" root_effort_explicit="$6" cli_model="$7" cli_effort="$8" expected_model="$9" expected_effort="${10}" expected_model_source="${11}" expected_effort_source="${12}" expected_dispatch="${13}"
  mana_story_start_stage_resolve "$provider" "$stage" "$root_model" "$root_effort" "$root_model_explicit" "$root_effort_explicit" "$cli_model" "$cli_effort" || fail "route resolution failed: $provider/$stage"
  [ "$MANA_STORY_START_ROUTE_MODEL" = "$expected_model" ] || fail "$provider/$stage model: expected $expected_model, got $MANA_STORY_START_ROUTE_MODEL"
  [ "$MANA_STORY_START_ROUTE_EFFORT" = "$expected_effort" ] || fail "$provider/$stage effort: expected $expected_effort, got $MANA_STORY_START_ROUTE_EFFORT"
  [ "$MANA_STORY_START_ROUTE_MODEL_SOURCE" = "$expected_model_source" ] || fail "$provider/$stage model source changed"
  [ "$MANA_STORY_START_ROUTE_EFFORT_SOURCE" = "$expected_effort_source" ] || fail "$provider/$stage effort source changed"
  [ "$MANA_STORY_START_ROUTE_EFFORT_DISPATCH" = "$expected_dispatch" ] || fail "$provider/$stage effort dispatch changed"
}

unset MANA_CODEX_STORY_START_DISCOVERY_MODEL MANA_CODEX_STORY_START_DISCOVERY_EFFORT
unset MANA_CODEX_STORY_START_TRIAGE_MODEL MANA_CODEX_STORY_START_TRIAGE_EFFORT
unset MANA_CODEX_STORY_START_PLANNER_MODEL MANA_CODEX_STORY_START_PLANNER_EFFORT
unset MANA_CODEX_STORY_START_CORRECTION_MODEL MANA_CODEX_STORY_START_CORRECTION_EFFORT
unset MANA_CODEX_STORY_START_TRAJECTORY_CHECKPOINT_MODEL MANA_CODEX_STORY_START_TRAJECTORY_CHECKPOINT_EFFORT

# Provider-stage defaults are explicit for all required routes.
assert_route codex discovery gpt-5.4-mini '' false false '' '' gpt-5.6-terra high provider-stage-default provider-stage-default explicit
assert_route codex triage gpt-5.4-mini '' false false '' '' gpt-5.6-sol xhigh provider-stage-default provider-stage-default explicit
assert_route codex planner gpt-5.4-mini '' false false '' '' gpt-5.6-sol high provider-stage-default provider-stage-default explicit
assert_route codex correction gpt-5.4-mini '' false false '' '' gpt-5.6-terra high provider-stage-default provider-stage-default explicit
assert_route codex trajectory-checkpoint gpt-5.4-mini '' false false '' '' gpt-5.6-terra high provider-stage-default provider-stage-default explicit

# Stage environment and CLI overrides supersede explicit root compatibility values.
MANA_CODEX_STORY_START_DISCOVERY_MODEL=environment-discovery \
MANA_CODEX_STORY_START_DISCOVERY_EFFORT=medium \
  assert_route codex discovery root-compat low true true '' '' environment-discovery medium stage-environment stage-environment explicit
assert_route codex triage root-compat low true true cli-triage xhigh cli-triage xhigh stage-cli stage-cli explicit
assert_route codex planner root-compat medium true true '' '' root-compat medium root-compatibility-override root-compatibility-override explicit

# Unsupported adapters retain the requested effort as diagnostics only.
assert_route claude triage haiku '' false false '' '' opus xhigh provider-stage-default provider-stage-default unsupported
assert_route opencode correction opencode/root '' false false '' '' opencode/gpt-5.1-codex high provider-stage-default provider-stage-default unsupported
MANA_CODEX_STORY_START_DISCOVERY_EFFORT=unknown \
  mana_story_start_stage_resolve codex discovery root '' false false '' '' && fail 'invalid stage effort was accepted'

# The shared isolated dispatch sends Codex effort through ignore-user-config.
mana_provider_synthesis_args codex "$tmp/empty" route-model host-disposable-non-git "$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json" high
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/codex-dispatch.args"
grep -Fxq 'model_reasoning_effort="high"' "$tmp/codex-dispatch.args" || fail 'Codex effort was not forwarded explicitly'

# A public v2 run uses per-stage CLI routes, emits sanitized diagnostics, and
# resolves the future checkpoint route without invoking it.
mkdir -p "$tmp/bin" "$tmp/project"
cp "$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json" "$tmp/project/story-context.json"
cat > "$tmp/bin/codex" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' 'CALL' >> "$TG01_CODEX_ARGS"
printf '%s\n' "$@" >> "$TG01_CODEX_ARGS"
last=""
for argument in "$@"; do last="$argument"; done
case "$last" in
  *COMPACT_DISCOVERY_PACKAGE*) cat "$TG01_DISCOVERY_OUTPUT" ;;
  *COMPACT_DISCOVERY_V2*) cat "$TG01_TRIAGE_OUTPUT" ;;
  *INVALID_IMPLEMENTATION_PLAN_V2*) cat "$TG01_CORRECTION_OUTPUT" ;;
  *SCOPE_TRIAGE_V2*) cat "$TG01_PLAN_OUTPUT" ;;
  *) exit 0 ;;
esac
STUB
chmod +x "$tmp/bin/codex"

MANA_UPDATE_CHECK=off \
MANA_STORY_START_SCOPE_VERSION=v2 \
MANA_STORY_START_CONTEXT=story-context.json \
MANA_ROUTING_TEST_SECRET=stage-secret-not-for-output \
TG01_CODEX_ARGS="$tmp/codex.args" \
TG01_DISCOVERY_OUTPUT="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json" \
TG01_TRIAGE_OUTPUT="$root/tests/fixtures/story-start-scope-v2/triage/provider-output.json" \
TG01_PLAN_OUTPUT="$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json" \
PATH="$tmp/bin:$PATH" \
"$root/scripts/run-profile.sh" story-start --project-root "$tmp/project" --codex \
  --story-start-discovery-model cli-discovery --story-start-discovery-effort high \
  --story-start-triage-model cli-triage --story-start-triage-effort xhigh \
  --story-start-planner-model cli-planner --story-start-planner-effort high \
  > "$tmp/v2.out" 2> "$tmp/v2.err"

[ "$(grep -c '^CALL$' "$tmp/codex.args")" = 3 ] || fail 'successful v2 run did not make exactly three calls'
awk '
  /^CALL$/ { call += 1; next }
  $0 == "--model" { getline; print call ":" $0 }
' "$tmp/codex.args" > "$tmp/models.tsv"
cmp -s "$tmp/models.tsv" <(printf '%s\n' '1:cli-discovery' '2:cli-triage' '3:cli-planner') || fail 'stage-specific models were not dispatched in phase order'
grep -Fxq 'model_reasoning_effort="high"' "$tmp/codex.args" || fail 'high effort missing from public stage dispatch'
grep -Fxq 'model_reasoning_effort="xhigh"' "$tmp/codex.args" || fail 'xhigh effort missing from public stage dispatch'
grep -Fq 'stage=correction provider=codex model=gpt-5.6-terra' "$tmp/v2.out" || fail 'correction route diagnostic missing'
grep -Fq 'stage=trajectory-checkpoint provider=codex model=gpt-5.6-terra' "$tmp/v2.out" || fail 'future checkpoint route diagnostic missing'
grep -Fq 'effort_dispatch=explicit' "$tmp/v2.out" || fail 'Codex effort diagnostic is not explicit'
if grep -Fq 'COMPACT_DISCOVERY_PACKAGE' "$tmp/v2.out" || grep -Fq 'COMPACT_DISCOVERY_PACKAGE' "$tmp/v2.err" || grep -Fq 'stage-secret-not-for-output' "$tmp/v2.out" || grep -Fq 'stage-secret-not-for-output' "$tmp/v2.err"; then
  fail 'routing diagnostics leaked a prompt body or secret'
fi

# A governed correction uses its separate model and explicit effort, while the
# future checkpoint still remains uncalled.
jq '(.basePlan[0].title) = "Add configuration channel"' \
  "$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json" > "$tmp/invalid-plan.json"
mkdir -p "$tmp/correction-project"
cp "$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json" "$tmp/correction-project/story-context.json"
MANA_UPDATE_CHECK=off \
MANA_STORY_START_SCOPE_VERSION=v2 \
MANA_STORY_START_CONTEXT=story-context.json \
TG01_CODEX_ARGS="$tmp/correction.args" \
TG01_DISCOVERY_OUTPUT="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json" \
TG01_TRIAGE_OUTPUT="$root/tests/fixtures/story-start-scope-v2/triage/provider-output.json" \
TG01_PLAN_OUTPUT="$tmp/invalid-plan.json" \
TG01_CORRECTION_OUTPUT="$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json" \
PATH="$tmp/bin:$PATH" \
"$root/scripts/run-profile.sh" story-start --project-root "$tmp/correction-project" --codex \
  --story-start-correction-model cli-correction --story-start-correction-effort xhigh \
  > "$tmp/correction.out" 2> "$tmp/correction.err"
[ "$(grep -c '^CALL$' "$tmp/correction.args")" = 4 ] || fail 'correction path did not make three phase calls plus one correction'
awk '
  /^CALL$/ { call += 1; next }
  $0 == "--model" { getline; print call ":" $0 }
' "$tmp/correction.args" > "$tmp/correction-models.tsv"
grep -Fxq '4:cli-correction' "$tmp/correction-models.tsv" || fail 'correction route model was not dispatched'
grep -Fxq 'model_reasoning_effort="xhigh"' "$tmp/correction.args" || fail 'correction route effort was not dispatched'
grep -Fq 'stage=trajectory-checkpoint provider=codex' "$tmp/correction.out" || fail 'checkpoint route was not resolved during correction path'

# Existing v1 execution still sends only the configured root model.
mkdir -p "$tmp/v1-project"
MANA_UPDATE_CHECK=off TG01_CODEX_ARGS="$tmp/v1.args" PATH="$tmp/bin:$PATH" \
  "$root/scripts/run-profile.sh" mana-help --project-root "$tmp/v1-project" --codex --codex-model v1-root > "$tmp/v1.out" 2> "$tmp/v1.err"
grep -Fxq 'v1-root' "$tmp/v1.args" || fail 'unrelated v1 root routing changed'
[ "$(grep -c '^CALL$' "$tmp/v1.args")" = 1 ] || fail 'unrelated v1 execution changed invocation count'
if grep -Fq 'model_reasoning_effort=' "$tmp/v1.args"; then
  fail 'v1 root invocation unexpectedly received v2 stage effort'
fi

echo 'Story Start Scope v2 stage routing tests passed (zero provider/network calls; fake Codex only)'
