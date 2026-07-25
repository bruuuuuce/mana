#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-cast.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
mkdir -p "$project/.mana/global" "$tmp/bin"

fail() { echo "FAIL: $*" >&2; exit 1; }
for file in service-mission.md architecture.md engineering-guards.md integration-map.md database-policy.md testing-policy.md; do
  printf 'test context\n' > "$project/.mana/global/$file"
done
run() { MANA_UPDATE_CHECK=off "$root/scripts/cast.sh" --project-root "$project" "$@"; }

before="$(find "$project/.mana" -type f -exec cksum {} + | sort)"
dry="$(run mana-help --dry-run)" || fail 'dry run failed'
printf '%s\n' "$dry" | grep -Fq 'MANA CAST DRY RUN' || fail 'dry-run heading'
printf '%s\n' "$dry" | grep -Fq 'mana-help-agent' || fail 'semantic agents missing'
printf '%s\n' "$dry" | grep -Fq 'Selected skills:' || fail 'skills missing'
printf '%s\n' "$dry" | grep -Fq 'No runner, tool, hook, build, test, or filesystem mutation has occurred.' || fail 'dry-run confirmation'
after="$(find "$project/.mana" -type f -exec cksum {} + | sort)"
[ "$before" = "$after" ] || fail 'dry run mutated workspace'

gated="$(run architecture-review --dry-run)" || fail 'gated dry run failed'
printf '%s\n' "$gated" | grep -Fq 'profile requires human approval for its governed decision; casting does not satisfy it' || fail 'human gate missing'

missing="$tmp/missing"
mkdir -p "$missing/.mana/global"
if MANA_UPDATE_CHECK=off "$root/scripts/cast.sh" --project-root "$missing" mana-help --dry-run >"$tmp/missing.out" 2>&1; then fail 'missing context accepted'; fi
grep -Fq 'Service Context is incomplete' "$tmp/missing.out" || fail 'missing context diagnostic'

if run does-not-exist --dry-run >"$tmp/invalid.out" 2>&1; then fail 'invalid profile accepted'; fi
grep -Fq 'profile not found: does-not-exist' "$tmp/invalid.out" || fail 'invalid profile diagnostic'

printf '%s\n' '#!/usr/bin/env bash' 'printf "mock codex invoked\\n" >&2' > "$tmp/bin/codex"
chmod +x "$tmp/bin/codex"
execution="$(PATH="$tmp/bin:$PATH" MANA_UPDATE_CHECK=off run mana-help --json 2>"$tmp/runner.err")" || fail 'runner execution failed'
printf '%s\n' "$execution" | grep -Fq '"status":"executed"' || fail 'execution JSON status'
grep -Fq 'mock codex invoked' "$tmp/runner.err" || fail 'existing runner did not invoke provider'

fingerprint="$(cksum < "$root/profiles/mana-help.yaml" | awk '{print $1 "-" $2}')"
printf '{"intent":"help","status":"recommended","recommendedProfile":"mana-help","profileFingerprint":"%s","readOnly":true}\n' "$fingerprint" > "$tmp/divination.json"
from="$(run --from "$tmp/divination.json" --dry-run --json)" || fail 'valid divination result rejected'
printf '%s\n' "$from" | grep -Fq '"profile":"mana-help"' || fail 'from result profile'
printf '{"status":"recommended","recommendedProfile":"mana-help","profileFingerprint":"0-0","readOnly":true}\n' > "$tmp/stale.json"
if run --from "$tmp/stale.json" --dry-run >"$tmp/stale.out" 2>&1; then fail 'stale divination accepted'; fi
grep -Fq 'stale divination result' "$tmp/stale.out" || fail 'stale diagnostic'
printf '{not json}\n' > "$tmp/malformed.json"
if run --from "$tmp/malformed.json" --dry-run >"$tmp/malformed.out" 2>&1; then fail 'malformed divination accepted'; fi
grep -Fq 'malformed divination JSON' "$tmp/malformed.out" || fail 'malformed JSON diagnostic'

json_one="$(run mana-help --dry-run --json)"
json_two="$(run mana-help --dry-run --json)"
[ "$json_one" = "$json_two" ] || fail 'JSON is not stable'
if run unknown --dry-run --json >"$tmp/no-substitution.json" 2>&1; then fail 'unknown profile was substituted'; fi
grep -Fq '"profile":"unknown"' "$tmp/no-substitution.json" || fail 'invalid requested profile was not preserved'

echo 'Cast tests passed'
