#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-learning.XXXXXX")"; trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
project="$tmp/project"; events="$project/.mana/runtime/events"; mkdir -p "$events"
cat > "$events/execution-one.jsonl" <<'EOF'
{"eventId":"one-1","timestamp":"2026-07-01T00:00:00Z","executionId":"execution-one","profileId":"demo","eventType":"evidence.missing"}
{"eventId":"one-2","timestamp":"2026-07-01T00:01:00Z","executionId":"execution-one","profileId":"demo","eventType":"profile.completed"}
EOF
cat > "$events/execution-two.jsonl" <<'EOF'
{"eventId":"two-1","timestamp":"2026-07-02T00:00:00Z","executionId":"execution-two","profileId":"demo","eventType":"evidence.missing"}
{"eventId":"two-2","timestamp":"2026-07-02T00:01:00Z","executionId":"execution-two","profileId":"demo","eventType":"guard.triggered"}
EOF
$root/scripts/mana-learning.sh --project-root "$project" collect
list="$($root/scripts/mana-learning.sh --project-root "$project" candidates --json)"; printf '%s' "$list" | grep -Fq '"recurrenceCount":2' || fail 'repeated observation did not aggregate'; printf '%s' "$list" | grep -Fq '"confidence":"medium"' || fail 'deterministic confidence missing'
id="$(printf '%s' "$list" | sed -n 's/.*"candidateId":"\([^"]*\)".*/\1/p' | head -n 1)"; [ -n "$id" ] || fail 'candidate id missing'
$root/scripts/mana-learning.sh --project-root "$project" review "$id" | grep -Fq 'review artifact' || fail 'review artifact not generated'
[ -f "$project/.mana/learning/reviews/$id-review.md" ] || fail 'review missing'
$root/scripts/mana-learning.sh --project-root "$project" show "$id" --json | grep -Fq '"status":"reviewed"' || fail 'review lifecycle missing'
$root/scripts/mana-learning.sh --project-root "$project" reject "$id" >/dev/null
$root/scripts/mana-learning.sh --project-root "$project" show "$id" --json | grep -Fq '"status":"rejected"' || fail 'rejected lifecycle missing'
grep -R -Eqi 'token|secret' "$project/.mana/learning/candidates" && fail 'candidate leaked a secret-bearing field'
echo 'Learning signal tests passed'
