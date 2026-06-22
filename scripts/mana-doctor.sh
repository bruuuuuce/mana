#!/usr/bin/env bash
set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/mana-doctor.sh [options]

Runs local diagnostics for the Mana repository or a project linked to Mana.

Options:
  --root <path>        Mana repository root. Defaults to this script's parent repo.
  --project <path>     Optional target project root to diagnose.
  --strict             Treat warnings as failures.
  --help               Show this help.

Checks:
  - Required Mana repository directories and scripts.
  - Skill and agent metadata validation.
  - Executable permissions.
  - Required profiles, including jessica-fletcher and mana-help.
  - Shared agent/skill output standard, story trace standard, and developer choice log standard.
  - No legacy naming references in writable Mana files.
  - Workspace initialization in a temporary project.
  - Linked project wrapper when --project is provided.
  - Jira MCP Docker wrapper dry-run.
  - Mana update-check script and no-fetch execution.
  - Claude Code CLI availability (warn if not installed).
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

script_dir="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$script_dir/.." && pwd)"
project=""
strict=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)
      root="${2:-}"
      [ -n "$root" ] || fail "--root requires a path"
      shift 2
      ;;
    --project)
      project="${2:-}"
      [ -n "$project" ] || fail "--project requires a path"
      shift 2
      ;;
    --strict)
      strict=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

root="$(cd "$root" && pwd)"
if [ -n "$project" ]; then
  project="$(cd "$project" && pwd)"
fi

errors=0
warnings=0

pass() {
  echo "PASS: $*"
}

warn() {
  echo "WARN: $*" >&2
  warnings=$((warnings + 1))
}

error() {
  echo "FAIL: $*" >&2
  errors=$((errors + 1))
}

check_file() {
  file="$1"
  if [ -f "$root/$file" ]; then pass "file exists: $file"; else error "missing file: $file"; fi
}

check_dir() {
  dir="$1"
  if [ -d "$root/$dir" ]; then pass "directory exists: $dir"; else error "missing directory: $dir"; fi
}

check_exec() {
  file="$1"
  if [ -x "$root/$file" ]; then pass "executable: $file"; else error "not executable: $file"; fi
}

echo "Mana doctor"
echo "Root: $root"
if [ -n "$project" ]; then echo "Project: $project"; fi

for dir in docs skills agents profiles mcp templates scripts hooks templates/mana-workspace .codex .junie .claude; do
  check_dir "$dir"
done

for file in README.md scripts/mana-workspace.sh scripts/bootstrap-project.sh scripts/mana-doctor.sh scripts/mana-update-check.sh scripts/run-profile.sh scripts/run-jira-mcp-docker.sh scripts/validate-output-standard.sh scripts/validate-story-trace.sh scripts/validate-developer-choice-log.sh profiles/jessica-fletcher.yaml profiles/mana-help.yaml profiles/pre-commit.yaml profiles/am-release-ready.yaml profiles/architecture-review.yaml profiles/team-planning.yaml profiles/story-ready-for-dev.yaml agents/pre-commit-documentation-agent/AGENT.md docs/workflow/mana-workspace.md docs/standards/agent-skill-output-standard.md docs/standards/story-trace-standard.md docs/standards/developer-choice-log-standard.md templates/standard-agent-skill-report.template.md templates/mana-workspace/story-trace.template.md templates/mana-workspace/developer-choice-log.template.md templates/pre-commit-development-summary.template.md templates/knowledge-transfer-brief.template.md .codex/README.md .codex/instructions.md .junie/README.md .junie/guidelines.md .claude/README.md .claude/instructions.md; do
  check_file "$file"
done

for file in scripts/mana-workspace.sh scripts/bootstrap-project.sh scripts/mana-doctor.sh scripts/mana-update-check.sh scripts/run-jira-mcp-docker.sh scripts/run-profile.sh scripts/validate-output-standard.sh scripts/validate-story-trace.sh scripts/validate-developer-choice-log.sh; do
  check_exec "$file"
done

if "$root/scripts/validate-skills.sh" "$root"; then pass "skills metadata"; else error "skills metadata validation failed"; fi
if "$root/scripts/validate-agents.sh" "$root"; then pass "agents metadata"; else error "agents metadata validation failed"; fi
if "$root/scripts/validate-output-standard.sh" "$root"; then pass "agent and skill output standard"; else error "agent and skill output standard validation failed"; fi
if "$root/scripts/validate-story-trace.sh" "$root"; then pass "story trace standard"; else error "story trace standard validation failed"; fi
if "$root/scripts/validate-developer-choice-log.sh" "$root"; then pass "developer choice log standard"; else error "developer choice log standard validation failed"; fi

if "$root/scripts/run-profile.sh" mana-help >/dev/null; then pass "mana-help profile loads"; else error "mana-help profile failed"; fi
if "$root/scripts/run-profile.sh" jessica-fletcher >/dev/null; then pass "jessica-fletcher profile loads"; else error "jessica-fletcher profile failed"; fi
for profile in pre-commit am-release-ready architecture-review team-planning story-ready-for-dev; do
  if "$root/scripts/run-profile.sh" "$profile" >/dev/null; then
    pass "$profile profile loads"
  else
    error "$profile profile failed"
  fi
done
if "$root/scripts/mana-update-check.sh" --root "$root" --mode warn --no-fetch --profile doctor >/dev/null 2>&1; then
  pass "Mana update check no-fetch"
else
  error "Mana update check failed"
fi

old_product_lower="ai-delivery-""framework"
old_product_title="AI Delivery ""Framework"
old_workspace_title="Pat""roclo"
old_workspace_lower="pat""roclo"
old_workspace_dir="\\.pat""roclo"
old_wrapper_word="\\ba""df\\b"
old_wrapper_dir="\\.a""df"
old_env_home="AI_DELIVERY_""FRAMEWORK"
old_env_project="A""DF_PROJECT_ROOT"
legacy_pattern="$(printf '%s|%s|%s|%s|%s|%s|%s|%s|%s' \
  "$old_product_lower" \
  "$old_product_title" \
  "$old_workspace_title" \
  "$old_workspace_lower" \
  "$old_workspace_dir" \
  "$old_wrapper_word" \
  "$old_wrapper_dir" \
  "$old_env_home" \
  "$old_env_project")"

legacy_matches="$(find "$root" \
  -path "$root/.git" -prune -o \
  -path "$root/scripts/mana-doctor.sh" -prune -o \
  -type f \( -name '*.md' -o -name '*.yaml' -o -name '*.yml' -o -name '*.json' -o -name '*.sh' -o -name '.gitignore' \) \
  -print0 | xargs -0 rg -n "$legacy_pattern" 2>/dev/null || true)"
if [ -n "$legacy_matches" ]; then
  echo "$legacy_matches" >&2
  error "legacy naming references found"
else
  pass "no legacy naming references"
fi

tmp="${TMPDIR:-/tmp}/mana-doctor-$$"
rm -rf "$tmp"
mkdir -p "$tmp"
if "$root/scripts/mana-workspace.sh" init --root "$tmp" --feature MANA-DOCTOR >/dev/null; then
  if [ -f "$tmp/.mana/active-workspace" ] && [ -f "$tmp/.mana/features/MANA-DOCTOR/manifest.yaml" ] && [ -f "$tmp/.mana/features/MANA-DOCTOR/agent-memory/story-trace.md" ] && [ -f "$tmp/.mana/features/MANA-DOCTOR/decisions/developer-choice-log.md" ] && [ -f "$tmp/.mana/global/hooks-config.yaml" ]; then
    pass "temporary Mana workspace initialization"
  else
    error "temporary Mana workspace missing expected files"
  fi
else
  error "temporary Mana workspace initialization failed"
fi
rm -rf "$tmp"

if "$root/scripts/run-jira-mcp-docker.sh" --env-file "$root/mcp/env/jira-mcp.env.example" --dry-run >/dev/null; then
  pass "Jira MCP wrapper dry-run"
else
  error "Jira MCP wrapper dry-run failed"
fi

if command -v claude >/dev/null 2>&1; then
  pass "Claude CLI available"
else
  warn "Claude CLI not found; install Claude Code to use the claude runner (https://claude.ai/code)"
fi

if [ -n "$project" ]; then
  if [ -x "$project/mana" ]; then pass "project wrapper exists: mana"; else warn "project wrapper missing: mana"; fi
  if [ -f "$project/.mana/env" ]; then pass "project Mana env exists"; else warn "project .mana/env missing"; fi
  if [ -f "$project/.mana/active-workspace" ]; then pass "project active workspace exists"; else warn "project active workspace missing"; fi
  if [ -f "$project/.mana/global/hooks-config.yaml" ]; then
    pass "project hooks-config.yaml exists"
  else
    warn "project .mana/global/hooks-config.yaml missing; run: scripts/mana-workspace.sh init --root $project"
  fi
  if [ -x "$project/mana" ] && "$project/mana" profile mana-help >/dev/null; then
    pass "project wrapper can load mana-help"
  elif [ -x "$project/mana" ]; then
    error "project wrapper failed to load mana-help"
  fi
fi

if [ "$strict" = true ] && [ "$warnings" -gt 0 ]; then
  errors=$((errors + warnings))
fi

echo "Summary: $errors error(s), $warnings warning(s)"
[ "$errors" -eq 0 ]
