# End-To-End Claude Code Flow

This example shows how to use Mana from installation through PR readiness
using Claude Code as the primary runner. Claude Code resolves `read_files`,
`code_search`, and `git_read` natively; Jira and Confluence access require
the MCP server configured in step 2b.

## 1. Validate Mana

From the Mana repository:

```bash
scripts/validate-repo.sh
scripts/mana-doctor.sh
```

`mana-doctor.sh` checks for the Claude CLI and warns if it is not installed.
Install Claude Code from `https://claude.ai/code` if needed.

## 2. Link Mana Into A Project

From the target application repository:

```bash
/path/to/mana/scripts/bootstrap-project.sh --feature EPIC-123
```

This creates:

- `./mana`, a local command wrapper.
- `.mana/env`, with the linked Mana path.
- `.mana/links/`, with symlinks to Mana skills, agents, profiles, docs, templates, and MCP definitions.
- `.mana/features/EPIC-123/`, the active evidence workspace.

## 2b. Configure Jira MCP (Optional)

To enable `jira_read` and `confluence_read` tools, configure the MCP server:

```bash
cp /path/to/mana/mcp/config/claude-jira-mcp.json ~/.claude/mcp.json
```

Edit `~/.claude/mcp.json` to point to the correct paths for
`run-jira-mcp-docker.sh` and `jira-mcp.env`. See
`mcp/env/jira-mcp.env.example` for required variables.

When Jira MCP is unavailable, populate requirements manually (see step 4).

## 3. Confirm The Link

```bash
./mana path
./mana workspace status
./mana profile mana-help
```

`profile` renders the selected profile and runs the Mana freshness check. It
does not autonomously execute every listed agent or skill.

## 4. Add Requirements Without Jira MCP

Copy `templates/epic-story-pack.template.md` into the active workspace:

```text
.mana/features/EPIC-123/context/epic-story-pack.md
```

Fill it with the epic goal, story list, acceptance criteria, constraints, open
questions, dependencies, and known risks.

## 5. Plan The Work With Claude Code

Ask Claude Code to use:

- `agents/story-implementation-planner/AGENT.md`
- `agents/story-implementation-planner/playbook.md`
- `.mana/features/EPIC-123/context/epic-story-pack.md`

Expected outputs include story context, source impact map, technical breakdown,
risk register, green-border plan, and open questions.

## 6. Get Development Support Before Writing Code

Before starting implementation of a task, run:

```bash
./mana profile dev-assist
```

Claude Code is the preferred runner for `dev-assist`. Ask it to invoke
`change-impact-preview` with a description of the planned change. The skill
identifies callers impacted, contract risks, concurrency flags, and tests to
update — before any code is written.

Also invoke `concurrency-risk` for concurrent or shared-state changes, and
`legacy-characterization` before touching legacy paths.

## 7. Implement One Technical Task

Use the approved plan to implement one bounded task at a time. Keep changes
inside the approved source impact map unless Claude Code records plan drift
and asks for approval.

Claude Code does not commit automatically. Every `git commit` requires
explicit developer approval.

## 8. Run Pre-Commit Pre-Mortem

Before commit:

```bash
./mana profile jessica-fletcher
```

Ask Claude Code to answer:

```text
The code introduced in this branch is causing production issues. Find the most
likely reasons.
```

Use `agents/jessica-fletcher-agent/AGENT.md` and route findings into the active
`.mana/` workspace.

## 9. Validate The Branch And PR Package

```bash
./mana profile branch-ready
./mana profile pr-ready
```

Use the corresponding agents to check drift, missing tests, unresolved risks,
database safety, reviewer focus, and PR evidence.
