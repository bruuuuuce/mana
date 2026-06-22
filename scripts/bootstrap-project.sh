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
  ./mana workspace <cmd> [args...]      Resolve/init/status Mana workspace.
  ./mana jira-mcp [args...]             Run Jira MCP Docker wrapper.
  ./mana validate-mana                  Validate the linked Mana repository.
  ./mana path                           Print linked Mana path.

Examples:
  ./mana profile story-start
  ./mana profile jessica-fletcher
  ./mana workspace status
  ./mana workspace init --feature PROJ-1234
  ./mana jira-mcp --env-file .mana/jira-mcp.env --dry-run
USAGE
    ;;
  profile)
    exec "$MANA_HOME/scripts/run-profile.sh" "$@"
    ;;
  workspace)
    exec "$MANA_HOME/scripts/mana-workspace.sh" "$@" --root "$project_root"
    ;;
  jira-mcp)
    exec "$MANA_HOME/scripts/run-jira-mcp-docker.sh" "$@"
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
  for name in skills agents profiles docs templates mcp .codex .junie .claude; do
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
./mana workspace status
./mana workspace init --feature <FEATURE-ID>
./mana jira-mcp --env-file .mana/jira-mcp.env --dry-run
\`\`\`

Project artifacts stay local under \`.mana/\`.

Linked Mana folders are under \`.mana/links/\`.
Do not put real Jira credentials in Git.
"

write_file "$project_root/.mana/README.md" "$readme_content"

claude_md_content="# Mana

This project uses Mana for structured AI-assisted delivery.
See \`.mana/links/.claude/instructions.md\` for full runner governance.

## Invoking Profiles

\`\`\`bash
./mana profile <name>
\`\`\`

Key profiles:
- \`dev-assist\`           — Development support (preferred runner: Claude Code)
- \`jessica-fletcher\`     — Production pre-mortem before commit
- \`branch-ready\`         — Branch validation before PR
- \`pr-ready\`             — PR package generation
- \`team-coaching-review\` — Per-contributor quality analysis (Team Leader)

## How Agents And Skills Work

When asked to run a profile, Claude Code:
1. Reads \`.mana/links/profiles/<name>.yaml\`
2. Reads \`.mana/links/agents/<agent>/AGENT.md\` and \`playbook.md\`
3. Invokes each skill via \`.mana/links/skills/<skill>/SKILL.md\`
4. Writes outputs to the active \`.mana/\` workspace

Say: \"Run the jessica-fletcher profile\" — Claude Code follows the full chain.

## Workspace

Active workspace:  \`.mana/\`
Feature work:      \`.mana/features/<JIRA-KEY>/\`
Global context:    \`.mana/global/service-mission.md\`, \`architecture.md\`, \`engineering-guards.md\`

## Governance

- Load \`.mana/global/engineering-guards.md\` before any analysis.
- Write outputs to \`.mana/\` only — never to \`src/\` or project source.
- Do not commit automatically — every git commit requires explicit developer approval.
"

write_file "$project_root/CLAUDE.md" "$claude_md_content"

agents_md_content="# Mana

This project uses Mana for structured AI-assisted delivery.
See \`.mana/links/.codex/instructions.md\` for full runner governance.

## Invoking Profiles

\`\`\`bash
./mana profile <name>
\`\`\`

Key profiles:
- \`story-start\`          — Requirement intake and planning artifacts
- \`jessica-fletcher\`     — Production pre-mortem before commit
- \`branch-ready\`         — Branch validation before PR
- \`pr-ready\`             — PR package generation
- \`team-coaching-review\` — Per-contributor quality analysis (Team Leader)

## How Agents And Skills Work

When asked to run a profile, Codex:
1. Reads \`.mana/links/profiles/<name>.yaml\`
2. Reads \`.mana/links/agents/<agent>/AGENT.md\` and \`playbook.md\`
3. Invokes each skill via \`.mana/links/skills/<skill>/SKILL.md\`
4. Writes outputs to the active \`.mana/\` workspace

Say: \"Run the jessica-fletcher profile\" — Codex follows the full chain.

## Workspace

Active workspace:  \`.mana/\`
Feature work:      \`.mana/features/<JIRA-KEY>/\`
Global context:    \`.mana/global/service-mission.md\`, \`architecture.md\`, \`engineering-guards.md\`

## Governance

- Load \`.mana/global/engineering-guards.md\` before any analysis.
- Write outputs to \`.mana/\` only — never to \`src/\` or project source.
- Do not modify the same branch while Junie is actively editing it.
- Do not commit automatically — every git commit requires explicit developer approval.
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
  add_ignore_line ".mana/"
fi

workspace_args=(init --root "$project_root" --purpose "$purpose")
if [ -n "$feature" ]; then
  workspace_args+=(--feature "$feature")
fi
"$framework_root/scripts/mana-workspace.sh" "${workspace_args[@]}"

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
  $project_root/.mana/

Try:
  ./mana profile mana-help
  ./mana workspace status
  ./mana profile jessica-fletcher
SUMMARY
