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

# Provider-stage models are resolved from discovery at invocation time.
assert_route codex discovery '' '' false false '' '' '' high provider-discovery provider-stage-default explicit
assert_route codex triage '' '' false false '' '' '' xhigh provider-discovery provider-stage-default explicit
assert_route codex planner '' '' false false '' '' '' high provider-discovery provider-stage-default explicit
assert_route codex correction '' '' false false '' '' '' high provider-discovery provider-stage-default explicit
assert_route codex trajectory-checkpoint '' '' false false '' '' '' high provider-discovery provider-stage-default explicit

# Stage environment and CLI overrides supersede explicit root compatibility values.
MANA_CODEX_STORY_START_DISCOVERY_MODEL=environment-discovery \
MANA_CODEX_STORY_START_DISCOVERY_EFFORT=medium \
  assert_route codex discovery root-compat low true true '' '' environment-discovery medium stage-environment stage-environment explicit
assert_route codex triage root-compat low true true cli-triage xhigh cli-triage xhigh stage-cli stage-cli explicit
assert_route codex planner root-compat medium true true '' '' root-compat medium root-compatibility-override root-compatibility-override explicit

# Unsupported adapters retain the requested effort as diagnostics only.
assert_route claude triage '' '' false false '' '' '' xhigh provider-discovery provider-stage-default unsupported
assert_route claude discovery '' '' false false '' '' '' high provider-discovery provider-stage-default unsupported
assert_route claude planner '' '' false false '' '' '' high provider-discovery provider-stage-default unsupported
assert_route claude correction '' '' false false '' '' '' high provider-discovery provider-stage-default unsupported
assert_route claude trajectory-checkpoint '' '' false false '' '' '' high provider-discovery provider-stage-default unsupported
assert_route opencode discovery '' '' false false '' '' '' high provider-discovery provider-stage-default unsupported
assert_route opencode triage '' '' false false '' '' '' xhigh provider-discovery provider-stage-default unsupported
assert_route opencode planner '' '' false false '' '' '' high provider-discovery provider-stage-default unsupported
assert_route opencode correction '' '' false false '' '' '' high provider-discovery provider-stage-default unsupported
assert_route opencode trajectory-checkpoint '' '' false false '' '' '' high provider-discovery provider-stage-default unsupported
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
if [ "${1:-}" = "--version" ]; then echo 'codex-fixture 1.0'; exit 0; fi
if [ "${1:-}" = app-server ]; then
  while IFS= read -r request; do
    method="$(jq -r '.method // empty' <<<"$request")"
    request_id="$(jq -r '.id // empty' <<<"$request")"
    case "$method" in
      initialize) printf '{"id":%s,"result":{}}\n' "$request_id" ;;
      model/list)
        printf '{"id":%s,"result":{"data":[{"id":"model-catalog-default","model":"model-catalog-default","isDefault":true,"supportedReasoningEfforts":[{"reasoningEffort":"high"},{"reasoningEffort":"xhigh"}]},{"id":"cli-discovery","model":"cli-discovery","supportedReasoningEfforts":[{"reasoningEffort":"high"}]},{"id":"cli-triage","model":"cli-triage","supportedReasoningEfforts":[{"reasoningEffort":"xhigh"}]},{"id":"cli-planner","model":"cli-planner","supportedReasoningEfforts":[{"reasoningEffort":"high"}]},{"id":"cli-correction","model":"cli-correction","supportedReasoningEfforts":[{"reasoningEffort":"xhigh"}]},{"id":"v1-root","model":"v1-root"}]}}\n' "$request_id"
        ;;
    esac
  done
  exit 0
fi
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

if MANA_UPDATE_CHECK=off \
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
  > "$tmp/v2.out" 2> "$tmp/v2.err"; then fail 'v2 run downgraded the unverified full-tier stage'; else code=$?; [ "$code" -eq 2 ] || fail 'full-tier resolution returned an unexpected status'; fi
[ ! -f "$tmp/codex.args" ] || fail 'provider invocation occurred after full-tier resolution was blocked'
grep -Fq 'Story Start triage model resolution is blocked' "$tmp/v2.err" || fail 'full-tier block reason was not reported'
grep -Fq 'does not establish full-tier capability' "$tmp/v2.err" || fail 'full-tier capability gap was not actionable'
if grep -Fq 'COMPACT_DISCOVERY_PACKAGE' "$tmp/v2.out" || grep -Fq 'COMPACT_DISCOVERY_PACKAGE' "$tmp/v2.err" || grep -Fq 'stage-secret-not-for-output' "$tmp/v2.out" || grep -Fq 'stage-secret-not-for-output' "$tmp/v2.err"; then
  fail 'routing diagnostics leaked a prompt body or secret'
fi

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
