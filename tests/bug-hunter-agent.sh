#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-bug-hunter.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
mkdir -p "$project/.mana/global"
project="$(cd "$project" && pwd -P)"
results_root="$project/.mana/evaluations/results"
fail() { echo "FAIL: $*" >&2; exit 1; }

for file in \
  docs/roadmap/m05-bug-hunter-gap-analysis.md \
  agents/bug-hunter-agent/AGENT.md \
  agents/bug-hunter-agent/playbook.md \
  agents/bug-hunter-agent/inputs.schema.json \
  agents/bug-hunter-agent/outputs.schema.json \
  profiles/bug-hunt.yaml; do
  [ -f "$root/$file" ] || fail "missing $file"
done

grep -Fq '25 files or 1,500 non-blank lines' "$root/agents/bug-hunter-agent/AGENT.md" || fail 'scope threshold missing'
grep -Fq 'no_material_findings' "$root/agents/bug-hunter-agent/AGENT.md" || fail 'no-findings contract missing'
grep -Fq 'Jessica' "$root/agents/bug-hunter-agent/AGENT.md" || fail 'Jessica routing missing'
grep -Fq 'must not apply' "$root/agents/bug-hunter-agent/AGENT.md" || fail 'read-only boundary missing'
jq -e '.required == ["target_paths", "scope_rationale"] and .properties.target_paths.maxItems == 25 and .properties.target_paths.items.pattern != null' "$root/agents/bug-hunter-agent/inputs.schema.json" >/dev/null || fail 'input scope contract is incomplete'
jq -e '.required == ["status", "findings"] and ([.properties.findings.items.required[]] | sort) == ["affected_path", "classification", "confidence", "failure_preconditions", "observable_symptom", "severity", "source_evidence", "suggested_reproducer_or_test"]' "$root/agents/bug-hunter-agent/outputs.schema.json" >/dev/null || fail 'finding evidence contract is incomplete'

scenarios=(bug-hunt-latent-defect bug-hunt-false-positive bug-hunt-large-scope bug-hunt-insufficient-evidence bug-hunt-overlap-routing bug-hunt-concurrency-boundary)
for scenario in "${scenarios[@]}"; do
  [ -f "$root/evals/scenarios/$scenario/scenario.md" ] || fail "missing scenario: $scenario"
  [ -f "$root/evals/scenarios/$scenario/eval.yaml" ] || fail "missing eval: $scenario"
  output="$("$root/scripts/mana-eval.sh" --project-root "$project" run "$scenario" --profile bug-hunt --json)" || fail "eval failed: $scenario"
  jq -e '.status == "passed" and (.results | length) == 1' <<<"$output" >/dev/null || fail "unexpected eval status or result count: $scenario"
  result="$(jq -r '.results[0]' <<<"$output")"
  [ -f "$result" ] && [ ! -L "$result" ] || fail "missing or linked result file: $scenario"
  result_dir="$(cd "$(dirname "$result")" && pwd -P)"
  case "$result_dir/$(basename "$result")" in
    "$results_root/$scenario/"*) ;;
    *) fail "result is outside the temporary project: $scenario" ;;
  esac
  case "$result_dir/" in
    "$root/"*) fail "result resolves under the repository: $scenario" ;;
  esac
  jq -e --arg scenario "$scenario" '.status == "passed" and .scenarioId == $scenario' "$result" >/dev/null || fail "invalid result file: $scenario"
done

for scenario in "${scenarios[@]}"; do
  [ -d "$results_root/$scenario" ] || fail "missing result directory: $scenario"
done
[ "$(find "$results_root" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" -eq 6 ] || fail 'unexpected bug-hunt result directory count'

echo 'Bug hunter agent tests passed'
