#!/usr/bin/env bash
set -u
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
required=(name version description compatibility preferred_runner allowed_tools inputs outputs risk_level owner_role stack tags)
status=0
count=0

validate_optional_value() {
  skill="$1"
  field="$2"
  allowed_pattern="$3"
  if grep -q "^${field}:" "$skill"; then
    value="$(grep "^${field}:" "$skill" | head -n 1 | sed "s/^${field}:[[:space:]]*//; s/^['\\\"]//; s/['\\\"]$//")"
    if ! printf '%s\n' "$value" | grep -Eq "$allowed_pattern"; then
      echo "ERROR: $skill invalid $field: $value" >&2
      status=1
    fi
  fi
}

for skill in "$root"/skills/*/SKILL.md; do
  [ -f "$skill" ] || continue
  count=$((count + 1))
  for field in "${required[@]}"; do
    if ! grep -q "^${field}:" "$skill"; then
      echo "ERROR: $skill missing front matter field: $field" >&2
      status=1
    fi
  done
  validate_optional_value "$skill" "model_tier" "^(economy|full)$"
  validate_optional_value "$skill" "execution_mode" "^(read|write)$"
  validate_optional_value "$skill" "delegation_group" "^(requirements|source|tests|architecture|contracts|database|security|operations|documentation|implementation)$"
  validate_optional_value "$skill" "parallel_safe" "^(true|false)$"
  validate_optional_value "$skill" "capability" "^(verification)$"
done
if [ -x "$root/scripts/validate-verification-skills.sh" ]; then
  "$root/scripts/validate-verification-skills.sh" "$root" || status=1
elif grep -R -q '^capability:[[:space:]]*verification$' "$root/skills" 2>/dev/null; then
  echo "ERROR: verification skills require scripts/validate-verification-skills.sh" >&2
  status=1
fi
if [ "$count" -eq 0 ]; then
  echo "ERROR: no skills found under $root/skills" >&2
  status=1
fi
if [ "$status" -eq 0 ]; then echo "Skills validation passed"; fi
exit "$status"
