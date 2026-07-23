#!/usr/bin/env bash
set -eu

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

for file in \
  "$root/profiles/epic-analysis.yaml" \
  "$root/skills/epic-structure-analysis/SKILL.md" \
  "$root/skills/epic-implementation-graph/SKILL.md" \
  "$root/agents/epic-analysis-agent/AGENT.md"; do
  [ -f "$file" ] || fail "missing $file"
done

grep -q '^service_discovery_approved=' "$root/scripts/run-profile.sh" || fail "missing discovery input"
grep -q -- '--allow-service-discovery' "$root/scripts/run-profile.sh" || fail "missing discovery flag"
grep -q 'Only if service_discovery_approved is true' "$root/scripts/run-profile.sh" || fail "missing runtime consent guard"
grep -q 'unverified_hypothesis' "$root/skills/epic-implementation-graph/SKILL.md" || fail "missing uncertain edge classification"
grep -q 'Never infer a dependency solely' "$root/skills/epic-implementation-graph/SKILL.md" || fail "missing dependency inference guard"

echo "Epic analysis profile tests passed"
