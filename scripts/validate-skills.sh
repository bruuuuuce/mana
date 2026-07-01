#!/usr/bin/env bash
set -u
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
required=(name version description compatibility preferred_runner allowed_tools inputs outputs risk_level owner_role tags)
status=0
count=0
for skill in "$root"/skills/*/SKILL.md; do
  [ -f "$skill" ] || continue
  count=$((count + 1))
  for field in "${required[@]}"; do
    if ! grep -q "^${field}:" "$skill"; then
      echo "ERROR: $skill missing front matter field: $field" >&2
      status=1
    fi
  done
done
if [ "$count" -eq 0 ]; then
  echo "ERROR: no skills found under $root/skills" >&2
  status=1
fi
if [ "$status" -eq 0 ]; then echo "Skills validation passed"; fi
exit "$status"
