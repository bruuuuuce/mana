#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
fail() { echo "FAIL: $*" >&2; exit 1; }

for file in \
  docs/roadmap/m07-release-readiness.md \
  docs/workflow/mana-inspect.md \
  docs/workflow/pilot-feedback.md \
  contracts/mana-inspect/v1/COMPATIBILITY.md \
  docs/standards/mana-familiar-inspect-v1-handoff.md \
  docs/standards/mana-familiar-inspect-compatibility-matrix.md; do
  [ -f "$root/$file" ] || fail "missing $file"
done

grep -Fq './mana inspect project --json' "$root/README.md" || fail 'README inspect command missing'
grep -Fq './mana inspect project --json' "$root/agents/mana-help-agent/AGENT.md" || fail 'mana-help inspect route missing'
grep -Fq 'Mana Familiar is a consumer' "$root/docs/workflow/mana-inspect.md" || fail 'consumer boundary missing'
grep -Fq 'not an approval mechanism' "$root/docs/workflow/mana-inspect.md" || fail 'approval boundary missing'
grep -Fq 'does not claim to be an OS sandbox' "$root/SECURITY.md" || fail 'sandbox limitation missing'
grep -Fq 'Complete zero-token acceptance suite' "$root/.github/workflows/validate-mana.yml" || fail 'CI acceptance suite missing'
grep -Fq 'mana-pilot-feedback.sh' "$root/scripts/validate-repo.sh" || fail 'pilot feedback validation missing'
grep -Fq 'mana-inspect.sh' "$root/scripts/validate-repo.sh" || fail 'inspect validation missing'
rg -n -i 'mana learning explorer|learning-journey-explorer' README.md docs agents profiles skills contracts scripts --glob '!docs/standards/mana-learning-journey-v0.md' >/dev/null && fail 'old Mana Familiar product name remains'

echo 'Release readiness documentation checks passed'
