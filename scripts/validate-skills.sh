#!/usr/bin/env bash
set -u
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
required=(name version description compatibility preferred_runner allowed_tools inputs outputs risk_level owner_role tags)
status=0
for skill in "$root"/skills/*/SKILL.md; do
  [ -f "$skill" ] || continue
  for field in "${required[@]}"; do
    if ! grep -q "^${field}:" "$skill"; then
      echo "ERROR: $skill missing front matter field: $field" >&2
      status=1
    fi
  done
done
if [ "$status" -eq 0 ]; then echo "Skills validation passed"; fi
exit "$status"
