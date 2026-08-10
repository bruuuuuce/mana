#!/usr/bin/env bash
set -eu

usage() {
  cat <<'USAGE'
Usage:
  /path/to/mana/scripts/bootstrap-project.sh [options]

Run this from the target project root to link Mana without copying the whole
repository.

Options:
  --project-root <path>      Target project root. Defaults to current directory.
  --mana-root <path>    Mana root. Defaults to this script's parent repo.
  --feature <id>             Initialize the active Mana workspace for a feature/story/epic id.
  --purpose <name>           Workspace purpose. Defaults to mana-bootstrap.
  --force                    Refresh generated wrapper files and replace managed symlinks.
  --no-links                 Do not create .mana links to framework folders.
  --no-jira-env              Do not create .mana/jira-mcp.env from the example template.
  --no-gitignore             Do not update project .gitignore.
  --help                     Show this help.

Created in the target project:
  .mana/env                   Mana path configuration.
  .mana/README.md             Local usage notes.
  .mana/links/*               Symlinks to framework skills, agents, profiles, docs, templates, mcp.
  .codex/agents/mana-*.toml    Mana-managed Codex runtime subagents.
  .claude/agents/mana-*.md     Mana-managed Claude Code runtime agents.
  .opencode/agents/mana_*.md   Mana-managed OpenCode runtime agents.
  .mana/jira-mcp.env          Local Jira MCP env template, ignored by Git.
  mana                        Local command wrapper for common Mana commands.
  AGENTS.md                   Codex auto-loaded runner instructions.
  CLAUDE.md                   Claude Code auto-loaded runner instructions.
  .mana/                      Project-local artifact workspace.

Examples:
  /opt/mana/scripts/bootstrap-project.sh
  /opt/mana/scripts/bootstrap-project.sh --feature PROJ-1234
  ./mana profile jessica-fletcher
  ./mana workspace status
  ./mana jira-mcp --dry-run
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

script_dir="$(cd "$(dirname "$0")" && pwd)"
default_framework_root="$(cd "$script_dir/.." && pwd)"
project_root="$(pwd)"
framework_root="$default_framework_root"
feature=""
purpose="mana-bootstrap"
force=false
create_links=true
create_jira_env=true
update_gitignore=true

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root)
      project_root="${2:-}"
      [ -n "$project_root" ] || fail "--project-root requires a path"
      shift 2
      ;;
    --mana-root)
      framework_root="${2:-}"
      [ -n "$framework_root" ] || fail "--mana-root requires a path"
      shift 2
      ;;
    --feature)
      feature="${2:-}"
      [ -n "$feature" ] || fail "--feature requires an id"
      shift 2
      ;;
    --purpose)
      purpose="${2:-}"
      [ -n "$purpose" ] || fail "--purpose requires a value"
      shift 2
      ;;
    --force)
      force=true
      shift
      ;;
    --no-links)
      create_links=false
      shift
      ;;
    --no-jira-env)
      create_jira_env=false
      shift
      ;;
    --no-gitignore)
      update_gitignore=false
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

project_root="$(cd "$project_root" && pwd)"
framework_root="$(cd "$framework_root" && pwd)"

[ -d "$framework_root/scripts" ] || fail "Mana root does not contain scripts/: $framework_root"
[ -f "$framework_root/scripts/mana-workspace.sh" ] || fail "missing mana-workspace.sh in Mana root"
[ -f "$framework_root/scripts/run-profile.sh" ] || fail "missing run-profile.sh in Mana root"

mkdir -p "$project_root/.mana" "$project_root/.mana/links"

write_file() {
  file="$1"
  content="$2"
  if [ "$force" = true ] || [ ! -f "$file" ]; then
    printf '%s\n' "$content" > "$file"
  fi
}

write_file "$project_root/.mana/env" "MANA_HOME=\"$framework_root\"
MANA_PROJECT_ROOT=\"$project_root\""

is_mana_managed_file() {
  file="$1"
  [ -f "$file" ] && grep -q 'Mana-managed' "$file" 2>/dev/null
}

install_managed_file_or_link() {
  source_file="$1"
  target_file="$2"
  mode="$3"

  if [ -e "$target_file" ] || [ -L "$target_file" ]; then
    if [ -L "$target_file" ]; then
      if [ "$force" = true ]; then
        rm "$target_file"
      else
        return 0
      fi
    elif is_mana_managed_file "$target_file"; then
      if [ "$force" = true ]; then
        rm "$target_file"
      else
        return 0
      fi
    else
      echo "WARNING: not replacing existing non-managed file $target_file" >&2
      return 0
    fi
  fi

  mkdir -p "$(dirname "$target_file")"
  if [ "$mode" = "link" ]; then
    ln -s "$source_file" "$target_file"
  else
    cp "$source_file" "$target_file"
  fi
}

install_codex_agents() {
  source_agents_dir="$framework_root/.codex/agents"
  target_agents_dir="$project_root/.codex/agents"
  [ -d "$source_agents_dir" ] || return 0
  mkdir -p "$target_agents_dir"

  mode="copy"
  if [ "$create_links" = true ]; then
    mode="link"
  fi

  for agent_file in mana-explorer.toml mana-full-specialist.toml mana-worker.toml; do
    [ -f "$source_agents_dir/$agent_file" ] || continue
    install_managed_file_or_link "$source_agents_dir/$agent_file" "$target_agents_dir/$agent_file" "$mode"
  done

  config_file="$project_root/.codex/config.toml"
  if [ ! -e "$config_file" ]; then
    cat > "$config_file" <<'CONFIG'
# Mana-managed minimal Codex project configuration.
# Existing user-owned .codex/config.toml files are never replaced by bootstrap.
[agents]
max_threads = 3
max_depth = 1
interrupt_message = false
CONFIG
  fi
}

install_claude_agents() {
  source_agents_dir="$framework_root/.claude/agents"
  target_agents_dir="$project_root/.claude/agents"
  [ -d "$source_agents_dir" ] || return 0
  mkdir -p "$target_agents_dir"

  mode="copy"
  if [ "$create_links" = true ]; then
    mode="link"
  fi

  for agent_file in mana-orchestrator.md mana-explorer.md mana-full-specialist.md mana-worker.md; do
    [ -f "$source_agents_dir/$agent_file" ] || continue
    install_managed_file_or_link "$source_agents_dir/$agent_file" "$target_agents_dir/$agent_file" "$mode"
  done
}

install_opencode_agents() {
  source_agents_dir="$framework_root/.opencode/agents"
  target_agents_dir="$project_root/.opencode/agents"
  [ -d "$source_agents_dir" ] || return 0
  mkdir -p "$target_agents_dir"

  mode="copy"
  if [ "$create_links" = true ]; then
    mode="link"
  fi

  for agent_file in mana_orchestrator.md mana_explorer.md mana_full_specialist.md mana_worker.md; do
    [ -f "$source_agents_dir/$agent_file" ] || continue
    install_managed_file_or_link "$source_agents_dir/$agent_file" "$target_agents_dir/$agent_file" "$mode"
  done
}

# The wrapper body is intentionally single-quoted so variables expand in the
# generated project wrapper, not while bootstrap-project.sh is running.
# shellcheck disable=SC2016
wrapper_content='#!/usr/bin/env bash
set -eu

project_root="$(cd "$(dirname "$0")" && pwd)"
env_file="$project_root/.mana/env"

if [ -f "$env_file" ]; then
  # shellcheck disable=SC1090
  . "$env_file"
fi

: "${MANA_HOME:?MANA_HOME is not set. Run scripts/bootstrap-project.sh again.}"

cmd="${1:-help}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$cmd" in
  help|--help|-h)
    cat <<USAGE
Usage:
  ./mana profile <name> [args...]       Print/run a Mana profile.
  ./mana divination "<intent>" [opts]    Recommend a profile without running it.
  ./mana cast <profile> [opts]           Validate and execute a Mana profile.
  ./mana explore "<question>" [opts]     Run bounded read-only explorer retrieval.
  ./mana context <cmd> [args...]         Inspect or refresh optional User Context.
  ./mana doctor [args...]                Diagnose Mana and this linked project.
  ./mana learning <cmd> [args...]        Inspect governed learning candidates.
  ./mana journey <cmd> [args...]         Create and inspect append-only Learning Journeys.
  ./mana concepts <cmd> [args...]        Query/validate the Learning Concept Registry.
  ./mana scout <cmd> [args...]           Scout or harden a bounded Learning Journey.
  ./mana expand <cmd> [args...]          Add a bounded explanation enrichment to a Journey node.
  ./mana user-learning <cmd> [args...]   Capture, aggregate, or synthesize external User Learning proposals.
  ./mana eval run [scenario] [opts]       Run deterministic behavioural evaluations.
  ./mana eval compare <base> <candidate>  Compare persisted evaluation results.
  ./mana verify [opts]                   Run deterministic Verification Skills.
  ./mana repair [opts]                   Run one bounded evidence-driven repair attempt.
  ./mana report governance [opts]         Generate a local governance summary.
  ./mana runtime <cmd> [args...]         Inspect repository-local runtime events.
  ./mana workspace <cmd> [args...]      Resolve/init/status Mana workspace.
  ./mana jira-mcp [args...]             Run Jira MCP Docker wrapper.
  ./mana sonar [args...]                Configure/check/run local sonar-scanner.
  ./mana dependency-evidence [args...]  Collect local dependency evidence inventory.
  ./mana evidence-index [args...]       Build active workspace evidence index.
  ./mana validate-mana                  Validate the linked Mana repository.
  ./mana path                           Print linked Mana path.

Examples:
  ./mana profile story-start
  ./mana profile jessica-fletcher --codex
  ./mana profile jessica-fletcher --claude
  ./mana profile jessica-fletcher --opencode
  ./mana profile jessica-fletcher --jira-key PROJ-1234 --codex
  ./mana divination "Add a Kafka contract field and Liquibase migration" --explain
  ./mana cast architecture-review --dry-run
  ./mana runtime sessions
  ./mana explore "Where is the Kafka contract?"
  ./mana context status
  ./mana context refresh
  ./mana learning candidates
  ./mana journey create --title "Trace request" --start-kind http_endpoint --start-value "POST /x" --termination-kind runtime_effect --termination-condition committed
  ./mana concepts candidates --language java --framework spring
  ./mana scout request --title "Trace payment" --path /payments
  ./mana scout harden jrn_0123456789abcdef01234567
  ./mana expand request --journey jrn_0123456789abcdef01234567 --node jn_0123456789abcdef01234567
  ./mana user-learning capture
  ./mana user-learning aggregate
  ./mana user-learning synthesize --dry-run
  ./mana user-learning candidates
  ./mana user-learning review <candidate-id> --accept
  ./mana user-learning promote <review-id>
  ./mana eval run conditional-contract-pr
  ./mana verify --dry-run --explain
  ./mana repair --from <result.json> --check <id> --allow-path <file> --runner codex --once --dry-run
  ./mana report governance
  ./mana workspace status
  ./mana workspace init --feature PROJ-1234
  ./mana jira-mcp --get-issue PROJ-1234
  ./mana jira-mcp --fetch-epic-story-pack PROJ-1234
  ./mana jira-mcp --env-file .mana/jira-mcp.env --check-access --issue PROJ-1234
  ./mana jira-mcp --env-file .mana/jira-mcp.env --dry-run
  ./mana sonar --init-config
  ./mana sonar --check
  ./mana dependency-evidence --collect
  ./mana evidence-index
USAGE
    ;;
  profile)
    exec "$MANA_HOME/scripts/run-profile.sh" "$@"
    ;;
  divination)
    exec "$MANA_HOME/scripts/divination.sh" --project-root "$project_root" "$@"
    ;;
  cast)
    exec "$MANA_HOME/scripts/cast.sh" --project-root "$project_root" "$@"
    ;;
  explore)
    exec "$MANA_HOME/scripts/mana-explore.sh" --project-root "$project_root" "$@"
    ;;
  context)
    exec "$MANA_HOME/scripts/mana-context.sh" "$@" --project-root "$project_root"
    ;;
  doctor)
    exec "$MANA_HOME/scripts/mana-doctor.sh" --project "$project_root" "$@"
    ;;
  learning)
    exec "$MANA_HOME/scripts/mana-learning.sh" --project-root "$project_root" "$@"
    ;;
  journey)
    exec "$MANA_HOME/scripts/mana-journey.sh" --project-root "$project_root" "$@"
    ;;
  concepts)
    exec "$MANA_HOME/scripts/mana-concepts.sh" --project-root "$project_root" "$@"
    ;;
  scout)
    exec "$MANA_HOME/scripts/mana-scout.sh" --project-root "$project_root" "$@"
    ;;
  expand)
    exec "$MANA_HOME/scripts/mana-expand.sh" --project-root "$project_root" "$@"
    ;;
  user-learning)
    exec "$MANA_HOME/scripts/mana-user-learning.sh" --project-root "$project_root" "$@"
    ;;
  eval)
    exec "$MANA_HOME/scripts/mana-eval.sh" --project-root "$project_root" "$@"
    ;;
  verify)
    exec "$MANA_HOME/scripts/mana-verify.sh" --project-root "$project_root" "$@"
    ;;
  repair)
    exec "$MANA_HOME/scripts/mana-repair.sh" --project-root "$project_root" "$@"
    ;;
  report)
    subcommand="${1:-}"
    [ "$subcommand" = governance ] || { echo "ERROR: report supports governance only" >&2; exit 2; }
    shift
    exec "$MANA_HOME/scripts/mana-governance-report.sh" --project-root "$project_root" "$@"
    ;;
  runtime)
    exec "$MANA_HOME/scripts/mana-runtime.sh" --project-root "$project_root" "$@"
    ;;
  workspace)
    exec "$MANA_HOME/scripts/mana-workspace.sh" "$@" --root "$project_root"
    ;;
  jira-mcp)
    exec "$MANA_HOME/scripts/run-jira-mcp-docker.sh" "$@"
    ;;
  sonar)
    exec "$MANA_HOME/scripts/run-sonar-scanner.sh" --project-root "$project_root" "$@"
    ;;
  dependency-evidence)
    exec "$MANA_HOME/scripts/run-dependency-evidence.sh" --project-root "$project_root" "$@"
    ;;
  evidence-index)
    exec "$MANA_HOME/scripts/run-evidence-index.sh" --project-root "$project_root" "$@"
    ;;
  validate-mana)
    exec "$MANA_HOME/scripts/validate-repo.sh"
    ;;
  path)
    printf "%s\n" "$MANA_HOME"
    ;;
  *)
    echo "ERROR: unknown mana command: $cmd" >&2
    echo "Run ./mana help" >&2
    exit 2
    ;;
esac'

write_file "$project_root/mana" "$wrapper_content"
chmod +x "$project_root/mana"

if [ "$create_links" = true ]; then
  for name in skills agents profiles docs templates mcp .codex .opencode .junie .claude; do
    source_path="$framework_root/$name"
    target_path="$project_root/.mana/links/$name"
    [ -e "$source_path" ] || continue
    if [ -L "$target_path" ]; then
      if [ "$force" = true ]; then
        rm "$target_path"
      else
        continue
      fi
    elif [ -e "$target_path" ]; then
      echo "WARNING: not replacing existing non-symlink $target_path" >&2
      continue
    fi
    ln -s "$source_path" "$target_path"
  done
fi

install_codex_agents
install_claude_agents
install_opencode_agents

if [ "$create_jira_env" = true ]; then
  jira_example="$framework_root/mcp/env/jira-mcp.env.example"
  jira_target="$project_root/.mana/jira-mcp.env"
  if [ -f "$jira_example" ] && { [ "$force" = true ] || [ ! -f "$jira_target" ]; }; then
    cp "$jira_example" "$jira_target"
    chmod 600 "$jira_target"
  fi
fi

readme_content="# Mana Link

This project is linked to:

\`\`\`text
$framework_root
\`\`\`

Use the local wrapper:

\`\`\`bash
./mana profile mana-help
./mana profile story-start
./mana profile jessica-fletcher
./mana profile jessica-fletcher --jira-key PROJ-1234 --codex
./mana workspace status
./mana context status
./mana context refresh
./mana workspace init --feature <FEATURE-ID>
./mana jira-mcp --get-issue PROJ-1234
./mana jira-mcp --fetch-epic-story-pack PROJ-1234
./mana jira-mcp --env-file .mana/jira-mcp.env --check-access --issue PROJ-1234
./mana jira-mcp --env-file .mana/jira-mcp.env --dry-run
./mana sonar --init-config
./mana sonar --check
./mana dependency-evidence --collect
./mana evidence-index
\`\`\`

Project artifacts stay local under \`.mana/\`.
\`.mana/user-context/\` is a generated, read-only working mirror of optional
user-owned reusable guidance. It is not Service Context and must not be edited
or committed.

Linked Mana folders are under \`.mana/links/\`.
Codex runtime agents are installed under \`.codex/agents/\` and OpenCode
runtime agents are installed under \`.opencode/agents/\` as Mana-managed files
or symlinks. Existing user-owned Codex/OpenCode agents and \`.codex/config.toml\`
are preserved. Mana still enforces Codex agent \`max_threads=3\`,
\`max_depth=1\`, and \`interrupt_message=false\` at runner startup with CLI
configuration. OpenCode receives equivalent bounded-delegation instructions
through the \`mana_orchestrator\` primary agent and the three Mana subagents.
Do not put real Jira credentials in Git. For Jira Server/Data Center, the
minimal shell setup is \`JIRA_URL\` plus \`JIRA_PERSONAL_TOKEN\`.
For Sonar scanner, keep only \`SONAR_HOST_URL\` and \`SONAR_TOKEN\` in the
environment. Project scanner properties live in
\`.mana/global/sonar-project.properties\`.
Use \`./mana evidence-index\` to refresh \`.mana/<workspace>/evidence/index.md\`
after collecting Jira, Sonar, dependency, test, validation, or PR evidence.
"

write_file "$project_root/.mana/README.md" "$readme_content"

claude_md_content="# Mana

This project uses Mana for structured AI-assisted delivery.
See \`.mana/links/.claude/instructions.md\` for full runner governance.

## Invoking Profiles

\`\`\`bash
./mana profile <name>                # render profile
./mana profile <name> --codex        # run via Codex
./mana profile <name> --claude       # run via Claude Code
./mana profile <name> --opencode     # run via OpenCode
\`\`\`

Key profiles:
- \`dev-assist\`           — Development support (preferred runner: Claude Code)
- \`jessica-fletcher\`     — Production pre-mortem before commit
- \`branch-ready\`         — Branch validation before PR
- \`pr-ready\`             — PR package generation
- \`requested-pr-review\`  — Requested-review PR inbox triage
- \`team-coaching-review\` — Per-contributor quality analysis (Team Leader)

## How Agents And Skills Work

When asked to run a profile, Claude Code:
1. Reads \`.mana/links/profiles/<name>.yaml\`
2. Reads \`.mana/links/agents/<agent>/AGENT.md\` and \`playbook.md\`
3. Loads only the primary or conditionally relevant skills via
   \`.mana/links/skills/<skill>/SKILL.md\`
4. Writes outputs to the active \`.mana/\` workspace

Run: \`./mana profile jessica-fletcher --claude\` — Claude Code follows the full chain.

## Workspace

Active workspace:  \`.mana/\`
Feature work:      \`.mana/features/<FEATURE-ID>/\`
Global context:    \`.mana/global/service-mission.md\`, \`architecture.md\`, \`engineering-guards.md\`
User Context:      \`.mana/user-context/\` when configured; generated, advisory, and read-only

## Jira Read-Only Context

Agents with \`jira_read\` may read Jira issues discovered from the branch name
or passed with \`--jira-key <KEY>\`. Issue keys use a generic configurable
pattern, not a fixed project prefix. Configure Jira with ignored
\`.mana/jira-mcp.env\` or shell variables:

\`\`\`bash
export JIRA_URL=https://jira.your-company.com
export JIRA_PERSONAL_TOKEN=...
\`\`\`

## Governance

- Load \`.mana/global/engineering-guards.md\` before any analysis.
- Treat healthy \`.mana/user-context/\` content as reusable personal guidance,
  not project truth. Start with \`index.md\` or \`preferences.md\` when present,
  inspect deeper files only when relevant, and prefer repository evidence and
  project/service constraints on conflict. Never edit the generated mirror.
- Write outputs to \`.mana/\` only — never to \`src/\` or project source.
- Do not commit automatically — every git commit requires explicit developer approval.
- \`jira_read\` is read-only. Do not expose tokens, transition issues, add Jira
  comments, or update tickets without explicit developer approval.
- Prefer \`./mana jira-mcp --get-issue <KEY>\` to read a Jira story. Use
  \`./mana jira-mcp --check-access --issue <KEY>\` only for credential or
  permission diagnostics.
- Treat Jira summary, description, status, standard attributes, visible custom
  fields, readable properties, linked context, and all readable comments as
  requirement evidence. Report inaccessible data as an evidence gap. For planning, check feasibility and
  testability. For review or validation, compare branch/PR changes against the
  story and report missing requested behavior, unrequested scope, contradicted
  acceptance criteria, and weak tests.
- \`github_read\` may use authenticated \`gh\` for read-only PR discovery,
  evidence, paginated comments, and review-thread resolution state. Validate
  unresolved or unknown threads against the current diff; do not infer that a
  general comment is resolved. Do not approve, comment, merge, edit, label, or assign through
  GitHub without explicit developer approval.
- \`github_pr_comment_write\` is allowed only for a selected PR when an explicit
  publish flag is provided, and only for blocker/high-criticality findings.
- \`sonar-scanner\` is optional evidence. Keep \`SONAR_HOST_URL\` and
  \`SONAR_TOKEN\` in the environment; keep project scanner properties in
  \`.mana/global/sonar-project.properties\`; write scanner outputs under
  \`.mana/<workspace>/evidence/sonar/\`.
- Follow \`docs/standards/agent-skill-output-standard.md\`. Instruction priority
  is current human instruction, profile YAML, agent \`AGENT.md\`, playbook,
  loaded skill \`SKILL.md\`, then global service context, with User Context as
  advisory guidance beneath project evidence and constraints. Never weaken safety,
  external-write, or human-approval rules.
- Use the Mana operating loop: identify the human decision, resolve inputs,
  workspace, requirement source, branch or PR target, and diff base; inventory
  evidence; classify risk domains; load only needed skills; then report status,
  findings, evidence, artifacts, and approvals.
- Use progressive load-light reading for candidate skills: front matter, title,
  \`Purpose\`, \`When To Use It\`, \`When Not To Use It\`, \`Inputs\`,
  \`Outputs\`, \`Execution Logic\`, and \`Decision Rules\` before deciding
  whether a deep read is needed. Do not read every skill, every example, or
  unrelated agent folders up front.
- Use compact caveman working notes while analyzing: terse fragments,
  evidence-first notes, no long narrative, and no private chain-of-thought in
  final artifacts. Maintain a context budget: keep a short working summary with
  objective, base branch or PR, issue keys, workspace path, checked evidence,
  open hypotheses, discarded hypotheses, and next checks instead of accumulating
  raw transcripts, full diffs, repeated file dumps, complete Jira payloads, full
  PR threads, full skill files, or copied tool output.
  Convert working notes into the structured sections required by
  \`docs/standards/agent-skill-output-standard.md\`.

## Claude Runtime Delegation

Claude Code uses project-scoped Mana agents in \`.claude/agents/\`:
- \`mana-orchestrator\` is the economy root for routing, evidence inventory,
  low-risk checks, delegation, aggregation, and synthesis.
- \`mana-explorer\` is a read-only evidence subagent.
- \`mana-full-specialist\` is a read-only high-risk/full-tier subagent.
- \`mana-worker\` is a serialized writer only when the selected profile
  explicitly permits source modification.

These are runtime capability classes, not Mana semantic agents. Batch related
skills by risk domain; do not create one Claude Code subagent per Mana skill.
The root may request at most three direct subagents, one per capability class;
child agents cannot delegate. Parallelism is only for independent read-heavy
work. If delegation is unavailable or insufficient for high-risk work, preserve
a concise handoff artifact and return \`needs_model_escalation\`.
"

write_file "$project_root/CLAUDE.md" "$claude_md_content"

agents_md_content="# Mana

This project uses Mana for structured AI-assisted delivery.
See \`.mana/links/.codex/instructions.md\` for full runner governance.

## Invoking Profiles

\`\`\`bash
./mana profile <name>                # render profile
./mana profile <name> --codex        # run via Codex
./mana profile <name> --claude       # run via Claude Code
./mana profile <name> --opencode     # run via OpenCode
\`\`\`

Key profiles:
- \`story-start\`          — Requirement intake and planning artifacts
- \`jessica-fletcher\`     — Production pre-mortem before commit
- \`branch-ready\`         — Branch validation before PR
- \`pr-ready\`             — PR package generation
- \`requested-pr-review\`  — Requested-review PR inbox triage
- \`team-coaching-review\` — Per-contributor quality analysis (Team Leader)

## How Agents And Skills Work

When asked to run a profile, Codex:
1. Reads \`.mana/links/profiles/<name>.yaml\`
2. Reads \`.mana/links/agents/<agent>/AGENT.md\` and \`playbook.md\`
3. Loads only the primary or conditionally relevant skills via
   \`.mana/links/skills/<skill>/SKILL.md\`
4. Uses the small root model for routing, evidence inventory, low-risk checks,
   delegation, aggregation, and final synthesis
5. Delegates bounded read-heavy evidence work to \`mana_explorer\` and bounded
   high-risk judgment to \`mana_full_specialist\` when those custom agents are
   available
6. Writes outputs to the active \`.mana/\` workspace

Run: \`./mana profile jessica-fletcher --codex\` — Codex follows the full chain.

Claude Code follows the same bounded delegation chain through
\`.claude/agents/mana-orchestrator.md\` and the Mana-managed
\`mana-explorer\`, \`mana-full-specialist\`, and \`mana-worker\` subagents.
Run: \`./mana profile jessica-fletcher --claude\`.

OpenCode follows the same Mana chain through \`.opencode/agents/mana_orchestrator.md\`
and the Mana-managed \`mana_explorer\`, \`mana_full_specialist\`, and
\`mana_worker\` subagents. Run: \`./mana profile jessica-fletcher --opencode\`.

## Workspace

Active workspace:  \`.mana/\`
Feature work:      \`.mana/features/<FEATURE-ID>/\`
Global context:    \`.mana/global/service-mission.md\`, \`architecture.md\`, \`engineering-guards.md\`
User Context:      \`.mana/user-context/\` when configured; generated, advisory, and read-only

## Jira Read-Only Context

Agents with \`jira_read\` may read Jira issues discovered from the branch name
or passed with \`--jira-key <KEY>\`. Issue keys use a generic configurable
pattern, not a fixed project prefix. Configure Jira with ignored
\`.mana/jira-mcp.env\` or shell variables:

\`\`\`bash
export JIRA_URL=https://jira.your-company.com
export JIRA_PERSONAL_TOKEN=...
\`\`\`

## Governance

- Load \`.mana/global/engineering-guards.md\` before any analysis.
- Treat healthy \`.mana/user-context/\` content as reusable personal guidance,
  not project truth. Start with \`index.md\` or \`preferences.md\` when present,
  inspect deeper files only when relevant, and prefer repository evidence and
  project/service constraints on conflict. Never edit the generated mirror.
- Write outputs to \`.mana/\` only — never to \`src/\` or project source.
- Do not modify the same branch while Junie is actively editing it.
- Do not commit automatically — every git commit requires explicit developer approval.
- \`jira_read\` is read-only. Do not expose tokens, transition issues, add Jira
  comments, or update tickets without explicit developer approval.
- Prefer \`./mana jira-mcp --get-issue <KEY>\` to read a Jira story. Use
  \`./mana jira-mcp --check-access --issue <KEY>\` only for credential or
  permission diagnostics.
- Treat Jira summary, description, status, standard attributes, visible custom
  fields, readable properties, linked context, and all readable comments as
  requirement evidence. Report inaccessible data as an evidence gap. For planning, check feasibility and
  testability. For review or validation, compare branch/PR changes against the
  story and report missing requested behavior, unrequested scope, contradicted
  acceptance criteria, and weak tests.
- \`github_read\` may use authenticated \`gh\` for read-only PR discovery,
  evidence, paginated comments, and review-thread resolution state. Validate
  unresolved or unknown threads against the current diff; do not infer that a
  general comment is resolved. Do not approve, comment, merge, edit, label, or assign through
  GitHub without explicit developer approval.
- \`github_pr_comment_write\` is allowed only for a selected PR when an explicit
  publish flag is provided, and only for blocker/high-criticality findings.
- \`sonar-scanner\` is optional evidence. Keep \`SONAR_HOST_URL\` and
  \`SONAR_TOKEN\` in the environment; keep project scanner properties in
  \`.mana/global/sonar-project.properties\`; write scanner outputs under
  \`.mana/<workspace>/evidence/sonar/\`.
- Follow \`docs/standards/agent-skill-output-standard.md\`. Instruction priority
  is current human instruction, profile YAML, agent \`AGENT.md\`, playbook,
  loaded skill \`SKILL.md\`, then global service context, with User Context as
  advisory guidance beneath project evidence and constraints. Never weaken safety,
  external-write, or human-approval rules.
- Use the Mana operating loop: identify the human decision, resolve inputs,
  workspace, requirement source, branch or PR target, and diff base; inventory
  evidence; classify risk domains; load only needed skills; then report status,
  findings, evidence, artifacts, and approvals.
- Codex subagents are runtime capability classes only. Mana semantic agents
  stay under \`.mana/links/agents/\`, and Mana skills stay under
  \`.mana/links/skills/\`. Do not create one Codex subagent per Mana skill.
- Codex may spawn at most three direct subagents and child agents must not
  spawn further agents. Parallel delegation is for independent read-heavy work.
  Write-heavy work is serialized and requires a profile that explicitly permits
  source modification.
- If Codex custom agents are unavailable, disabled, fail, or return
  insufficient evidence for a high-risk judgment, preserve a concise handoff
  artifact and return \`needs_model_escalation\` instead of performing that
  judgment on the small root model.
- Claude Code uses the same bounded delegation model: \`mana-orchestrator\` is
  the primary agent, and \`mana-explorer\`, \`mana-full-specialist\`, and
  \`mana-worker\` are runtime subagents. Do not create one Claude Code
  subagent per Mana skill; use at most three direct subagents and no recursive
  delegation. If they are unavailable or insufficient for high-risk work,
  return \`needs_model_escalation\` rather than letting the economy root make
  the judgment.
- OpenCode uses the same bounded delegation model: \`mana_orchestrator\` is the
  primary agent, and \`mana_explorer\`, \`mana_full_specialist\`, and
  \`mana_worker\` are runtime subagents. Do not create one OpenCode subagent per
  Mana skill; use at most three direct subagents and no recursive delegation.
- Use progressive load-light reading for candidate skills: front matter, title,
  \`Purpose\`, \`When To Use It\`, \`When Not To Use It\`, \`Inputs\`,
  \`Outputs\`, \`Execution Logic\`, and \`Decision Rules\` before deciding
  whether a deep read is needed. Do not read every skill, every example, or
  unrelated agent folders up front.
- Use compact caveman working notes while analyzing: terse fragments,
  evidence-first notes, no long narrative, and no private chain-of-thought in
  final artifacts. Maintain a context budget: keep a short working summary with
  objective, base branch or PR, issue keys, workspace path, checked evidence,
  open hypotheses, discarded hypotheses, and next checks instead of accumulating
  raw transcripts, full diffs, repeated file dumps, complete Jira payloads, full
  PR threads, full skill files, or copied tool output.
  Convert working notes into the structured sections required by
  \`docs/standards/agent-skill-output-standard.md\`.
"

write_file "$project_root/AGENTS.md" "$agents_md_content"

if [ "$update_gitignore" = true ]; then
  gitignore="$project_root/.gitignore"
  touch "$gitignore"
  add_ignore_line() {
    line="$1"
    if ! grep -qxF "$line" "$gitignore"; then
      printf '%s\n' "$line" >> "$gitignore"
    fi
  }
  add_ignore_line ".mana/jira-mcp.env"
  add_ignore_line ".mana/user-context/"
  add_ignore_line ".mana/"
fi

workspace_args=(init --root "$project_root" --purpose "$purpose")
if [ -n "$feature" ]; then
  workspace_args+=(--feature "$feature")
fi
"$framework_root/scripts/mana-workspace.sh" "${workspace_args[@]}"

if ! "$framework_root/scripts/mana-context.sh" refresh --project-root "$project_root" >/dev/null; then
  echo "WARNING: User Context is configured but could not be materialized; run ./mana context status" >&2
fi

cat <<SUMMARY
Mana linked successfully.

Project root:   $project_root
Mana root: $framework_root

Created:
  $project_root/mana
  $project_root/AGENTS.md
  $project_root/CLAUDE.md
  $project_root/.mana/env
  $project_root/.mana/README.md
  $project_root/.mana/links/
  $project_root/.codex/agents/
  $project_root/.claude/agents/
  $project_root/.opencode/agents/
  $project_root/.mana/

Try:
  ./mana profile mana-help
  ./mana workspace status
  ./mana context status
  ./mana profile jessica-fletcher
SUMMARY
