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
  if ! grep -q "context budget" "$file"; then
    echo "ERROR: $file does not reference context budget discipline" >&2
    status=1
  fi
}

check_progressive_loading_reference() {
  file="$1"
  if ! grep -Eq "progressive load-light|Progressive Loading|load-light" "$file"; then
    echo "ERROR: $file does not reference progressive load-light loading" >&2
    status=1
  fi
}

check_skill_operational_shape() {
  file="$1"
  first_lines="$(sed -n '1,140p' "$file")"
  for heading in "## Purpose" "## When To Use It" "## Outputs" "## Decision Rules"; do
    if ! printf '%s\n' "$first_lines" | grep -qxF "$heading"; then
      echo "ERROR: $file is missing $heading in its load-light section" >&2
      status=1
    fi
  done
}

for file in "$root"/skills/*/SKILL.md "$root"/agents/*/AGENT.md "$root"/agents/*/playbook.md; do
  [ -f "$file" ] || continue
  check_output_standard_reference "$file"
done

for file in "$root"/skills/*/SKILL.md; do
  [ -f "$file" ] || continue
  check_skill_operational_shape "$file"
done

for file in \
  "$root/.codex/instructions.md" \
  "$root/.claude/instructions.md" \
  "$root/.junie/guidelines.md" \
  "$root/scripts/run-profile.sh" \
  "$root/scripts/bootstrap-project.sh"; do
  [ -f "$file" ] || continue
  check_output_standard_reference "$file"
  check_progressive_loading_reference "$file"
done

check_progressive_loading_reference "$root/$standard"

if [ "$status" -eq 0 ]; then
  echo "Output standard validation passed"
fi

exit "$status"
