#!/usr/bin/env bash
set -u
# Doctor is an observer.  Child Python processes must not create bytecode in a
# diagnosed project even when a host Python has its normal cache policy.
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/mana-doctor-pycache"

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
  - External tool availability and configuration for Mana capabilities.
  - Required Mana repository directories and scripts.
  - Skill and agent metadata validation.
  - Executable permissions.
  - Required profiles, including jessica-fletcher and mana-help.
  - Shared agent/skill output standard, story trace standard, and developer choice log standard.
  - No legacy naming references in writable Mana files.
  - Linked-project artifact availability when --project is provided.
  - Mana update-check script and no-fetch execution.
  - Optional User Context configuration, source health, and materialization freshness.
  - Read-only CTX-10 policy, bootstrap, provider and capability diagnostics.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

script_dir="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$script_dir/.." && pwd)"
. "$root/scripts/lib/user-context.sh"
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

check_required_tool() {
  tool="$1"
  purpose="$2"
  if command -v "$tool" >/dev/null 2>&1; then
    pass "tool available: $tool ($purpose)"
  else
    error "required tool missing: $tool ($purpose)"
  fi
}

check_optional_tool() {
  tool="$1"
  purpose="$2"
  if command -v "$tool" >/dev/null 2>&1; then
    pass "tool available: $tool ($purpose)"
    return 0
  fi
  warn "optional tool missing: $tool ($purpose)"
  return 1
}

has_jira_credentials_in_env() {
  if [ -n "${JIRA_URL:-}" ] && { [ -n "${JIRA_PERSONAL_TOKEN:-}" ] || [ -n "${JIRA_ACCESS_TOKEN:-}" ] || { [ -n "${JIRA_USERNAME:-}" ] && [ -n "${JIRA_API_TOKEN:-}" ]; }; }; then
    return 0
  fi
  return 1
}

has_sonar_credentials_in_env() {
  if [ -n "${SONAR_HOST_URL:-}" ] && [ -n "${SONAR_TOKEN:-}" ]; then
    return 0
  fi
  return 1
}

check_external_tools() {
  echo "External tool readiness:"

  check_required_tool bash "shell script execution"
  check_required_tool git "repository state, diffs, update checks"
  check_required_tool rg "repository search and diagnostics"

  check_optional_tool curl "Jira REST access checks and issue reads"
  check_optional_tool base64 "Jira Cloud basic-auth header generation"
  check_optional_tool shellcheck "Mana script linting during framework development"
  if check_optional_tool sonar-scanner "optional local code-quality evidence for branch and PR review"; then
    if sonar-scanner --version >/dev/null 2>&1; then
      pass "sonar-scanner command responds"
    else
      warn "sonar-scanner is installed but did not run; check Java version and scanner installation"
    fi
    warn "Sonar server/authentication probe skipped: mana doctor is local-only"
  fi

  if check_optional_tool docker "Jira MCP container runner"; then
    if docker info >/dev/null 2>&1; then
      pass "docker daemon reachable"
    else
      warn "docker installed but daemon is not reachable; Jira MCP container execution may fail"
    fi
  fi

  if check_optional_tool gh "GitHub PR discovery and requested-review workflows"; then
    pass "gh command available (authentication is not probed by local-only doctor)"
  fi

  if check_optional_tool codex "Codex profile runner"; then
    if codex --version >/dev/null 2>&1; then
      pass "codex command responds"
    else
      warn "codex is installed but did not respond to --version"
    fi
  fi

  if check_optional_tool claude "Claude Code profile runner"; then
    if claude --version >/dev/null 2>&1; then
      pass "claude command responds"
    else
      warn "claude is installed but did not respond to --version"
    fi
  fi

  if has_jira_credentials_in_env; then
    pass "Jira credential presence detected (authentication is not probed by local-only doctor)"
  elif [ -n "$project" ] && [ -f "$project/.mana/jira-mcp.env" ]; then
    pass "project Jira env file detected (contents and authentication are not inspected)"
  else
    warn "Jira credentials not configured; Jira story access will be unavailable until JIRA_URL and credentials are set"
  fi
}

echo "Mana doctor"
echo "Root: $root"
if [ -n "$project" ]; then echo "Project: $project"; fi

check_external_tools

echo "Repair containment"
echo "backend: unavailable (doctor does not materialize a repair workspace)"
echo "capability: unavailable"
echo "host patch import: unavailable"
echo "process isolation: unavailable"
echo "host filesystem isolation: unavailable"
echo "network isolation: unavailable"
echo "adversarial containment: unavailable"

user_context_project="${project:-$root}"
mana_user_context_status "$user_context_project"
if [ "$MANA_UC_CONFIGURED" != true ]; then
  if [ "$MANA_UC_FRESHNESS" = invalid ]; then
    warn "User Context configuration is invalid: $MANA_UC_ERROR"
  else
    pass "optional User Context is not configured"
  fi
elif [ "$MANA_UC_SOURCE_USABLE" != true ]; then
  warn "User Context is configured but unavailable: $MANA_UC_ERROR"
elif [ "$MANA_UC_MATERIALIZED" != true ]; then
  warn "User Context source is usable but has not been materialized; run: ./mana context refresh"
elif [ "$MANA_UC_FRESHNESS" != current ]; then
  warn "User Context materialization is $MANA_UC_FRESHNESS; run: ./mana context refresh"
else
  pass "User Context is configured, usable, and current (${MANA_UC_FILE_COUNT} files)"
fi

echo "Context runtime rollout (CTX-10 local-only):"
rollout_project="${project:-$root}"
if rollout_status="$(python3 "$root/scripts/context-runtime-rollout.py" status --project-root "$rollout_project" 2>/dev/null)"; then
  rollout_summary="$(printf '%s' "$rollout_status" | jq -r '
    "legacy=" + (.legacyAvailable|tostring) + " v2=" + (.v2Available|tostring) + " policy=" + .policy + " no-links=" + (.noLinks|tostring) + " budgets=" + .budget,
    (.providers|to_entries|sort_by(.key)[]|"provider " + .key + " installed=" + (.value.installed|tostring) + " block=" + .value.managedBlock),
    (.profileDiagnostics[]|"profile " + .profileId + " configured=" + .configuredSelection + " inherited=" + (.inheritedDefault|tostring) + " effective=" + .effectiveRuntime + " readiness=" + .readiness + " bootstrap=" + .bootstrapState + " gaps=" + (if (.blockingCapabilityGaps|length)==0 then "none" else (.blockingCapabilityGaps|join(",")) end), (.migrationWarnings[]|"warning " + .code + " severity=" + .severity + " profile=" + .profileId + " runtime=" + .currentRuntime + " reason=" + .reason + " action=" + .recommendedNextAction))
  ')" || rollout_summary=""
  [ -n "$rollout_summary" ] && printf '%s\n' "$rollout_summary"
  if printf '%s' "$rollout_status" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["policy"] == "current" else 1)'; then
    pass "CTX-10 host-owned runtime policy is available"
  else
    warn "CTX-10 host-owned runtime policy is unavailable or invalid; legacy remains the safe default"
  fi
else
  warn "CTX-10 local diagnostics unavailable; no provider or network probe was attempted"
fi

for dir in docs skills agents profiles mcp templates scripts hooks templates/mana-workspace .codex .junie .claude; do
  check_dir "$dir"
done

for file in README.md scripts/mana-workspace.sh scripts/mana-context.sh scripts/lib/user-context.sh scripts/bootstrap-project.sh scripts/mana-doctor.sh scripts/mana-update-check.sh scripts/run-profile.sh scripts/run-jira-mcp-docker.sh scripts/run-sonar-scanner.sh scripts/run-dependency-evidence.sh scripts/run-evidence-index.sh scripts/validate-output-standard.sh scripts/validate-story-trace.sh scripts/validate-developer-choice-log.sh profiles/jessica-fletcher.yaml profiles/mana-help.yaml profiles/pre-commit.yaml profiles/am-release-ready.yaml profiles/architecture-review.yaml profiles/team-planning.yaml profiles/story-ready-for-dev.yaml agents/pre-commit-documentation-agent/AGENT.md docs/workflow/mana-workspace.md docs/standards/agent-skill-output-standard.md docs/standards/story-trace-standard.md docs/standards/developer-choice-log-standard.md templates/standard-agent-skill-report.template.md templates/mana-workspace/story-trace.template.md templates/mana-workspace/developer-choice-log.template.md templates/mana-workspace/global/sonar-project.properties.template templates/pre-commit-development-summary.template.md templates/knowledge-transfer-brief.template.md .codex/README.md .codex/instructions.md .junie/README.md .junie/guidelines.md .claude/README.md .claude/instructions.md; do
  check_file "$file"
done

for file in scripts/mana-workspace.sh scripts/mana-context.sh scripts/bootstrap-project.sh scripts/mana-doctor.sh scripts/mana-update-check.sh scripts/run-jira-mcp-docker.sh scripts/run-sonar-scanner.sh scripts/run-dependency-evidence.sh scripts/run-evidence-index.sh scripts/run-profile.sh scripts/validate-output-standard.sh scripts/validate-story-trace.sh scripts/validate-developer-choice-log.sh; do
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

echo "Publication-sensitive diagnostics"
echo "workspace initialization: unavailable (doctor is read-only)"
echo "Sonar config initialization: unavailable (doctor is read-only)"
echo "Jira wrapper execution: unavailable (doctor does not start containers)"
echo "dependency evidence collection: unavailable (doctor does not collect evidence)"
echo "evidence-index production: unavailable (doctor does not publish an index)"

if [ -n "$project" ]; then
  if [ -x "$project/mana" ]; then pass "project wrapper exists: mana"; else warn "project wrapper missing: mana"; fi
  if [ -f "$project/.mana/env" ]; then pass "project Mana env exists"; else warn "project .mana/env missing"; fi
  if [ -f "$project/.mana/active-workspace" ]; then pass "project active workspace exists"; else warn "project active workspace missing"; fi
  if [ -f "$project/.mana/global/hooks-config.yaml" ]; then
    pass "project hooks-config.yaml exists"
  else
    warn "project .mana/global/hooks-config.yaml missing; run: scripts/mana-workspace.sh init --root $project"
  fi
  if [ -f "$project/.mana/global/sonar-project.properties" ]; then
    pass "project sonar-project.properties exists"
  else
    warn "project .mana/global/sonar-project.properties missing; run: ./mana sonar --init-config"
  fi
  for context_file in service-mission.md architecture.md engineering-guards.md; do
    if [ -s "$project/.mana/global/$context_file" ]; then
      pass "project service context exists: $context_file"
    else
      warn "project service context missing or empty: .mana/global/$context_file"
    fi
  done
  project_branch="$(git -C "$project" branch --show-current 2>/dev/null || true)"
  if [ -n "$project_branch" ]; then
    if printf '%s\n' "$project_branch" | grep -Eq '[A-Z][A-Z0-9]+-[0-9]+'; then
      pass "project branch contains issue key: $project_branch"
    else
      warn "project branch does not contain a generic issue key: $project_branch"
    fi
  else
    warn "project branch could not be resolved"
  fi
  if [ -f "$project/.mana/evidence/index.md" ] && [ ! -L "$project/.mana/evidence/index.md" ]; then
    pass "project evidence index is already materialized (contents not inspected)"
  else
    warn "project evidence index is unavailable/not-materialized; doctor will not generate it"
  fi
  if [ -x "$project/mana" ] && "$project/mana" profile mana-help >/dev/null; then
    pass "project wrapper can load mana-help"
  elif [ -x "$project/mana" ]; then
    error "project wrapper failed to load mana-help"
  fi
  for project_profile in story-start branch-ready requested-pr-review; do
    if [ -x "$project/mana" ] && "$project/mana" profile "$project_profile" >/dev/null; then
      pass "project wrapper can load $project_profile"
    elif [ -x "$project/mana" ]; then
      warn "project wrapper failed to load $project_profile"
    fi
  done
fi

if [ "$strict" = true ] && [ "$warnings" -gt 0 ]; then
  errors=$((errors + warnings))
fi

echo "Summary: $errors error(s), $warnings warning(s)"
[ "$errors" -eq 0 ]
