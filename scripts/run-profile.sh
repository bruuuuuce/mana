#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
profile=""
project_root=""
render_only=false
runner=""
pr_number=""
publish_high_risk_comments=false
jira_keys=""
jira_key_regex="${MANA_JIRA_KEY_REGEX:-[A-Z][A-Z0-9]+-[0-9]+}"
jira_env_file="${MANA_JIRA_MCP_ENV:-}"
jira_mcp_configured=false
jira_mcp_config_source=""

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-profile.sh <profile-name> [options]

Options:
  --project-root <path>          Target project root. Defaults to current directory.
  --render-only                  Render the profile and never start a runner.
  --codex                        Execute the rendered profile through Codex.
  --claude                       Execute the rendered profile through Claude Code.
  --pr, --pr-number <value>      Pull request number or URL for requested-pr-review.
  --jira-key, --jira-issue <KEY> Add an explicit Jira issue key.
  --jira-key-regex <regex>       Override branch issue-key discovery.
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
    --pr|--pr-number)
      pr_number="${2:-}"
      [ -n "$pr_number" ] || { echo "ERROR: $1 requires a pull request number or URL" >&2; exit 2; }
      shift 2
      ;;
    --publish-high-risk-comments)
      publish_high_risk_comments=true
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

if [ -z "$project_root" ]; then
  project_root="$(pwd)"
fi

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

echo "Profile: $profile"
echo "This profile renderer validates Mana freshness and prints the configured profile."
echo "Use --codex or --claude to execute the profile through a runner."
sed -n '1,220p' "$file"
echo
if [ -n "$pr_number" ] || [ "$publish_high_risk_comments" = true ] || [ -n "$jira_keys" ]; then
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
    echo "Run with --codex or --claude to execute the profile through that runner."
  fi
  exit 0
fi

prompt="$(cat <<PROMPT
Run the Mana profile '$profile' in this repository.

Repository root: $project_root
Mana framework root: $root
Selected runner: $runner
Profile input overrides:
- pr_number: ${pr_number:-}
- publish_high_risk_comments: $publish_high_risk_comments
- jira_issue_keys: ${jira_keys:-}
- jira_key_regex: $jira_key_regex
- current_branch: ${current_branch:-}
- jira_mcp_configured: $jira_mcp_configured
- jira_mcp_config_source: ${jira_mcp_config_source:-none}

Instructions:
- Do not run './mana profile $profile' or 'scripts/run-profile.sh $profile' again; this command already rendered the profile and would recurse.
- Read '.mana/links/profiles/$profile.yaml' if present, otherwise '$file'.
- Follow docs/standards/agent-skill-output-standard.md. Instruction priority is: current human instruction, profile YAML, agent AGENT.md, playbook.md, loaded skill SKILL.md, then global service context. Never weaken safety, external-write, or human-approval rules.
- Use the Mana operating loop: identify the human decision, resolve inputs/workspace/requirement source/branch or PR target/diff base, inventory evidence, classify risk domains, load only needed skills, then report status, findings, evidence, artifacts, and approvals.
- Read only the selected agent AGENT.md and playbook.md. For candidate skills, use progressive load-light reading first: front matter, title, Purpose, When To Use It, When Not To Use It, Inputs, Outputs, Execution Logic, and Decision Rules. Load only the primary skill required to start the profile, then deep-load specialist skills only when the filtered inputs show that their risk domain is relevant or the load-light pass is insufficient. Do not read every listed skill, every example, or unrelated agent folders up front.
- Use compact caveman working notes while analyzing: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts. Maintain a context budget: keep a short working summary with objective, base branch or PR, issue keys, workspace path, checked evidence, open hypotheses, discarded hypotheses, and next checks instead of accumulating raw transcripts, full diffs, repeated file dumps, complete Jira payloads, full PR threads, full skill files, or copied tool output. Convert working notes into the structured sections required by docs/standards/agent-skill-output-standard.md.
- Resolve the active .mana workspace and write the profile artifacts there using the agent routing rules.
- Load .mana/global/service-mission.md, architecture.md, and engineering-guards.md when present before analysis.
- If the profile or agent allows jira_read and jira_issue_keys is non-empty, read those Jira issues as requirement context through the configured Jira MCP server before drawing requirement, plan-drift, risk, or review conclusions. Treat Jira as read-only. Do not expose tokens, transition issues, write comments, or update tickets.
- In a Mana-linked project, prefer './mana jira-mcp --get-issue <KEY>' for fast read-only Jira story retrieval. Use './mana jira-mcp --check-access --issue <KEY>' only to diagnose credentials or permissions.
- Treat Jira story text, acceptance criteria, linked context, and relevant comments as requirement evidence. For feasibility/planning profiles, check whether the requested story is coherent, implementable, testable, and has the owners/approvals needed to start. For review/validation/premortem/PR profiles, compare the branch or PR changes against the story and report missing requested behavior, unrequested scope, contradicted acceptance criteria, and tests that do not prove the story. Do not treat code correctness as sufficient when it diverges from the story.
- Jira issue keys are generic and project-configurable. Use the provided jira_key_regex only as discovery input; do not assume a project-specific prefix. If no Jira issue keys are found, continue with repository and Mana artifacts unless the selected profile requires story context.
- If jira_issue_keys are present but Jira MCP is unavailable or unauthenticated, report the access gap and fall back to local .mana planning artifacts or ask the user for story context when needed.
- For jessica-fletcher, resolve the main branch first, compare the full local branch changes against it, include uncommitted working-tree changes, and stop with a clear question if the main branch is ambiguous.
- For any profile using branch or code diff evidence, resolve and report the comparison base. Prefer explicit input, then origin/HEAD, then a single credible primary branch. If ambiguous, ask the user; do not default to main.
- For any profile using branch or code diff evidence, start with a filtered diff inventory, exclude Mana/bootstrap noise, classify changed files by risk domain, and read only files needed to validate plausible blocker or warning hypotheses. If the filtered diff is larger than roughly 80 files or 2,000 changed lines, ask the user to choose a review scope instead of scanning the whole repository.
- Exclude Mana framework/bootstrap noise from production findings and evidence: .mana/**, AGENTS.md, CLAUDE.md, mana, and Mana-only .gitignore or env ignore changes. Mention them only as operational setup notes when relevant.
- If a profile or agent allows github_read, treat authenticated gh CLI as an optional read-only helper for PR metadata, diffs, files, checks, and reviewer requests. Do not approve, comment, merge, edit, label, assign, or otherwise write through gh without explicit human approval.
- If the selected profile is requested-pr-review and pr_number is set, analyze that pull request directly instead of discovering all PRs where the user is a requested reviewer.
- If the selected profile is requested-pr-review and publish_high_risk_comments is true, this flag is explicit human approval to publish exactly one gh PR comment on the selected PR containing only blocker or high-criticality findings found by this run. Do not publish medium/low findings. Do not approve, request changes, merge, edit, label, assign, push, or trigger CI.
- Do not commit, push, deploy, trigger CI, write to external systems, or make destructive changes, except for the limited requested-pr-review high-risk PR comment explicitly allowed above.
- Final response must summarize status, blockers, warnings, artifact paths, and any required human approval.
PROMPT
)"

run_codex() {
  if [ "$jira_mcp_configured" = true ] && [ "$jira_mcp_config_source" = "env_file" ]; then
    MANA_PROFILE_RUNNING=1 codex --ask-for-approval on-request exec --cd "$project_root" --sandbox workspace-write \
      -c "mcp_servers.jira.command=\"$root/scripts/run-jira-mcp-docker.sh\"" \
      -c "mcp_servers.jira.args=[\"--env-file\",\"$jira_env_file\"]" \
      "$prompt"
  elif [ "$jira_mcp_configured" = true ]; then
    MANA_PROFILE_RUNNING=1 codex --ask-for-approval on-request exec --cd "$project_root" --sandbox workspace-write \
      -c "mcp_servers.jira.command=\"$root/scripts/run-jira-mcp-docker.sh\"" \
      -c "mcp_servers.jira.args=[]" \
      "$prompt"
  else
    MANA_PROFILE_RUNNING=1 codex --ask-for-approval on-request exec --cd "$project_root" --sandbox workspace-write "$prompt"
  fi
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
    MANA_PROFILE_RUNNING=1 claude -p --permission-mode default "$prompt"
    ;;
  *)
    echo "ERROR: unsupported runner: $runner" >&2
    exit 2
    ;;
esac
