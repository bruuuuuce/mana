#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-model-resolution.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
resolver="$root/scripts/mana-models.py"
fixtures="$root/tests/fixtures/model-resolution"
fail() { echo "FAIL: $*" >&2; exit 1; }

python3 "$resolver" doctor --provider codex --tier economy --effort medium --fixture "$fixtures/codex-new-default.json" --json > "$tmp/economy.json"
jq -e '.schemaVersion == "mana.model-resolution/v1" and .selectedModel == "provider-new-default" and .availability == "available" and .confidence == "verified"' "$tmp/economy.json" >/dev/null || fail 'new provider default was not selected'
if grep -q 'old-model' "$tmp/economy.json"; then fail 'resolver retained an obsolete hardcoded model'; fi

python3 "$resolver" doctor --provider codex --tier full --effort high --fixture "$fixtures/codex-new-default.json" --json > "$tmp/full.json" && fail 'unrated full tier was accepted'
jq -e '.selectedModel == null and .availability == "blocked" and (.selectionReason | contains("refusing downgrade"))' "$tmp/full.json" >/dev/null || fail 'full-tier discovery failure did not block safely'

python3 "$resolver" doctor --provider codex --tier standard --model provider-new-default --fixture "$fixtures/codex-new-default.json" --json > "$tmp/pinned.json"
jq -e '.selectedModel == "provider-new-default" and .explicitOverride == "provider-new-default"' "$tmp/pinned.json" >/dev/null || fail 'explicit pin did not take precedence'
MANA_CODEX_MODEL=retired-model python3 "$resolver" doctor --provider codex --tier standard --model provider-new-default --fixture "$fixtures/codex-new-default.json" --json > "$tmp/pinned-env.json"
jq -e '.selectedModel == "provider-new-default" and .explicitOverride == "provider-new-default"' "$tmp/pinned-env.json" >/dev/null || fail 'CLI pin did not take precedence over environment pin'
MANA_CODEX_MODEL=retired-model python3 "$resolver" doctor --provider codex --tier standard --fixture "$fixtures/codex-new-default.json" --json > "$tmp/env-pin.json" && fail 'unavailable environment pin was substituted'
jq -e '.selectedModel == null and .explicitOverride == "retired-model" and .availability == "unavailable"' "$tmp/env-pin.json" >/dev/null || fail 'environment pin was not preserved'

python3 "$resolver" doctor --provider codex --tier economy --model retired-model --fixture "$fixtures/codex-new-default.json" --json > "$tmp/unavailable.json" && fail 'unavailable explicit pin was accepted'
jq -e '.selectedModel == null and .availability == "unavailable" and .explicitOverride == "retired-model"' "$tmp/unavailable.json" >/dev/null || fail 'unavailable explicit pin was substituted'

python3 "$resolver" doctor --provider codex --tier full --effort high --model provider-newer-unrated --fixture "$fixtures/codex-new-default.json" --json > "$tmp/pinned-full.json" && fail 'full-tier pin without capability evidence was accepted'
jq -e '.selectedModel == "provider-newer-unrated" and .invocationCompatibility == "unknown"' "$tmp/pinned-full.json" >/dev/null || fail 'full-tier pin capability uncertainty was lost'

python3 "$resolver" doctor --provider codex --tier economy --effort high --model provider-new-default --fixture "$fixtures/codex-new-default.json" --json > "$tmp/effort.json" && fail 'unsupported reasoning effort was accepted'
jq -e '.selectedModel == "provider-new-default" and .availability == "blocked" and .invocationCompatibility == "incompatible"' "$tmp/effort.json" >/dev/null || fail 'unsupported effort was not blocked safely'

if python3 "$resolver" doctor --provider claude --tier full --json > "$tmp/claude.json"; then fail 'Claude opus alias was treated as full-tier proof'; fi
jq -e '.selectedModel == "opus" and .confidence == "assumed" and .availability == "unknown" and .invocationCompatibility == "unknown"' "$tmp/claude.json" >/dev/null || fail 'Claude alias certainty was overstated'
python3 "$resolver" doctor --provider claude --tier economy --effort medium --json > "$tmp/claude-effort.json"
jq -e '.selectedModel == "haiku" and .reasoningEffort == "medium" and (.supportedReasoningEfforts | index("medium")) and .invocationCompatibility == "compatible"' "$tmp/claude-effort.json" >/dev/null || fail 'Claude CLI effort was not resolved as a supported invocation setting'
python3 "$resolver" doctor --provider claude --tier economy --effort minimal --json > "$tmp/claude-invalid-effort.json" && fail 'unsupported Claude effort level was accepted'
jq -e '.availability == "blocked" and .invocationCompatibility == "incompatible"' "$tmp/claude-invalid-effort.json" >/dev/null || fail 'unsupported Claude effort did not block safely'
if MANA_CLAUDE_BIN=mana-claude-missing python3 "$resolver" doctor --provider claude --tier economy --json > "$tmp/claude-missing-cli.json"; then fail 'Claude alias was selected without an installed CLI'; fi
jq -e '.selectedModel == null and .availability == "blocked" and (.fallbackReason | contains("CLI is not installed"))' "$tmp/claude-missing-cli.json" >/dev/null || fail 'missing Claude CLI was not reported as unavailable'

python3 "$resolver" doctor --provider opencode --tier economy --fixture "$fixtures/opencode-models.json" --json > "$tmp/opencode.json"
jq -e '.selectedModel == "provider/example-model" and .availability == "available"' "$tmp/opencode.json" >/dev/null || fail 'OpenCode project default was not resolved'
python3 "$resolver" doctor --provider opencode --tier economy --effort high --fixture "$fixtures/opencode-models.json" --json > "$tmp/opencode-variant.json"
jq -e '.selectedModel == "provider/example-model" and .selectedVariant == "high" and .invocationCompatibility == "compatible"' "$tmp/opencode-variant.json" >/dev/null || fail 'OpenCode advertised variant was not selected'
python3 "$resolver" doctor --provider opencode --tier economy --effort low --fixture "$fixtures/opencode-models.json" --json > "$tmp/opencode-unsupported.json" && fail 'OpenCode unsupported effort was accepted'
jq -e '.availability == "blocked" and .invocationCompatibility == "incompatible"' "$tmp/opencode-unsupported.json" >/dev/null || fail 'OpenCode unsupported effort was not blocked'

python3 "$resolver" doctor --provider opencode --tier full --fixture "$fixtures/opencode-models.json" --json > "$tmp/opencode-full.json" && fail 'OpenCode model listing was treated as full-tier proof'
jq -e '.selectedModel == "provider/example-model" and .availability == "available" and .invocationCompatibility == "unknown" and .discoverySource == "fixture:opencode-models.json"' "$tmp/opencode-full.json" >/dev/null || fail 'OpenCode full-tier uncertainty was not retained'

python3 "$resolver" doctor --provider opencode --tier economy --model provider/example-model --fixture "$fixtures/opencode-models.json" --json > "$tmp/opencode-pinned.json"
jq -e '.selectedModel == "provider/example-model" and .availability == "available"' "$tmp/opencode-pinned.json" >/dev/null || fail 'OpenCode full provider/model identity was not preserved'
python3 - "$root" "$fixtures/opencode-models-cli.txt" <<'PY'
import importlib.util, json, pathlib, sys
sys.dont_write_bytecode = True
root, fixture = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("mana_models", root / "scripts/mana-models.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
records = module.parse_opencode_catalog(fixture.read_text())
assert len(records) == 1 and records[0]["model"] == "provider/example-model"
assert records[0]["supportedReasoningEfforts"] == [{"reasoningEffort": "high"}]
PY

python3 "$resolver" doctor --provider junie --tier economy --fixture "$fixtures/junie-models.json" --json > "$tmp/junie.json"
jq -e '.selectedModel == "Default" and .confidence == "assumed" and .invocationCompatibility == "compatible"' "$tmp/junie.json" >/dev/null || fail 'Junie dynamic Default alias was not recognized'
python3 "$resolver" doctor --provider junie --tier full --fixture "$fixtures/junie-models.json" --json > "$tmp/junie-full.json" && fail 'Junie full tier was treated as verified'
jq -e '.selectedModel == null and .confidence == "assumed" and .availability == "blocked" and .invocationCompatibility == "unknown" and .executionSupport == "unsupported"' "$tmp/junie-full.json" >/dev/null || fail 'Junie full-tier uncertainty or unsupported execution was hidden'
python3 "$resolver" doctor --provider junie --tier economy --model custom:local-coder --fixture "$fixtures/junie-models.json" --json > "$tmp/junie-custom.json"
jq -e '.selectedModel == "custom:local-coder" and .explicitOverride == "custom:local-coder"' "$tmp/junie-custom.json" >/dev/null || fail 'Junie custom model profile identity was not preserved'
JUNIE_MODEL=opus python3 "$resolver" doctor --provider junie --tier standard --fixture "$fixtures/junie-models.json" --json > "$tmp/junie-env-pin.json"
jq -e '.selectedModel == "opus" and .explicitOverride == "opus"' "$tmp/junie-env-pin.json" >/dev/null || fail 'Junie provider-native environment pin was ignored'

python3 "$resolver" doctor --provider codex --tier economy --fixture "$fixtures/missing-catalog.json" --json > "$tmp/failure.json" && fail 'missing catalog was accepted'
jq -e '.selectedModel == null and .availability == "blocked" and .confidence == "unknown"' "$tmp/failure.json" >/dev/null || fail 'catalog failure was not differentiated'

mkdir -p "$tmp/bin"
cat > "$tmp/bin/codex" <<'STUB'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then echo 'codex fixture 1'; exit 0; fi
if [ "${1:-}" = "app-server" ]; then
  while IFS= read -r request; do
    method="$(jq -r '.method // empty' <<<"$request")"
    request_id="$(jq -r '.id // empty' <<<"$request")"
    if [ "$method" = "initialize" ]; then
      printf '{"method":"account/updated","params":{}}\n{"id":%s,"result":{}}\n' "$request_id"
    fi
    if [ "$method" = "account/gatewayOAuth/read" ]; then printf '{"id":%s,"result":{"required":false,"status":null}}\n' "$request_id"; fi
    if [ "$method" = "model/list" ]; then printf '{"id":%s,"error":{"code":-32601,"message":"unsupported"}}\n' "$request_id"; fi
  done
  exit 0
fi
exit 1
STUB
chmod +x "$tmp/bin/codex"
MANA_CODEX_BIN="$tmp/bin/codex" python3 "$resolver" doctor --provider codex --tier economy --json > "$tmp/codex-default.json"
jq -e '.selectedModel == null and .availability == "unknown" and .invocationCompatibility == "compatible" and (.discoverySource | contains("provider-owned-default"))' "$tmp/codex-default.json" >/dev/null || fail 'Codex CLI default fallback was not represented truthfully'
if MANA_CODEX_BIN="$tmp/bin/codex" python3 "$resolver" doctor --provider codex --tier economy --effort high --json > "$tmp/codex-effort.json"; then fail 'Codex default fallback ignored unverified effort'; fi
jq -e '.invocationCompatibility == "unknown" and .selectedModel == null' "$tmp/codex-effort.json" >/dev/null || fail 'Codex effort uncertainty was lost during fallback'

cat > "$tmp/bin/codex-auth-rejected" <<'STUB'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then echo 'codex fixture 1'; exit 0; fi
if [ "${1:-}" = "app-server" ]; then
  while IFS= read -r request; do
    method="$(jq -r '.method // empty' <<<"$request")"
    request_id="$(jq -r '.id // empty' <<<"$request")"
    case "$method" in
      initialize) printf '{"id":%s,"result":{}}\n' "$request_id" ;;
      account/gatewayOAuth/read) printf '{"id":%s,"result":{"required":false,"status":null}}\n' "$request_id" ;;
      model/list) printf '{"id":%s,"error":{"code":401,"message":"unauthorized"}}\n' "$request_id" ;;
    esac
  done
  exit 0
fi
printf 'provider invocation must not happen after catalog authentication rejection\n' >> "$MANA_MODEL_AUTH_INVOKED"
exit 9
STUB
chmod +x "$tmp/bin/codex-auth-rejected"
if MANA_CODEX_BIN="$tmp/bin/codex-auth-rejected" MANA_MODEL_AUTH_INVOKED="$tmp/auth-invoked" \
    python3 "$resolver" doctor --provider codex --tier economy --json > "$tmp/auth-rejected.json"; then
  fail 'Codex catalog authentication rejection was treated as a provider-default fallback'
fi
jq -e '.availability == "blocked" and (.fallbackReason | contains("authentication or entitlement was rejected"))' "$tmp/auth-rejected.json" >/dev/null || fail 'authentication rejection diagnostic was not distinguished'
[ ! -e "$tmp/auth-invoked" ] || fail 'provider invocation occurred after discovery authentication rejection'

cat > "$tmp/bin/codex-gateway-pending" <<'STUB'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then echo 'codex fixture 1'; exit 0; fi
if [ "${1:-}" = "app-server" ]; then
  while IFS= read -r request; do
    method="$(jq -r '.method // empty' <<<"$request")"
    request_id="$(jq -r '.id // empty' <<<"$request")"
    case "$method" in
      initialize) printf '{"id":%s,"result":{}}\n' "$request_id" ;;
      account/gatewayOAuth/read) printf '{"id":%s,"result":{"required":true,"status":"notReady"}}\n' "$request_id" ;;
      model/list) printf 'catalog query must not follow an unready gateway auth check\n' >> "$MANA_GATEWAY_CATALOG_INVOKED" ;;
    esac
  done
  exit 0
fi
printf 'provider invocation must not happen before gateway authentication is ready\n' >> "$MANA_GATEWAY_PROVIDER_INVOKED"
exit 9
STUB
chmod +x "$tmp/bin/codex-gateway-pending"
if MANA_CODEX_BIN="$tmp/bin/codex-gateway-pending" MANA_GATEWAY_CATALOG_INVOKED="$tmp/gateway-catalog-invoked" MANA_GATEWAY_PROVIDER_INVOKED="$tmp/gateway-provider-invoked" \
    python3 "$resolver" doctor --provider codex --tier economy --json > "$tmp/gateway-pending.json"; then
  fail 'Codex discovery proceeded without ready gateway credentials'
fi
jq -e '.availability == "blocked" and (.fallbackReason | contains("gateway authentication is required"))' "$tmp/gateway-pending.json" >/dev/null || fail 'gateway-auth readiness failure was not reported'
[ ! -e "$tmp/gateway-catalog-invoked" ] || fail 'model catalog was queried before gateway auth readiness'
[ ! -e "$tmp/gateway-provider-invoked" ] || fail 'provider was invoked before gateway auth readiness'

for result in "$tmp"/*.json; do
  python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/model-resolution-v1.schema.json" "$result" ||
    fail "model-resolution result violates schema: $(basename "$result")"
done

echo 'Model resolution tests passed'
