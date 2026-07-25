#!/usr/bin/env bash
# Static, repository-local governance summary. No server and no execution.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"; project_root="$(pwd)"; json=false
while [ "$#" -gt 0 ]; do case "$1" in --project-root) project_root="${2:-}"; shift 2;; --json) json=true; shift;; --help|-h) echo 'Usage: mana report governance [--json]'; exit 0;; *) echo "ERROR: unknown option: $1" >&2; exit 2;; esac; done
project_root="$(cd "$project_root" && pwd)"; rev="$(git -C "$root" rev-parse --short HEAD 2>/dev/null || printf workspace)"
escape_md() { printf '%s' "$1" | sed 's/|/\\|/g; s/</\\</g; s/>/\\>/g'; }
profiles="$(find "$root/profiles" -name '*.yaml' -type f | wc -l | tr -d ' ')"; skills="$(awk '/^  - id:/{n++} END{print n+0}' "$root/skills/index.yaml")"; gates="$(grep -l '^human_approval_requirement: true' "$root"/profiles/*.yaml | wc -l | tr -d ' ')"
risk_low="$(grep -c '^    risk_level: low' "$root/skills/index.yaml" || true)"; risk_medium="$(grep -c '^    risk_level: medium' "$root/skills/index.yaml" || true)"; risk_high="$(grep -c '^    risk_level: high' "$root/skills/index.yaml" || true)"
results_dir="$project_root/.mana/evaluations/results"; total=0; passed=0; for f in "$results_dir"/*.json; do [ -f "$f" ] || continue; total=$((total+1)); grep -Fq '"pass":true' "$f" && passed=$((passed+1)); done
missing=""; for p in "$root"/profiles/*.yaml; do ctx="$(sed -n '/^service_context:/,/^[^ ]/p' "$p" | sed -n 's/^  - //p')"; while IFS= read -r x; do [ -n "$x" ] && [ ! -f "$project_root/.mana/global/$x" ] && missing="${missing}${missing:+, }$x"; done <<EOF
$ctx
EOF
done; missing="$(printf '%s' "$missing" | tr ',' '\n' | sed '/^ *$/d' | LC_ALL=C sort -u | tr '\n' ',' | sed 's/,$//')"
invalid=false; "$root/scripts/validate-divination-metadata.sh" "$root" >/dev/null 2>&1 || invalid=true
learning="$(find "$project_root/.mana/learning/candidates" -name '*.json' -type f 2>/dev/null | wc -l | tr -d ' ')"
outdir="$project_root/.mana/reports"; mkdir -p "$outdir"; out="$outdir/governance-$rev.md"
{ echo '# Mana Governance Report'; echo; printf 'Revision: `%s`\n\n' "$(escape_md "$rev")"; echo '| Measure | Value |'; echo '|---|---:|'; echo "| Profile coverage | $profiles profiles |"; echo "| Skill ownership | $skills indexed skills |"; echo "| Risk-domain coverage | low: $risk_low, medium: $risk_medium, high: $risk_high skills |"; echo "| Human-gate coverage | $gates profiles require approval |"; echo "| Behavioural eval pass rate | $passed / $total |"; echo "| Model-routing coverage | skills indexed with tiers in skills/index.yaml |"; echo '| Stale components | no time-based component lifecycle is declared |'; echo "| Invalid metadata | $invalid |"; echo "| Unreviewed learning candidates | $learning |"; echo '| Recent regressions | inspect `mana eval compare` result |'; echo; echo '## Missing Service Context'; echo; [ -n "$missing" ] && printf '%s\n' "$missing" | tr ',' '\n' | sed 's/^/- `/' | sed 's/$/`/' || echo 'None detected from profile core-file declarations.'; echo; echo '## Scope'; echo; echo 'This is a repository-data summary. It does not prove semantic model quality, production safety, or human approval.'; } > "$out"
if [ "$json" = true ]; then printf '{"report":"%s","profiles":%s,"skills":%s,"humanGateProfiles":%s,"evalPassed":%s,"evalTotal":%s,"invalidMetadata":%s,"unreviewedLearningCandidates":%s}\n' "$out" "$profiles" "$skills" "$gates" "$passed" "$total" "$invalid" "$learning"; else echo "MANA GOVERNANCE REPORT"; echo "$out"; fi
