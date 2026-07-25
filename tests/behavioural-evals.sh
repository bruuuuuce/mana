#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-evals.XXXXXX")"; trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
project="$tmp/project"; scenario="$tmp/passing"; mkdir -p "$project/.mana/global" "$scenario"
cat > "$scenario/scenario.md" <<'EOF'
# Scenario: deterministic plan
**Profile:** `mana-help`
EOF
cat > "$scenario/eval.yaml" <<'EOF'
version: 7
assertions:
  - type: must_use_skill
    value: mana-usage-help
  - type: must_not_use_tool
    value: database_write
  - type: must_not_modify
    value: true
  - type: max_delegation_depth
    value: 1
  - type: max_retrieval_cycles
    value: 3
  - type: must_flag
    value: compatibility-risk
EOF
printf 'compatibility-risk\n' > "$scenario/fixture-signals.txt"
one="$($root/scripts/mana-eval.sh --project-root "$project" run "$scenario" --json)" || fail 'passing assertions failed'
two="$($root/scripts/mana-eval.sh --project-root "$project" run "$scenario" --json)" || fail 'second passing run failed'
[ "$one" != "$two" ] || fail 'eval run identity was reused'
result="$(printf '%s' "$one" | sed -n 's/.*"results":\["\([^"]*\)"\].*/\1/p')"; [ -f "$result" ] || fail 'result was not persisted'
grep -Fq 'hidden reasoning' "$result" && fail 'private reasoning leaked'

failing="$tmp/failing"; cp -R "$scenario" "$failing"; sed -i.bak 's/mana-usage-help/no-such-skill/' "$failing/eval.yaml"; rm "$failing/eval.yaml.bak"
if "$root/scripts/mana-eval.sh" --project-root "$project" run "$failing" >/dev/null; then fail 'failing assertion passed'; fi

malformed="$tmp/malformed"; mkdir -p "$malformed"; printf '# Scenario\n**Profile:** `pr-ready`\n' > "$malformed/scenario.md"; printf 'version: 1\n' > "$malformed/eval.yaml"
if "$root/scripts/mana-eval.sh" --project-root "$project" run "$malformed" >/dev/null 2>&1; then fail 'malformed definition passed'; fi
if "$root/scripts/mana-eval.sh" --project-root "$project" run "$tmp/no-fixture" >/dev/null 2>&1; then fail 'missing fixture accepted'; fi

baseline="$tmp/baseline.json"; cp "$result" "$baseline"
candidate="$tmp/candidate.json"; sed 's/"pass":true/"pass":false/' "$result" > "$candidate"
comparison="$($root/scripts/mana-eval.sh compare "$baseline" "$candidate" --json)"; printf '%s' "$comparison" | grep -Fq '"newlyFailing":true' || fail 'regression comparison missing'
stale="$tmp/stale.json"; sed 's/"scenarioVersion":"7"/"scenarioVersion":"8"/' "$result" > "$stale"
stale_comparison="$($root/scripts/mana-eval.sh compare "$baseline" "$stale" --json)"; printf '%s' "$stale_comparison" | grep -Fq '"staleScenarioVersion":true' || fail 'stale scenario version missing'
report="$($root/scripts/mana-governance-report.sh --project-root "$project")"; report_file="$(printf '%s\n' "$report" | tail -n1)"; [ -f "$report_file" ] || fail 'governance report missing'
grep -Fq '# Mana Governance Report' "$report_file" || fail 'governance report content missing'
grep -Fq '`mana eval compare`' "$report_file" || fail 'Markdown report escaping/content missing'
echo 'Behavioural eval tests passed'
