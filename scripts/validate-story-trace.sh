#!/usr/bin/env bash
set -u

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
status=0

required_files=(
  "docs/standards/story-trace-standard.md"
  "templates/mana-workspace/story-trace.template.md"
)

for file in "${required_files[@]}"; do
  if [ ! -f "$root/$file" ]; then
    echo "ERROR: missing $file" >&2
    status=1
  fi
done

for agent in "$root"/agents/*/AGENT.md; do
  [ -f "$agent" ] || continue
  if ! grep -q "agent-memory/story-trace.md" "$agent"; then
    echo "ERROR: $agent does not reference agent-memory/story-trace.md" >&2
    status=1
  fi
  if ! grep -q "Story Trace Standard" "$agent"; then
    echo "ERROR: $agent does not reference the Story Trace Standard" >&2
    status=1
  fi
done

for playbook in "$root"/agents/*/playbook.md; do
  [ -f "$playbook" ] || continue
  if ! grep -q "agent-memory/story-trace.md" "$playbook"; then
    echo "ERROR: $playbook does not reference agent-memory/story-trace.md" >&2
    status=1
  fi
done

if [ "$status" -eq 0 ]; then
  echo "Story trace validation passed"
fi

exit "$status"
