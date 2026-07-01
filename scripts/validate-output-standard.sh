#!/usr/bin/env bash
set -u

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
status=0
standard="docs/standards/agent-skill-output-standard.md"

if [ ! -f "$root/$standard" ]; then
  echo "ERROR: missing $standard" >&2
  exit 1
fi

check_output_standard_reference() {
  file="$1"
  if ! grep -Eq "Agent And Skill Output Standard|agent-skill-output-standard\\.md" "$file"; then
    echo "ERROR: $file does not reference the output standard" >&2
    status=1
  fi
  if ! grep -q "caveman" "$file"; then
    echo "ERROR: $file does not reference compact caveman reasoning mode" >&2
    status=1
  fi
}

for file in "$root"/skills/*/SKILL.md "$root"/agents/*/AGENT.md "$root"/agents/*/playbook.md; do
  [ -f "$file" ] || continue
  check_output_standard_reference "$file"
done

for file in \
  "$root/.codex/instructions.md" \
  "$root/.claude/instructions.md" \
  "$root/.junie/guidelines.md" \
  "$root/scripts/run-profile.sh" \
  "$root/scripts/bootstrap-project.sh"; do
  [ -f "$file" ] || continue
  check_output_standard_reference "$file"
done

if [ "$status" -eq 0 ]; then
  echo "Output standard validation passed"
fi

exit "$status"
