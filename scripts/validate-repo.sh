#!/usr/bin/env bash
set -u
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
status=0
required_dirs=(docs skills agents profiles mcp templates scripts hooks .codex .junie templates/mana-workspace)
for d in "${required_dirs[@]}"; do
  if [ ! -d "$root/$d" ]; then echo "ERROR: missing directory $d" >&2; status=1; fi
done
"$root/scripts/validate-skills.sh" "$root" || status=1
"$root/scripts/validate-agents.sh" "$root" || status=1
"$root/scripts/validate-output-standard.sh" "$root" || status=1
"$root/scripts/validate-story-trace.sh" "$root" || status=1
"$root/scripts/validate-developer-choice-log.sh" "$root" || status=1
for f in README.md LICENSE CHANGELOG.md CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md docs/standards/agent-skill-output-standard.md docs/standards/story-trace-standard.md docs/standards/developer-choice-log-standard.md templates/standard-agent-skill-report.template.md templates/mana-workspace/story-trace.template.md templates/mana-workspace/developer-choice-log.template.md; do
  if [ ! -f "$root/$f" ]; then echo "ERROR: missing $f" >&2; status=1; fi
done
for f in scripts/mana-workspace.sh scripts/bootstrap-project.sh scripts/mana-doctor.sh scripts/mana-update-check.sh docs/workflow/mana-workspace.md docs/workflow/service-context-layer.md docs/deployment/project-link-bootstrap.md templates/mana-workspace/manifest.template.yaml templates/mana-workspace/index.template.md templates/mana-workspace/global/service-mission.template.md templates/mana-workspace/global/engineering-guards.template.md templates/mana-workspace/global/hooks-config.template.yaml; do
  if [ ! -f "$root/$f" ]; then echo "ERROR: missing $f" >&2; status=1; fi
done
if [ -f "$root/scripts/mana-workspace.sh" ] && [ ! -x "$root/scripts/mana-workspace.sh" ]; then
  echo "ERROR: scripts/mana-workspace.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/bootstrap-project.sh" ] && [ ! -x "$root/scripts/bootstrap-project.sh" ]; then
  echo "ERROR: scripts/bootstrap-project.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/mana-doctor.sh" ] && [ ! -x "$root/scripts/mana-doctor.sh" ]; then
  echo "ERROR: scripts/mana-doctor.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/mana-update-check.sh" ] && [ ! -x "$root/scripts/mana-update-check.sh" ]; then
  echo "ERROR: scripts/mana-update-check.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/validate-output-standard.sh" ] && [ ! -x "$root/scripts/validate-output-standard.sh" ]; then
  echo "ERROR: scripts/validate-output-standard.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/validate-story-trace.sh" ] && [ ! -x "$root/scripts/validate-story-trace.sh" ]; then
  echo "ERROR: scripts/validate-story-trace.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/validate-developer-choice-log.sh" ] && [ ! -x "$root/scripts/validate-developer-choice-log.sh" ]; then
  echo "ERROR: scripts/validate-developer-choice-log.sh is not executable" >&2
  status=1
fi
for f in "$root"/scripts/*.sh "$root"/hooks/pre-commit "$root"/hooks/pre-push; do
  [ -f "$f" ] || continue
  bash -n "$f" || status=1
done
if [ "$status" -eq 0 ]; then echo "Repository validation passed"; fi
exit "$status"
