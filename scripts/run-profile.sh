#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/profile-metadata.sh
. "$root/scripts/lib/profile-metadata.sh"
profile=""
project_root=""
render_only=false
runner=""
pr_number=""
publish_high_risk_comments=false
service_discovery_approved=false
jira_keys=""
jira_key_regex="${MANA_JIRA_KEY_REGEX:-[A-Z][A-Z0-9]+-[0-9]+}"
jira_env_file="${MANA_JIRA_MCP_ENV:-}"
jira_mcp_configured=false
jira_mcp_config_source=""
codex_model="${MANA_CODEX_MODEL:-gpt-5.4-mini}"
codex_full_model="${MANA_CODEX_FULL_MODEL:-gpt-5.6-sol}"
codex_explorer_model="${MANA_CODEX_EXPLORER_MODEL:-gpt-5.6-terra}"
codex_worker_model="${MANA_CODEX_WORKER_MODEL:-gpt-5.6-terra}"
codex_model_policy="${MANA_CODEX_MODEL_POLICY:-economy-first}"
codex_subagents="${MANA_CODEX_SUBAGENTS:-true}"
codex_max_threads="${MANA_CODEX_MAX_THREADS:-3}"
codex_max_depth=1
codex_agent_install_warnings=""
claude_model="${MANA_CLAUDE_MODEL:-haiku}"
claude_full_model="${MANA_CLAUDE_FULL_MODEL:-opus}"
claude_explorer_model="${MANA_CLAUDE_EXPLORER_MODEL:-sonnet}"
claude_worker_model="${MANA_CLAUDE_WORKER_MODEL:-sonnet}"
claude_subagents="${MANA_CLAUDE_SUBAGENTS:-true}"
claude_max_threads="${MANA_CLAUDE_MAX_THREADS:-3}"
claude_agent_install_warnings=""
opencode_model="${MANA_OPENCODE_MODEL:-opencode/gpt-5.1-codex}"
opencode_full_model="${MANA_OPENCODE_FULL_MODEL:-}"
opencode_explorer_model="${MANA_OPENCODE_EXPLORER_MODEL:-}"
opencode_worker_model="${MANA_OPENCODE_WORKER_MODEL:-}"
opencode_subagents="${MANA_OPENCODE_SUBAGENTS:-true}"
opencode_max_threads="${MANA_OPENCODE_MAX_THREADS:-3}"
opencode_agent_install_warnings=""

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-profile.sh <profile-name> [options]

Options:
  --project-root <path>          Target project root. Defaults to current directory.
  --render-only                  Render the profile and never start a runner.
  --codex                        Execute the rendered profile through Codex.
  --claude                       Execute the rendered profile through Claude Code.
  --opencode                     Execute the rendered profile through OpenCode.
  --codex-model <model>          Codex model for the root orchestrator. Defaults to MANA_CODEX_MODEL or gpt-5.4-mini.
  --codex-full-model <model>     Codex model for mana_full_specialist. Defaults to MANA_CODEX_FULL_MODEL or gpt-5.6-sol.
  --codex-explorer-model <model> Codex model for mana_explorer. Defaults to MANA_CODEX_EXPLORER_MODEL or gpt-5.6-terra.
  --codex-worker-model <model>   Codex model for mana_worker. Defaults to MANA_CODEX_WORKER_MODEL or gpt-5.6-terra.
  --codex-model-policy <policy>  Model policy note passed to Codex. Defaults to economy-first.
  --no-codex-subagents           Disable Codex subagent orchestration and use legacy manual escalation.
  --claude-model <model>         Claude model for the root orchestrator. Defaults to MANA_CLAUDE_MODEL or haiku.
  --claude-full-model <model>    Claude model for mana-full-specialist. Defaults to MANA_CLAUDE_FULL_MODEL or opus.
  --claude-explorer-model <m>    Claude model for mana-explorer. Defaults to MANA_CLAUDE_EXPLORER_MODEL or sonnet.
  --claude-worker-model <model>  Claude model for mana-worker. Defaults to MANA_CLAUDE_WORKER_MODEL or sonnet.
  --no-claude-subagents          Disable Claude subagent orchestration and use manual escalation.
  --opencode-model <model>       OpenCode model for the primary orchestrator. Defaults to MANA_OPENCODE_MODEL or opencode/gpt-5.1-codex.
  --opencode-full-model <model>  OpenCode model for mana_full_specialist. Defaults to MANA_OPENCODE_FULL_MODEL or the root OpenCode model.
  --opencode-explorer-model <m>  OpenCode model for mana_explorer. Defaults to MANA_OPENCODE_EXPLORER_MODEL or the root OpenCode model.
  --opencode-worker-model <m>    OpenCode model for mana_worker. Defaults to MANA_OPENCODE_WORKER_MODEL or the root OpenCode model.
  --no-opencode-subagents        Disable OpenCode subagent orchestration and use manual escalation.
  --pr, --pr-number <value>      Pull request number or URL for requested-pr-review.
  --jira-key, --jira-issue <KEY> Add an explicit Jira issue key.
  --jira-key-regex <regex>       Override branch issue-key discovery.
  --allow-service-discovery       Allow epic-analysis to inspect named services read-only.
  --publish-high-risk-comments   Allow requested-pr-review to publish one high-risk PR comment.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root)
      project_root="${2:-}"
      [ -n "$project_root" ] || { echo "ERROR: --project-root requires a path" >&2; exit 2; }
      shift 2
      ;;
    --render-only)
      render_only=true
      shift
      ;;
    --codex)
      [ -z "$runner" ] || { echo "ERROR: choose only one runner flag" >&2; exit 2; }
      runner="codex"
      shift
      ;;
    --claude)
      [ -z "$runner" ] || { echo "ERROR: choose only one runner flag" >&2; exit 2; }
      runner="claude"
      shift
      ;;
    --opencode)
      [ -z "$runner" ] || { echo "ERROR: choose only one runner flag" >&2; exit 2; }
      runner="opencode"
      shift
      ;;
    --codex-model)
      codex_model="${2:-}"
      [ -n "$codex_model" ] || { echo "ERROR: --codex-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --codex-full-model)
      codex_full_model="${2:-}"
      [ -n "$codex_full_model" ] || { echo "ERROR: --codex-full-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --codex-explorer-model)
      codex_explorer_model="${2:-}"
      [ -n "$codex_explorer_model" ] || { echo "ERROR: --codex-explorer-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --codex-worker-model)
      codex_worker_model="${2:-}"
      [ -n "$codex_worker_model" ] || { echo "ERROR: --codex-worker-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --codex-model-policy)
      codex_model_policy="${2:-}"
      [ -n "$codex_model_policy" ] || { echo "ERROR: --codex-model-policy requires a policy name" >&2; exit 2; }
      shift 2
      ;;
    --no-codex-subagents)
      codex_subagents=false
      shift
      ;;
    --claude-model)
      claude_model="${2:-}"
      [ -n "$claude_model" ] || { echo "ERROR: --claude-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --claude-full-model)
      claude_full_model="${2:-}"
      [ -n "$claude_full_model" ] || { echo "ERROR: --claude-full-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --claude-explorer-model)
      claude_explorer_model="${2:-}"
      [ -n "$claude_explorer_model" ] || { echo "ERROR: --claude-explorer-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --claude-worker-model)
      claude_worker_model="${2:-}"
      [ -n "$claude_worker_model" ] || { echo "ERROR: --claude-worker-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --no-claude-subagents)
      claude_subagents=false
      shift
      ;;
    --opencode-model)
      opencode_model="${2:-}"
      [ -n "$opencode_model" ] || { echo "ERROR: --opencode-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --opencode-full-model)
      opencode_full_model="${2:-}"
      [ -n "$opencode_full_model" ] || { echo "ERROR: --opencode-full-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --opencode-explorer-model)
      opencode_explorer_model="${2:-}"
      [ -n "$opencode_explorer_model" ] || { echo "ERROR: --opencode-explorer-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --opencode-worker-model)
      opencode_worker_model="${2:-}"
      [ -n "$opencode_worker_model" ] || { echo "ERROR: --opencode-worker-model requires a model name" >&2; exit 2; }
      shift 2
      ;;
    --no-opencode-subagents)
      opencode_subagents=false
      shift
      ;;
    --pr|--pr-number)
      pr_number="${2:-}"
      [ -n "$pr_number" ] || { echo "ERROR: $1 requires a pull request number or URL" >&2; exit 2; }
      shift 2
      ;;
    --publish-high-risk-comments)
      publish_high_risk_comments=true
      shift
      ;;
    --allow-service-discovery)
      service_discovery_approved=true
      shift
      ;;
    --jira-key|--jira-issue)
      jira_keys="${jira_keys}${jira_keys:+ }${2:-}"
      [ -n "${2:-}" ] || { echo "ERROR: $1 requires a Jira issue key" >&2; exit 2; }
      shift 2
      ;;
    --jira-key-regex)
      jira_key_regex="${2:-}"
      [ -n "$jira_key_regex" ] || { echo "ERROR: --jira-key-regex requires a regex" >&2; exit 2; }
      shift 2
      ;;
    --*)
      echo "ERROR: unknown option: $1" >&2
      exit 2
      ;;
    *)
      if [ -z "$profile" ]; then
        profile="$1"
        shift
      else
        echo "ERROR: unexpected argument: $1" >&2
        exit 2
      fi
      ;;
  esac
done

if [ -z "$profile" ]; then
  active_file="${project_root:-.}/.mana/active-profile"
  if [ -f "$active_file" ]; then
    profile="$(tr -d '[:space:]' < "$active_file")"
    echo "Using active profile: $profile (from .mana/active-profile)"
  else
    usage
    exit 2
  fi
fi

file="$root/profiles/${profile}.yaml"
if [ ! -f "$file" ]; then
  echo "ERROR: profile not found: $profile"
  exit 1
fi

if [ "$publish_high_risk_comments" = true ] && [ "$profile" != "requested-pr-review" ]; then
  echo "ERROR: --publish-high-risk-comments is only supported by requested-pr-review" >&2
  exit 2
fi

if [ "$publish_high_risk_comments" = true ] && [ -z "$pr_number" ]; then
  echo "ERROR: --publish-high-risk-comments requires --pr <number-or-url>" >&2
  exit 2
fi

if [ "$service_discovery_approved" = true ] && [ "$profile" != "epic-analysis" ]; then
  echo "ERROR: --allow-service-discovery is only supported by epic-analysis" >&2
  exit 2
fi

if [ -z "$project_root" ]; then
  project_root="$(pwd)"
fi

case "$codex_subagents" in
  true|TRUE|True|1|yes|YES|on|ON)
    codex_subagents=true
    ;;
  false|FALSE|False|0|no|NO|off|OFF)
    codex_subagents=false
    ;;
  *)
    echo "ERROR: MANA_CODEX_SUBAGENTS must be true or false" >&2
    exit 2
    ;;
esac

case "$claude_subagents" in
  true|TRUE|True|1|yes|YES|on|ON)
    claude_subagents=true
    ;;
  false|FALSE|False|0|no|NO|off|OFF)
    claude_subagents=false
    ;;
  *)
    echo "ERROR: MANA_CLAUDE_SUBAGENTS must be true or false" >&2
    exit 2
    ;;
esac

if ! printf '%s\n' "$codex_max_threads" | grep -Eq '^[0-9]+$' || [ "$codex_max_threads" -lt 1 ] || [ "$codex_max_threads" -gt 3 ]; then
  echo "ERROR: MANA_CODEX_MAX_THREADS must be a positive integer no greater than 3" >&2
  exit 2
fi

if ! printf '%s\n' "$claude_max_threads" | grep -Eq '^[0-9]+$' || [ "$claude_max_threads" -lt 1 ] || [ "$claude_max_threads" -gt 3 ]; then
  echo "ERROR: MANA_CLAUDE_MAX_THREADS must be a positive integer no greater than 3" >&2
  exit 2
fi

case "$opencode_subagents" in
  true|TRUE|True|1|yes|YES|on|ON)
    opencode_subagents=true
    ;;
  false|FALSE|False|0|no|NO|off|OFF)
    opencode_subagents=false
    ;;
  *)
    echo "ERROR: MANA_OPENCODE_SUBAGENTS must be true or false" >&2
    exit 2
    ;;
esac

if ! printf '%s\n' "$opencode_max_threads" | grep -Eq '^[0-9]+$' || [ "$opencode_max_threads" -lt 1 ] || [ "$opencode_max_threads" -gt 3 ]; then
  echo "ERROR: MANA_OPENCODE_MAX_THREADS must be a positive integer no greater than 3" >&2
  exit 2
fi

: "${opencode_full_model:=$opencode_model}"
: "${opencode_explorer_model:=$opencode_model}"
: "${opencode_worker_model:=$opencode_model}"

current_branch=""
if git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  current_branch="$(git -C "$project_root" branch --show-current 2>/dev/null || true)"
fi

discovered_jira_keys=""
if [ -n "$current_branch" ]; then
  discovered_jira_keys="$(printf '%s\n' "$current_branch" | grep -Eo "$jira_key_regex" | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
fi
if [ -z "$jira_keys" ]; then
  jira_keys="$discovered_jira_keys"
elif [ -n "$discovered_jira_keys" ]; then
  jira_keys="$(printf '%s\n%s\n' "$jira_keys" "$discovered_jira_keys" | tr ' ' '\n' | sed '/^$/d' | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
fi

if [ -z "$jira_env_file" ]; then
  if [ -f "$project_root/.mana/jira-mcp.env" ]; then
    jira_env_file="$project_root/.mana/jira-mcp.env"
  elif [ -f "$root/mcp/env/jira-mcp.env" ]; then
    jira_env_file="$root/mcp/env/jira-mcp.env"
  fi
fi
if [ -n "$jira_env_file" ]; then
  jira_mcp_configured=true
  jira_mcp_config_source="env_file"
elif [ -n "${JIRA_URL:-}" ] &&
  {
    [ -n "${JIRA_PERSONAL_TOKEN:-}" ] ||
      { [ -n "${JIRA_USERNAME:-}" ] && [ -n "${JIRA_API_TOKEN:-}" ]; }
  }; then
  jira_mcp_configured=true
  jira_mcp_config_source="environment"
fi

if [ "$render_only" = true ] && [ -n "$runner" ]; then
  echo "ERROR: --render-only cannot be combined with --$runner" >&2
  exit 2
fi

"$root/scripts/mana-update-check.sh" --root "$root" --profile "$profile" || exit 1

profile_skills="$(mana_profile_skills "$file")"
skill_index="$root/skills/index.yaml"

skill_metadata() {
  skill_id="$1"
  awk -v target="$skill_id" '
    $1 == "-" && $2 == "id:" {
      if (found) { print risk "|" tier "|" mode "|" group; active = 0; exit }
      active = ($3 == target)
      found = active
      next
    }
    active && $1 == "risk_level:" { risk = $2 }
    active && $1 == "model_tier:" { tier = $2 }
    active && $1 == "execution_mode:" { mode = $2 }
    active && $1 == "delegation_group:" { group = $2 }
    END { if (found && active) print risk "|" tier "|" mode "|" group }
  ' "$skill_index"
}

model_escalation_skills=""
if [ -n "$profile_skills" ]; then
  while IFS= read -r skill; do
    [ -n "$skill" ] || continue
    metadata="$(skill_metadata "$skill")"
    case "$metadata" in
      *'|full|'*|high'|'*)
      model_escalation_skills="${model_escalation_skills}${model_escalation_skills:+ }$skill"
        ;;
    esac
  done <<EOF
$profile_skills
EOF
fi

model_routing_warning=""
if [ -n "$model_escalation_skills" ]; then
  model_routing_warning="This profile includes full-tier or high-risk skill candidates. The root model is for routing, evidence inventory, low-risk checks, and synthesis only; delegate deep judgment to the configured full specialist or stop with needs_model_escalation if escalation is unavailable."
fi

render_codex_agent() {
  agent_name="$1"
  model="$2"
  effort="$3"
  sandbox="$4"
  description="$5"
  instructions="$6"

  cat <<AGENT
# Mana-managed Codex custom agent.
# Source: Mana scripts/run-profile.sh and scripts/bootstrap-project.sh.
# Safe to replace with --force or during a Mana profile run.
name = "$agent_name"
description = "$description"
model = "$model"
model_reasoning_effort = "$effort"
sandbox_mode = "$sandbox"
developer_instructions = """
$instructions
"""
AGENT
}

codex_agent_instructions() {
  case "$1" in
    mana_explorer)
      cat <<'TEXT'
You are mana_explorer, a Mana runtime Codex agent for bounded repository evidence discovery.
Remain read-only. Use targeted search rather than broad repository dumping. Do not redesign the solution, make high-risk architecture judgments, edit source, or spawn other agents.
Use at most three explicit retrieval cycles: DISPATCH a focused question, EVALUATE the evidence, REFINE only when a new targeted request is meaningful, then LOOP or STOP. Each cycle must record the question, available evidence, requested files or symbols and why, retrieved evidence, sufficiency, gaps, and its stop/refine decision. Never retrieve an unchanged item twice or load a full file when a symbol/range suffices. Stop on sufficiency, the third cycle, no meaningful refinement, a tool/governance boundary, or a required human input. Do not recursively delegate to another explorer.
Return a compact structured summary with: investigated_question, retrieval_cycles, relevant_evidence_with_provenance, rejected_evidence, probably_modify, inspect_before_deciding, do_not_touch_unless_approved, unresolved_evidence_gaps, sufficiency_status, recommended_next_action, artifact_paths.
Use exact file and symbol references. Explicitly report evidence gaps. Do not copy large diffs, raw logs, or full file bodies.
TEXT
      ;;
    mana_full_specialist)
      cat <<'TEXT'
You are mana_full_specialist, a Mana runtime Codex agent for bounded high-risk judgment.
Remain read-only. Execute only the bounded task and Mana skills assigned by the parent. Do not broaden scope, edit source, or spawn other agents.
Use this role for architecture, security, trust boundaries, concurrency, transaction semantics, database and Liquibase production risk, cross-service contracts, backwards compatibility, production behavior, large or ambiguous diffs, and model_tier: full work.
Inspect the minimum sufficient evidence. Distinguish facts, inferences, uncertainty, and missing evidence. Return actionable findings by severity.
Return a compact structured summary with: status, assigned_goal, skills_executed, risk_domains, evidence_inspected, findings_by_severity, assumptions, evidence_gaps, confidence, required_human_approvals, artifact_paths.
Do not copy raw logs, entire diffs, full Jira payloads, PR threads, or large file bodies.
TEXT
      ;;
    mana_worker)
      cat <<'TEXT'
You are mana_worker, a Mana runtime Codex agent for narrowly bounded implementation or artifact-writing work.
Run only when the selected Mana profile explicitly permits source modification. Never infer write permission from sandbox access. Do not run for analysis-only profiles.
Use one writer at a time; never run parallel writers against the same working tree. Make the smallest defensible change and avoid unrelated cleanup.
Do not commit, push, merge, publish, deploy, trigger CI, write to external systems, or spawn other agents.
Report files changed and validation performed.
TEXT
      ;;
  esac
}

install_codex_agent_file() {
  target="$1"
  content="$2"
  if [ -e "$target" ] && [ ! -L "$target" ] && ! grep -q 'Mana-managed Codex custom agent' "$target" 2>/dev/null; then
    codex_agent_install_warnings="${codex_agent_install_warnings}${codex_agent_install_warnings:+
}WARNING: not replacing non-managed Codex agent $target"
    return 1
  fi
  if [ -L "$target" ]; then
    rm "$target"
  fi
  printf '%s\n' "$content" > "$target"
}

render_claude_agent() {
  agent_name="$1"
  description="$2"
  tools="$3"
  model="$4"
  permission_mode="$5"
  effort="$6"
  instructions="$7"

  cat <<AGENT
---
# Mana-managed Claude Code subagent.
# Source: Mana scripts/run-profile.sh and scripts/bootstrap-project.sh.
# Safe to replace with --force or during a Mana profile run.
name: $agent_name
description: "$description"
tools: $tools
model: $model
permissionMode: $permission_mode
effort: $effort
---
$instructions
AGENT
}

claude_agent_instructions() {
  case "$1" in
    mana-orchestrator)
      cat <<'TEXT'
You are mana-orchestrator, the Claude Code primary runtime agent for Mana profile execution.

Use the economy root model for routing, evidence inventory, low-risk checks, delegation, aggregation, and final synthesis. Mana semantic agents remain under agents/ and Mana skills remain under skills/. Do not map every Mana agent or every Mana skill to a separate Claude subagent.

When required work is high-risk, explicitly full-tier, noisy, or beyond root-model confidence, delegate it to the appropriate Mana Claude subagent. Batch related Mana skills into one delegation by risk domain. Do not spawn one subagent per skill. Spawn at most three direct subagents in total, never more than one per capability class, and delegate parallel work only when it is independent and read-heavy.

Use mana-explorer for read-heavy evidence discovery. Use mana-full-specialist for architecture, security, database, concurrency, cross-service, production, transactional, backwards-compatibility, model_tier: full, or large/ambiguous diff judgment. Use mana-worker only when the selected Mana profile explicitly permits source modification, and never run parallel writers.

Wait for delegated work and aggregate compact structured summaries and artifact paths only. Do not import raw tool transcripts into the root context. If subagents are disabled, missing, fail, or return insufficient evidence for a high-risk judgment, preserve a concise handoff artifact and return needs_model_escalation instead of performing that judgment on the economy model.
TEXT
      ;;
    mana-explorer)
      codex_agent_instructions mana_explorer | sed 's/Mana runtime Codex agent/Mana runtime Claude Code subagent/; s/Codex/Claude Code/g'
      ;;
    mana-full-specialist)
      codex_agent_instructions mana_full_specialist | sed 's/Mana runtime Codex agent/Mana runtime Claude Code subagent/; s/Codex/Claude Code/g'
      ;;
    mana-worker)
      codex_agent_instructions mana_worker | sed 's/Mana runtime Codex agent/Mana runtime Claude Code subagent/; s/Codex/Claude Code/g'
      ;;
  esac
}

install_claude_agent_file() {
  target="$1"
  content="$2"
  if [ -e "$target" ] && [ ! -L "$target" ] && ! grep -q 'Mana-managed Claude Code subagent' "$target" 2>/dev/null; then
    claude_agent_install_warnings="${claude_agent_install_warnings}${claude_agent_install_warnings:+
}WARNING: not replacing non-managed Claude Code subagent $target"
    return 1
  fi
  if [ -L "$target" ]; then
    rm "$target"
  fi
  printf '%s\n' "$content" > "$target"
}

ensure_claude_agents() {
  agents_dir="$project_root/.claude/agents"
  if ! mkdir -p "$agents_dir" 2>/dev/null; then
    claude_agent_install_warnings="${claude_agent_install_warnings}${claude_agent_install_warnings:+
}WARNING: could not create $agents_dir; Claude Code delegation must fall back if agents are unavailable"
    return 0
  fi

  orchestrator_content="$(render_claude_agent "mana-orchestrator" "Mana primary orchestrator for profile routing, light evidence inventory, bounded delegation, and final synthesis." "Agent(mana-explorer, mana-full-specialist, mana-worker), Read, Glob, Grep, Bash, Write, Edit" "$claude_model" "default" "low" "$(claude_agent_instructions mana-orchestrator)")"
  install_claude_agent_file "$agents_dir/mana-orchestrator.md" "$orchestrator_content" || true

  [ "$claude_subagents" = true ] || return 0

  readonly_claude_tools="Read, Glob, Grep, Bash(git diff:*), Bash(git status:*), Bash(git log:*), Bash(git show:*), Bash(rg:*), Bash(find:*)"
  explorer_content="$(render_claude_agent "mana-explorer" "Mana read-only repository evidence discovery and inventory." "$readonly_claude_tools" "$claude_explorer_model" "default" "medium" "$(claude_agent_instructions mana-explorer)")"
  full_content="$(render_claude_agent "mana-full-specialist" "Mana high-risk full-model specialist for bounded architecture, database, security, contract, concurrency, and production judgments." "$readonly_claude_tools" "$claude_full_model" "default" "high" "$(claude_agent_instructions mana-full-specialist)")"
  worker_content="$(render_claude_agent "mana-worker" "Mana bounded worker for explicitly authorized implementation or artifact-writing tasks." "Read, Glob, Grep, Bash, Write, Edit" "$claude_worker_model" "default" "medium" "$(claude_agent_instructions mana-worker)")"

  install_claude_agent_file "$agents_dir/mana-explorer.md" "$explorer_content" || true
  install_claude_agent_file "$agents_dir/mana-full-specialist.md" "$full_content" || true
  install_claude_agent_file "$agents_dir/mana-worker.md" "$worker_content" || true
}

render_opencode_agent() {
  agent_name="$1"
  mode="$2"
  model="$3"
  description="$4"
  permission_block="$5"
  instructions="$6"

  cat <<AGENT
---
# Mana-managed OpenCode agent.
# Source: Mana scripts/run-profile.sh and scripts/bootstrap-project.sh.
# Safe to replace with --force or during a Mana profile run.
description: "$description"
mode: $mode
model: $model
temperature: 0.1
permission:
$permission_block
---
$instructions
AGENT
}

opencode_agent_instructions() {
  case "$1" in
    mana_orchestrator)
      cat <<'TEXT'
You are mana_orchestrator, the OpenCode primary runtime agent for Mana profile execution.

Use the primary model for routing, evidence inventory, low-risk checks, delegation, aggregation, and final synthesis. Mana semantic agents remain under agents/ and Mana skills remain under skills/. Do not map every Mana agent or every Mana skill to a separate OpenCode subagent.

When required work is high-risk, explicitly full-tier, noisy, or beyond primary-model confidence, delegate it to the appropriate Mana OpenCode subagent. Batch related Mana skills into one delegation by risk domain. Do not spawn one subagent per skill. Spawn at most three direct subagents. Child agents must not delegate further.

Use mana_explorer for read-heavy evidence discovery. Use mana_full_specialist for architecture, security, database, concurrency, cross-service, production, transactional, backwards-compatibility, model_tier: full, or large/ambiguous diff judgment. Use mana_worker only when the selected Mana profile explicitly permits source modification, and never run parallel writers.

If subagents are disabled, missing, fail, or return insufficient evidence for a high-risk judgment, preserve a concise handoff artifact and return needs_model_escalation instead of performing that judgment on the primary model.
TEXT
      ;;
    mana_explorer|mana_full_specialist|mana_worker)
      codex_agent_instructions "$1" | sed 's/Codex/OpenCode/g'
      ;;
  esac
}

install_opencode_agent_file() {
  target="$1"
  content="$2"
  if [ -e "$target" ] && [ ! -L "$target" ] && ! grep -q 'Mana-managed OpenCode agent' "$target" 2>/dev/null; then
    opencode_agent_install_warnings="${opencode_agent_install_warnings}${opencode_agent_install_warnings:+
}WARNING: not replacing non-managed OpenCode agent $target"
    return 1
  fi
  if [ -L "$target" ]; then
    rm "$target"
  fi
  printf '%s\n' "$content" > "$target"
}

ensure_opencode_agents() {
  agents_dir="$project_root/.opencode/agents"
  if ! mkdir -p "$agents_dir" 2>/dev/null; then
    opencode_agent_install_warnings="${opencode_agent_install_warnings}${opencode_agent_install_warnings:+
}WARNING: could not create $agents_dir; OpenCode delegation must fall back if agents are unavailable"
    return 0
  fi

  orchestrator_permissions="  read: allow
  glob: allow
  grep: allow
  list: allow
  bash: ask
  edit: ask
  task: allow
  webfetch: ask
  websearch: ask
  external_directory: ask"
  readonly_permissions="  read: allow
  glob: allow
  grep: allow
  list: allow
  bash: ask
  edit: deny
  task: deny
  webfetch: ask
  websearch: ask
  external_directory: ask"
  worker_permissions="  read: allow
  glob: allow
  grep: allow
  list: allow
  bash: ask
  edit: ask
  task: deny
  webfetch: ask
  websearch: ask
  external_directory: ask"

  orchestrator_content="$(render_opencode_agent "mana_orchestrator" "primary" "$opencode_model" "Mana primary orchestrator for profile routing, light evidence inventory, bounded delegation, and final synthesis." "$orchestrator_permissions" "$(opencode_agent_instructions mana_orchestrator)")"
  install_opencode_agent_file "$agents_dir/mana_orchestrator.md" "$orchestrator_content" || true

  [ "$opencode_subagents" = true ] || return 0

  explorer_content="$(render_opencode_agent "mana_explorer" "subagent" "$opencode_explorer_model" "Mana read-only repository evidence discovery and inventory." "$readonly_permissions" "$(opencode_agent_instructions mana_explorer)")"
  full_content="$(render_opencode_agent "mana_full_specialist" "subagent" "$opencode_full_model" "Mana high-risk full-model specialist for bounded architecture, database, security, contract, concurrency, and production judgments." "$readonly_permissions" "$(opencode_agent_instructions mana_full_specialist)")"
  worker_content="$(render_opencode_agent "mana_worker" "subagent" "$opencode_worker_model" "Mana bounded worker for explicitly authorized implementation or artifact-writing tasks." "$worker_permissions" "$(opencode_agent_instructions mana_worker)")"

  install_opencode_agent_file "$agents_dir/mana_explorer.md" "$explorer_content" || true
  install_opencode_agent_file "$agents_dir/mana_full_specialist.md" "$full_content" || true
  install_opencode_agent_file "$agents_dir/mana_worker.md" "$worker_content" || true
}

ensure_codex_agents() {
  [ "$codex_subagents" = true ] || return 0
  agents_dir="$project_root/.codex/agents"
  if ! mkdir -p "$agents_dir" 2>/dev/null; then
    codex_agent_install_warnings="${codex_agent_install_warnings}${codex_agent_install_warnings:+
}WARNING: could not create $agents_dir; Codex subagent delegation must fall back if agents are unavailable"
    return 0
  fi

  explorer_content="$(render_codex_agent "mana_explorer" "$codex_explorer_model" "medium" "read-only" "Mana read-only repository evidence discovery and inventory." "$(codex_agent_instructions mana_explorer)")"
  full_content="$(render_codex_agent "mana_full_specialist" "$codex_full_model" "high" "read-only" "Mana high-risk full-model specialist for bounded architecture, database, security, contract, concurrency, and production judgments." "$(codex_agent_instructions mana_full_specialist)")"
  worker_content="$(render_codex_agent "mana_worker" "$codex_worker_model" "medium" "workspace-write" "Mana bounded worker for explicitly authorized implementation or artifact-writing tasks." "$(codex_agent_instructions mana_worker)")"

  install_codex_agent_file "$agents_dir/mana-explorer.toml" "$explorer_content" || true
  install_codex_agent_file "$agents_dir/mana-full-specialist.toml" "$full_content" || true
  install_codex_agent_file "$agents_dir/mana-worker.toml" "$worker_content" || true
}

echo "Profile: $profile"
echo "This profile renderer validates Mana freshness and prints the configured profile."
echo "Use --codex, --claude, or --opencode to execute the profile through a runner."
if [ "$runner" = "codex" ]; then
  echo "Codex model: $codex_model"
  echo "Codex explorer model: $codex_explorer_model"
  echo "Codex full specialist model: $codex_full_model"
  echo "Codex worker model: $codex_worker_model"
  echo "Codex model policy: $codex_model_policy"
  echo "Codex subagents: $codex_subagents"
  echo "Codex agent limits: max_threads=$codex_max_threads max_depth=$codex_max_depth interrupt_message=false"
  if [ -n "$model_escalation_skills" ]; then
    echo "Codex delegation/escalation candidate skills: $model_escalation_skills"
    echo "Model routing warning: $model_routing_warning"
  else
    echo "Codex delegation/escalation candidate skills: none"
  fi
fi
if [ "$runner" = "claude" ]; then
  echo "Claude model: $claude_model"
  echo "Claude explorer model: $claude_explorer_model"
  echo "Claude full specialist model: $claude_full_model"
  echo "Claude worker model: $claude_worker_model"
  echo "Claude subagents: $claude_subagents"
  echo "Claude delegation limit: max_direct_subagents=$claude_max_threads, max_depth=1"
  if [ -n "$model_escalation_skills" ]; then
    echo "Claude delegation/escalation candidate skills: $model_escalation_skills"
    echo "Model routing warning: $model_routing_warning"
  else
    echo "Claude delegation/escalation candidate skills: none"
  fi
fi
if [ "$runner" = "opencode" ]; then
  echo "OpenCode model: $opencode_model"
  echo "OpenCode explorer model: $opencode_explorer_model"
  echo "OpenCode full specialist model: $opencode_full_model"
  echo "OpenCode worker model: $opencode_worker_model"
  echo "OpenCode subagents: $opencode_subagents"
  echo "OpenCode agent limits: max_threads=$opencode_max_threads max_depth=1"
  if [ -n "$model_escalation_skills" ]; then
    echo "OpenCode delegation/escalation candidate skills: $model_escalation_skills"
    echo "Model routing warning: $model_routing_warning"
  else
    echo "OpenCode delegation/escalation candidate skills: none"
  fi
fi
sed -n '1,220p' "$file"
echo
if [ -n "$pr_number" ] || [ "$publish_high_risk_comments" = true ] || [ "$service_discovery_approved" = true ] || [ -n "$jira_keys" ]; then
  echo "Profile input overrides:"
  if [ -n "$pr_number" ]; then
    echo "  pr_number: $pr_number"
  fi
  if [ -n "$jira_keys" ]; then
    echo "  jira_issue_keys: $jira_keys"
    echo "  jira_key_regex: $jira_key_regex"
  fi
  if [ "$publish_high_risk_comments" = true ]; then
    echo "  publish_high_risk_comments: true"
  fi
  if [ "$service_discovery_approved" = true ]; then
    echo "  service_discovery_approved: true"
  fi
  echo
fi
if [ "$jira_mcp_configured" = true ] && [ "$jira_mcp_config_source" = "env_file" ]; then
  echo "Jira MCP env: configured ($jira_env_file)"
elif [ "$jira_mcp_configured" = true ]; then
  echo "Jira MCP env: configured from environment variables"
else
  echo "Jira MCP env: not configured; jira_read agents must use local artifacts or ask for credentials."
fi
echo "Workspace note: profiles use the project-local .mana workspace. Run scripts/mana-workspace.sh init in the target project before agent execution when artifacts must be persisted."

hooks_config=""
if [ -n "$project_root" ] && [ -f "$project_root/.mana/global/hooks-config.yaml" ]; then
  hooks_config="$project_root/.mana/global/hooks-config.yaml"
fi

if [ -n "$hooks_config" ]; then
  trigger="$(grep '^trigger:' "$file" | awk '{print $2}' | tr -d '"' | head -n 1)"
  if [ -n "$trigger" ]; then
    disabled_skills="$(awk -v section="$trigger" '
      /^hooks:/ { in_hooks=1; next }
      in_hooks && $0 ~ "^  " section ":" { in_section=1; next }
      in_hooks && in_section && /^    disabled_skills:/ { in_skills=1; in_agents=0; next }
      in_hooks && in_section && /^    disabled_agents:/ { in_agents=1; in_skills=0; next }
      in_hooks && in_section && in_skills && /^      - / { sub(/^      - /, ""); print }
      in_hooks && in_section && /^  [a-z_]+:/ { in_section=0; in_skills=0; in_agents=0 }
    ' "$hooks_config")"
    disabled_agents="$(awk -v section="$trigger" '
      /^hooks:/ { in_hooks=1; next }
      in_hooks && $0 ~ "^  " section ":" { in_section=1; next }
      in_hooks && in_section && /^    disabled_skills:/ { in_skills=1; in_agents=0; next }
      in_hooks && in_section && /^    disabled_agents:/ { in_agents=1; in_skills=0; next }
      in_hooks && in_section && in_agents && /^      - / { sub(/^      - /, ""); print }
      in_hooks && in_section && /^  [a-z_]+:/ { in_section=0; in_skills=0; in_agents=0 }
    ' "$hooks_config")"

    if [ -n "$disabled_skills" ] || [ -n "$disabled_agents" ]; then
      echo
      echo "Project hooks-config.yaml overrides ($project_root/.mana/global/hooks-config.yaml):"
      if [ -n "$disabled_skills" ]; then
        echo "  Disabled skills for $trigger:"
        echo "$disabled_skills" | while IFS= read -r s; do echo "    DISABLED: $s"; done
      fi
      if [ -n "$disabled_agents" ]; then
        echo "  Disabled agents for $trigger:"
        echo "$disabled_agents" | while IFS= read -r a; do echo "    DISABLED: $a"; done
      fi
    else
      echo
      echo "Project hooks-config.yaml: no overrides for $trigger (all framework defaults active)."
    fi
  fi
fi

if [ "$render_only" = true ] || [ "${MANA_PROFILE_RUNNING:-}" = "1" ] || [ -z "$runner" ]; then
  if [ "$render_only" = true ]; then
    echo
    echo "Execution note: --render-only requested; no runner was started."
  elif [ "${MANA_PROFILE_RUNNING:-}" = "1" ]; then
    echo
    echo "Execution note: already inside a Mana profile runner; no nested runner was started."
  else
    echo
    echo "Execution note: no runner flag was provided, so no runner was started."
    echo "Run with --codex, --claude, or --opencode to execute the profile through that runner."
  fi
  exit 0
fi

legacy_prompt="$(cat <<PROMPT
Run the Mana profile '$profile' in this repository.

Repository root: $project_root
Mana framework root: $root
Selected runner: $runner
Codex initial model: $codex_model
Codex full model: $codex_full_model
Codex explorer model: $codex_explorer_model
Codex worker model: $codex_worker_model
Codex model policy: $codex_model_policy
Codex subagents enabled: $codex_subagents
Codex agent runtime limits: max_threads=$codex_max_threads, max_depth=$codex_max_depth, interrupt_message=false
Model delegation/escalation candidate skills: ${model_escalation_skills:-none}
Model routing warning: ${model_routing_warning:-none}
Claude initial model: $claude_model
Claude full model: $claude_full_model
Claude explorer model: $claude_explorer_model
Claude worker model: $claude_worker_model
Claude subagents enabled: $claude_subagents
Claude delegation limits: max_direct_subagents=$claude_max_threads, max_depth=1
OpenCode initial model: $opencode_model
OpenCode full model: $opencode_full_model
OpenCode explorer model: $opencode_explorer_model
OpenCode worker model: $opencode_worker_model
OpenCode subagents enabled: $opencode_subagents
OpenCode agent runtime limits: max_threads=$opencode_max_threads, max_depth=1
Profile input overrides:
- pr_number: ${pr_number:-}
- publish_high_risk_comments: $publish_high_risk_comments
- service_discovery_approved: $service_discovery_approved
- jira_issue_keys: ${jira_keys:-}
- jira_key_regex: $jira_key_regex
- current_branch: ${current_branch:-}
- jira_mcp_configured: $jira_mcp_configured
- jira_mcp_config_source: ${jira_mcp_config_source:-none}

Instructions:
- Do not run './mana profile $profile' or 'scripts/run-profile.sh $profile' again; this command already rendered the profile and would recurse.
- Read '.mana/links/profiles/$profile.yaml' if present, otherwise '$file'.
- Follow docs/policies/model-tier-routing-policy.md for provider-neutral economy/full routing, downgrade behavior, and Jira/tool access treatment.
- If the selected runner is Codex, use the economy root model for routing, evidence inventory, low-risk checks, delegation, aggregation, and final synthesis. Treat the listed Codex delegation/escalation candidate skills as full-model candidates, not mandatory work.
- Codex runtime agents are capability classes only. Mana agents under agents/ remain semantic workflow orchestrators, and Mana skills under skills/ remain reusable domain capabilities. Do not map every Mana agent or every Mana skill to a separate Codex subagent.
- Codex subagent orchestration is enabled: $codex_subagents. When enabled and available, delegate required high-risk, explicitly full-tier, noisy, or beyond-root-confidence work to project-scoped custom agents: mana_explorer, mana_full_specialist, and mana_worker. Child agents must not delegate further.
- Inspect candidate skill metadata using progressive loading, determine which skills are truly required by current evidence, group related work by risk domain or execution phase, spawn no more than $codex_max_threads direct subagents, avoid one subagent per skill, prefer parallel delegation only for independent read-heavy work, wait for delegated work to finish, collect compact structured summaries, and synthesize the final Mana output.
- Delegation grouping policy is bounded and deterministic: requirements (story quality, epic/story goal extraction, acceptance-criteria testability), source (source impact, symbol and call-path mapping, technical task decomposition), tests (test inventory, green-border planning, missing-test analysis), architecture (architecture risk, NFR impact, transaction and concurrency review), contracts (API/event contracts and cross-service compatibility), database (schema and Liquibase production risk), security (trust boundaries, secrets, authorization, dependency-security evidence), operations (release, rollback, continuity, incident and production risk), documentation, and implementation.
- Use mana_explorer for read-heavy evidence discovery, source impact mapping, symbol/call-path discovery, test inventory, contract inventory, dependency evidence, diff classification, and locating relevant Mana or project files.
- Use mana_full_specialist for architecture, security, database, concurrency, cross-service, production, transactional, backwards-compatibility, model_tier: full, or large/ambiguous diff judgment. The root orchestrator must not directly perform deep high-risk analysis in those domains.
- Use mana_worker only when the selected Mana profile explicitly permits source modification. Never infer write permission from a writable sandbox. Do not run mana_worker for analysis-only profiles, and never run parallel writers against the same working tree.
- Wait for delegated work and aggregate only compact summaries and artifact paths. Do not import raw tool transcripts into the root context.
- If Codex subagents are disabled, the installed Codex runtime cannot discover custom agents, spawning fails, a specialist returns insufficient evidence, or a high-risk judgment remains unsupported, preserve a concise handoff artifact in the workspace when possible and return status \`needs_model_escalation\`. Tell the user to rerun the same profile with \`MANA_CODEX_MODEL=$codex_full_model\` or \`--codex-model $codex_full_model\`. Do not silently continue a high-risk judgment on the economy model.
- When Codex subagents are disabled, preserve the legacy economy-first/manual-escalation behavior: do not pretend a specialist ran, and stop with \`needs_model_escalation\` before deep analysis of required full-tier or high-risk work.
- If the selected runner is Claude Code, use the mana-orchestrator economy root agent for routing, evidence inventory, low-risk checks, delegation, aggregation, and final synthesis. Treat the listed delegation/escalation candidate skills as full-model candidates, not mandatory work.
- Claude Code runtime agents are capability classes only. Mana agents under agents/ remain semantic workflow orchestrators, and Mana skills under skills/ remain reusable domain capabilities. Do not map every Mana agent or every Mana skill to a separate Claude Code subagent.
- Claude Code subagent orchestration is enabled: $claude_subagents. When enabled and available, delegate required high-risk, explicitly full-tier, noisy, or beyond-root-confidence work to project-scoped agents: mana-explorer, mana-full-specialist, and mana-worker. Child agents do not have the Agent tool and must not delegate further.
- For Claude Code, spawn no more than $claude_max_threads direct subagents in total, no more than one per capability class, avoid one subagent per skill, prefer parallel delegation only for independent read-heavy work, wait for delegated work to finish, collect compact structured summaries, and synthesize the final Mana output.
- Use mana-explorer for read-heavy evidence discovery, source impact mapping, symbol/call-path discovery, test inventory, contract inventory, dependency evidence, diff classification, and locating relevant Mana or project files.
- Use mana-full-specialist for architecture, security, database, concurrency, cross-service, production, transactional, backwards-compatibility, model_tier: full, or large/ambiguous diff judgment. The root orchestrator must not directly perform deep high-risk analysis in those domains.
- Use mana-worker only when the selected Mana profile explicitly permits source modification. Never infer write permission from tool access. Do not run mana-worker for analysis-only profiles, and never run parallel writers against the same working tree.
- If Claude Code subagents are disabled, the installed Claude Code runtime cannot discover custom agents, spawning fails, a specialist returns insufficient evidence, or a high-risk judgment remains unsupported, preserve a concise handoff artifact in the workspace when possible and return status \`needs_model_escalation\`. Tell the user to rerun the same profile with \`MANA_CLAUDE_MODEL=$claude_full_model\` or \`--claude-model $claude_full_model\`. Do not silently continue a high-risk judgment on the economy model.
- When Claude Code subagents are disabled, preserve manual-escalation behavior: do not pretend a specialist ran, and stop with \`needs_model_escalation\` before deep analysis of required full-tier or high-risk work.
- If the selected runner is OpenCode, use the mana_orchestrator primary agent for routing, evidence inventory, low-risk checks, delegation, aggregation, and final synthesis. Treat the listed delegation/escalation candidate skills as full-model candidates, not mandatory work.
- OpenCode runtime agents are capability classes only. Mana agents under agents/ remain semantic workflow orchestrators, and Mana skills under skills/ remain reusable domain capabilities. Do not map every Mana agent or every Mana skill to a separate OpenCode subagent.
- OpenCode subagent orchestration is enabled: $opencode_subagents. When enabled and available, delegate required high-risk, explicitly full-tier, noisy, or beyond-primary-confidence work to project-scoped agents: mana_explorer, mana_full_specialist, and mana_worker. Child agents must not delegate further.
- For OpenCode, spawn no more than $opencode_max_threads direct subagents, avoid one subagent per skill, prefer parallel delegation only for independent read-heavy work, wait for delegated work to finish, collect compact structured summaries, and synthesize the final Mana output.
- If OpenCode subagents are disabled, the installed OpenCode runtime cannot discover custom agents, spawning fails, a specialist returns insufficient evidence, or a high-risk judgment remains unsupported, preserve a concise handoff artifact in the workspace when possible and return status \`needs_model_escalation\`. Tell the user to rerun the same profile with \`MANA_OPENCODE_MODEL=$opencode_full_model\` or \`--opencode-model $opencode_full_model\`. Do not silently continue a high-risk judgment on the primary model.
- When OpenCode subagents are disabled, preserve manual-escalation behavior: do not pretend a specialist ran, and stop with \`needs_model_escalation\` before deep analysis of required full-tier or high-risk work.
- Follow docs/standards/agent-skill-output-standard.md. Instruction priority is: current human instruction, profile YAML, agent AGENT.md, playbook.md, loaded skill SKILL.md, then global service context. Never weaken safety, external-write, or human-approval rules.
- Use the Mana operating loop: identify the human decision, resolve inputs/workspace/requirement source/branch or PR target/diff base, inventory evidence, classify risk domains, load only needed skills, then report status, findings, evidence, artifacts, and approvals.
- Read only the selected agent AGENT.md and playbook.md. For candidate skills, use progressive load-light reading first: front matter, title, Purpose, When To Use It, When Not To Use It, Inputs, Outputs, Execution Logic, and Decision Rules. Load only the primary skill required to start the profile, then deep-load specialist skills only when the filtered inputs show that their risk domain is relevant or the load-light pass is insufficient. Do not read every listed skill, every example, or unrelated agent folders up front.
- Use compact caveman working notes while analyzing: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts. Maintain a context budget: keep a short working summary with objective, base branch or PR, issue keys, workspace path, checked evidence, open hypotheses, discarded hypotheses, and next checks instead of accumulating raw transcripts, full diffs, repeated file dumps, complete Jira payloads, full PR threads, full skill files, or copied tool output. Convert working notes into the structured sections required by docs/standards/agent-skill-output-standard.md.
- Resolve the active .mana workspace and write the profile artifacts there using the agent routing rules.
- Load .mana/global/service-mission.md, architecture.md, and engineering-guards.md when present before analysis.
- If the profile or agent allows jira_read and jira_issue_keys is non-empty, read those Jira issues as requirement context through the configured Jira MCP server before drawing requirement, plan-drift, risk, or review conclusions. Treat Jira as read-only. Do not expose tokens, transition issues, write comments, or update tickets.
- For epic-analysis, treat the explicit Jira issue key as the epic target: refresh or load its normalized epic story pack before judging structure, sibling overlap, contradictions, or implementation order. Build the implementation graph from Jira and the existing service KB first. Only if service_discovery_approved is true may you inspect, read-only, the services explicitly named by the epic or its stories; otherwise do not traverse repositories or services and mark dependent edges unverified. Never treat shared service names as proof of a dependency.
- In a Mana-linked project, prefer './mana jira-mcp --get-issue <KEY>' for fast read-only Jira story retrieval. Use './mana jira-mcp --check-access --issue <KEY>' only to diagnose credentials or permissions.
- Treat Jira summary, description, status, standard attributes, visible custom fields, readable properties, linked context, and all readable comments as requirement evidence. Use the complete read-only issue payload when available; report inaccessible fields, properties, or comment pages as gaps. For feasibility/planning profiles, check whether the requested story is coherent, implementable, testable, and has the owners/approvals needed to start. For review/validation/premortem/PR profiles, compare the branch or PR changes against the story and report missing requested behavior, unrequested scope, contradicted acceptance criteria, and tests that do not prove the story. Do not treat code correctness as sufficient when it diverges from the story.
- Jira issue keys are generic and project-configurable. Use the provided jira_key_regex only as discovery input; do not assume a project-specific prefix. If no Jira issue keys are found, continue with repository and Mana artifacts unless the selected profile requires story context.
- If jira_issue_keys are present but Jira MCP is unavailable or unauthenticated, report the access gap and fall back to local .mana planning artifacts or ask the user for story context when needed.
- For jessica-fletcher, resolve the main branch first, compare the full local branch changes against it, include uncommitted working-tree changes, and stop with a clear question if the main branch is ambiguous.
- For any profile using branch or code diff evidence, resolve and report the comparison base. Prefer explicit input, then origin/HEAD, then a single credible primary branch. If ambiguous, ask the user; do not default to main.
- For any profile using branch or code diff evidence, start with a filtered diff inventory, exclude Mana/bootstrap noise, classify changed files by risk domain, and read only files needed to validate plausible blocker or warning hypotheses. If the filtered diff is larger than roughly 80 files or 2,000 changed lines, ask the user to choose a review scope instead of scanning the whole repository.
- Exclude Mana framework/bootstrap noise from production findings and evidence: .mana/**, AGENTS.md, CLAUDE.md, mana, and Mana-only .gitignore or env ignore changes. Mention them only as operational setup notes when relevant.
- If a profile or agent allows github_read, treat authenticated gh CLI as an optional read-only helper for PR metadata, diffs, files, checks, reviews, paginated general/inline comments, and GraphQL review-thread resolution state. Validate unresolved or unknown threads against the current diff; never infer a resolved state for comments that have no platform thread state. Do not approve, comment, merge, edit, label, assign, or otherwise write through gh without explicit human approval.
- If the selected profile is requested-pr-review and pr_number is set, analyze that pull request directly instead of discovering all PRs where the user is a requested reviewer.
- If the selected profile is requested-pr-review and publish_high_risk_comments is true, this flag is explicit human approval to publish exactly one gh PR comment on the selected PR containing only blocker or high-criticality findings found by this run. Do not publish medium/low findings. Do not approve, request changes, merge, edit, label, assign, push, or trigger CI.
- Do not commit, push, deploy, trigger CI, write to external systems, or make destructive changes, except for the limited requested-pr-review high-risk PR comment explicitly allowed above.
- Final response must summarize status, blockers, warnings, artifact paths, and any required human approval.
PROMPT
)"

prompt="$(cat <<PROMPT
Run Mana profile '$profile' in this repository.

Repository root: $project_root
Framework root: $root
Runner: $runner
Profile inputs: pr_number=${pr_number:-none}; jira_issue_keys=${jira_keys:-none}; current_branch=${current_branch:-detached}; jira_mcp_configured=$jira_mcp_configured; publish_high_risk_comments=$publish_high_risk_comments; service_discovery_approved=$service_discovery_approved.
Model routing: root=economy; full-tier candidates=${model_escalation_skills:-none}; escalation warning=${model_routing_warning:-none}.
Runtime limits: Codex subagents=$codex_subagents/$codex_max_threads; Claude subagents=$claude_subagents/$claude_max_threads; OpenCode subagents=$opencode_subagents/$opencode_max_threads.

Read '.mana/links/profiles/$profile.yaml' if present, otherwise '$file'. Follow docs/policies/runtime-execution-contract.md and docs/standards/output-contract.md. The profile's skill_activation block is authoritative: begin with baseline skills, then load a conditional skill only after filtered evidence matches its signal. Use skills/index.yaml for metadata; read only the selected skill bodies.

Read only the selected agent AGENT.md and playbook, core service-context files, and evidence required for a concrete hypothesis. Do not recursively invoke Mana. Keep evidence compact and return artifact paths rather than transcripts.

The root model may route, inventory, perform low-risk checks, and synthesize. It must delegate required high-risk or full-tier work only when relevant and bounded. If needed escalation is unavailable or insufficient, return needs_model_escalation rather than guessing. Do not write source or external systems unless the profile explicitly permits it; do not commit, push, deploy, trigger CI, or change Jira/GitHub state except the narrowly approved requested-pr-review comment.

For Jira, use read-only access when issue keys are available; report an access gap if unavailable. For PR or diff work, resolve the comparison base, exclude Mana bootstrap noise, and request scope if the filtered diff exceeds 80 files or 2,000 lines. Final output: status, blockers, warnings, evidence/artifact paths, and required approvals.
PROMPT
)"

run_codex() {
  ensure_codex_agents
  if [ -n "$codex_agent_install_warnings" ]; then
    printf '%s\n' "$codex_agent_install_warnings" >&2
  fi

  codex_args=(
    --ask-for-approval on-request
    exec
    --model "$codex_model"
    --cd "$project_root"
    --sandbox workspace-write
    -c "agents.max_threads=$codex_max_threads"
    -c "agents.max_depth=$codex_max_depth"
    -c "agents.interrupt_message=false"
  )

  if [ "$jira_mcp_configured" = true ] && [ "$jira_mcp_config_source" = "env_file" ]; then
    codex_args+=(
      -c "mcp_servers.jira.command=\"$root/scripts/run-jira-mcp-docker.sh\""
      -c "mcp_servers.jira.args=[\"--env-file\",\"$jira_env_file\"]"
    )
  elif [ "$jira_mcp_configured" = true ]; then
    codex_args+=(
      -c "mcp_servers.jira.command=\"$root/scripts/run-jira-mcp-docker.sh\""
      -c "mcp_servers.jira.args=[]"
    )
  fi

  MANA_PROFILE_RUNNING=1 codex "${codex_args[@]}" "$prompt"
}

run_claude() {
  ensure_claude_agents
  if [ -n "$claude_agent_install_warnings" ]; then
    printf '%s\n' "$claude_agent_install_warnings" >&2
  fi

  claude_args=(
    -p
    --agent mana-orchestrator
    --model "$claude_model"
    --permission-mode default
  )

  MANA_PROFILE_RUNNING=1 claude "${claude_args[@]}" "$prompt"
}

run_opencode() {
  ensure_opencode_agents
  if [ -n "$opencode_agent_install_warnings" ]; then
    printf '%s\n' "$opencode_agent_install_warnings" >&2
  fi

  opencode_args=(
    run
    --dir "$project_root"
    --model "$opencode_model"
    --agent mana_orchestrator
  )

  MANA_PROFILE_RUNNING=1 opencode "${opencode_args[@]}" "$prompt"
}

case "$runner" in
  codex)
    if ! command -v codex >/dev/null 2>&1; then
      echo "ERROR: --codex requested, but codex was not found in PATH" >&2
      exit 1
    fi

    echo
    echo "Starting Codex runner for profile: $profile"
    run_codex
    ;;
  claude)
    if ! command -v claude >/dev/null 2>&1; then
      echo "ERROR: --claude requested, but claude was not found in PATH" >&2
      exit 1
    fi

    echo
    echo "Starting Claude runner for profile: $profile"
    cd "$project_root" || exit 1
    run_claude
    ;;
  opencode)
    if ! command -v opencode >/dev/null 2>&1; then
      echo "ERROR: --opencode requested, but opencode was not found in PATH" >&2
      exit 1
    fi

    echo
    echo "Starting OpenCode runner for profile: $profile"
    run_opencode
    ;;
  *)
    echo "ERROR: unsupported runner: $runner" >&2
    exit 2
    ;;
esac
