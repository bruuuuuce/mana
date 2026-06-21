#!/usr/bin/env bash
set -u

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
status=0

required_files=(
  "docs/standards/developer-choice-log-standard.md"
  "templates/mana-workspace/developer-choice-log.template.md"
)

for file in "${required_files[@]}"; do
  if [ ! -f "$root/$file" ]; then
    echo "ERROR: missing $file" >&2
    status=1
  fi
done

for file in \
  "$root/skills/developer-decision-review/SKILL.md" \
  "$root/skills/developer-handoff/SKILL.md" \
  "$root/skills/development-summary/SKILL.md" \
  "$root/agents/branch-validation-agent/AGENT.md" \
  "$root/agents/pr-readiness-agent/AGENT.md" \
  "$root/agents/team-leader-planning-agent/AGENT.md" \
  "$root/agents/jessica-fletcher-agent/AGENT.md"; do
  [ -f "$file" ] || continue
  if ! grep -q "decisions/developer-choice-log.md" "$file"; then
    echo "ERROR: $file does not reference decisions/developer-choice-log.md" >&2
    status=1
  fi
  if ! grep -q "Developer Choice Log Standard" "$file"; then
    echo "ERROR: $file does not reference the Developer Choice Log Standard" >&2
    status=1
  fi
done

for playbook in \
  "$root/agents/branch-validation-agent/playbook.md" \
  "$root/agents/pr-readiness-agent/playbook.md" \
  "$root/agents/team-leader-planning-agent/playbook.md" \
  "$root/agents/jessica-fletcher-agent/playbook.md"; do
  [ -f "$playbook" ] || continue
  if ! grep -q "decisions/developer-choice-log.md" "$playbook"; then
    echo "ERROR: $playbook does not reference decisions/developer-choice-log.md" >&2
    status=1
  fi
done

if [ "$status" -eq 0 ]; then
  echo "Developer choice log validation passed"
fi

exit "$status"
