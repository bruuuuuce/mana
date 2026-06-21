#!/usr/bin/env bash
set -u

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
status=0
standard="docs/standards/agent-skill-output-standard.md"

if [ ! -f "$root/$standard" ]; then
  echo "ERROR: missing $standard" >&2
  exit 1
fi

for file in "$root"/skills/*/SKILL.md "$root"/agents/*/AGENT.md; do
  [ -f "$file" ] || continue
  if ! grep -q "Agent And Skill Output Standard" "$file"; then
    echo "ERROR: $file does not reference the output standard" >&2
    status=1
  fi
  if ! grep -q "caveman" "$file"; then
    echo "ERROR: $file does not reference compact caveman reasoning mode" >&2
    status=1
  fi
done

if [ "$status" -eq 0 ]; then
  echo "Output standard validation passed"
fi

exit "$status"
