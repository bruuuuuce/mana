#!/usr/bin/env bash
set -u
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
required=(name version description preferred_runner compatible_runners skills_used allowed_tools trigger_points inputs outputs human_approval_required risk_level)
status=0
count=0
for agent in "$root"/agents/*/AGENT.md; do
  [ -f "$agent" ] || continue
  count=$((count + 1))
  dir="$(dirname "$agent")"
  for field in "${required[@]}"; do
    if ! grep -q "^${field}:" "$agent"; then
      echo "ERROR: $agent missing front matter field: $field" >&2
      status=1
    fi
  done
  for f in playbook.md inputs.schema.json outputs.schema.json; do
    if [ ! -f "$dir/$f" ]; then
      echo "ERROR: $dir missing $f" >&2
      status=1
    fi
  done
done
if [ "$count" -eq 0 ]; then
  echo "ERROR: no agents found under $root/agents" >&2
  status=1
fi
if [ "$status" -eq 0 ]; then echo "Agents validation passed"; fi
exit "$status"
