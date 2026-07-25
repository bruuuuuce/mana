#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-runtime.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"; mkdir -p "$project/.mana/global" "$tmp/bin"
for file in service-mission.md architecture.md engineering-guards.md integration-map.md database-policy.md testing-policy.md; do printf 'context\n' > "$project/.mana/global/$file"; done
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$tmp/bin/codex"; chmod +x "$tmp/bin/codex"
fail() { echo "FAIL: $*" >&2; exit 1; }

PATH="$tmp/bin:$PATH" MANA_UPDATE_CHECK=off "$root/scripts/cast.sh" --project-root "$project" mana-help --json > "$tmp/result.json" || fail 'cast failed'
events="$(find "$project/.mana/runtime/events" -name '*.jsonl' -type f | head -n 1)"
[ -n "$events" ] || fail 'events file missing'
grep -Fq '"schemaVersion":"1"' "$events" || fail 'schema version missing'
for field in eventId timestamp sessionId executionId profileId eventType componentType componentId status attributes evidenceReferences; do grep -Fq "\"$field\"" "$events" || fail "event field missing: $field"; done
grep -Fq '"eventType":"profile.started"' "$events" || fail 'start event missing'
grep -Fq '"eventType":"skill.selected"' "$events" || fail 'skill event missing'
grep -Fq '"eventType":"model.selected"' "$events" || fail 'model event missing'
grep -Fq '"eventType":"profile.completed"' "$events" || fail 'completion event missing'
! grep -Eqi '"(prompt|response|chainOfThought|environment|token)"' "$events" || fail 'private field present'
execution="$(basename "$events" .jsonl)"
one="$("$root/scripts/mana-runtime.sh" --project-root "$project" events "$execution" --json)"
two="$("$root/scripts/mana-runtime.sh" --project-root "$project" events "$execution" --json)"
[ "$one" = "$two" ] || fail 'runtime JSON is not stable'
printf '%s\n' "$one" | grep -Fq '"executionId"' || fail 'events JSON missing execution id'
"$root/scripts/mana-runtime.sh" --project-root "$project" prune --dry-run --retain-days 0 --json | grep -Fq '"dryRun":true' || fail 'retention dry run failed'

# Concurrent appends use one execution-local lock and leave one complete line per event.
. "$root/scripts/lib/runtime-events.sh"
runtime_init "$project" concurrent || fail 'runtime init failed'
for n in 1 2 3 4; do (runtime_emit tool.blocked tool "tool-$n" blocked "reason=allowlist" "" true) & done
wait
concurrent="$project/.mana/runtime/events/$MANA_RUNTIME_EXECUTION_ID.jsonl"
[ "$(wc -l < "$concurrent" | tr -d ' ')" = 4 ] || fail 'concurrent event write lost events'
 [ "$(awk -F'"' '/eventId/ { print $4 }' "$concurrent" | sort -u | wc -l | tr -d ' ')" = 4 ] || fail 'concurrent event IDs are not unique'
runtime_emit tool.invoked tool safe completed "apiToken=top-secret" "" false
grep -Fq '[REDACTED]' "$concurrent" || fail 'secret redaction missing'
runtime_init /dev/null unavailable >/dev/null 2>&1 && fail 'storage failure was accepted'
[ -n "$MANA_RUNTIME_WARNING" ] || fail 'storage failure did not surface a warning'

missing="$tmp/missing"; mkdir -p "$missing/.mana/global"
if PATH="$tmp/bin:$PATH" MANA_UPDATE_CHECK=off "$root/scripts/cast.sh" --project-root "$missing" mana-help --json > /dev/null 2>&1; then fail 'incomplete context cast succeeded'; fi
[ ! -e "$missing/.mana/runtime" ] || fail 'preflight failure wrote runtime telemetry'
echo 'Runtime event tests passed'
