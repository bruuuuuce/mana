# Codex Instructions

- Read planning artifacts before analysis.
- Resolve the active `.mana` workspace before running planning, validation, PR readiness, or learning workflows.
- Load `.mana/global/service-mission.md`, `.mana/global/architecture.md`, and `.mana/global/engineering-guards.md` when present before producing recommendations.
- Treat violations of `.mana/global/engineering-guards.md` as blockers unless an accountable owner explicitly approves an exception.
- Write planning artifacts, validation reports, PR packages, developer handoff, and learning outputs into the active `.mana` workspace.
- Do not modify the same branch while Junie is actively editing it.
- Prefer reports, risk registers, and proposed patches over direct destructive edits.
- Respect MCP least privilege, redaction, approval, and audit policies.
- Stop on high-risk database, architecture, security, or cross-service blockers.
- `jira_read` is optional read-only Jira MCP access. If Jira issue keys are
  provided by the profile or discovered from the branch, read those issues as
  requirement context when the configured MCP server is available. Never expose
  Jira tokens, transition issues, add comments, or update tickets without
  explicit human approval.
- In a Mana-linked project, prefer `./mana jira-mcp --get-issue <KEY>` to read
  a Jira story quickly. Use `./mana jira-mcp --check-access --issue <KEY>` only
  to diagnose credentials or permissions.
- Treat Jira story text, acceptance criteria, linked context, and relevant
  comments as requirement evidence. For feasibility or planning work, check
  whether the story is coherent, implementable, testable, and has required
  owners or approvals. For review, validation, pre-mortem, and PR work, compare
  the branch or PR changes against the story and report missing requested
  behavior, unrequested scope, contradicted acceptance criteria, and weak tests.
  Code that works technically can still be a finding if it diverges from the
  story.
- Jira issue key discovery is generic and project-configurable; do not assume a
  fixed project prefix. If no key is found, continue with local Mana artifacts
  unless the profile requires story context.
- `github_read` is optional read-only GitHub CLI access. If `gh` exists and is
  authenticated, use it to read PR metadata, diffs, files, checks, and reviewer
  requests. Do not approve, comment, merge, edit, label, assign, or otherwise
  write through `gh` without explicit human approval.
- `github_pr_comment_write` is allowed only when a profile explicitly receives
  `publish_high_risk_comments=true` and a single PR number or URL. In that case,
  publish at most one `gh pr comment` containing blocker or high-criticality
  findings from the current run.
- Exclude Mana framework/bootstrap noise from production findings and evidence:
  `.mana/**`, `AGENTS.md`, `CLAUDE.md`, `mana`, and Mana-only `.gitignore` or
  env ignore changes. Mention them only as operational setup notes when relevant.
- For any profile using branch or code diff evidence, resolve and report the
  comparison base. Prefer explicit input, then `origin/HEAD`, then a single
  credible primary branch. If ambiguous, ask the user; do not default to `main`.
- For any profile using branch or code diff evidence, start with a filtered diff
  inventory, exclude Mana/bootstrap noise, classify changed files by risk domain,
  and read only files needed to validate plausible blocker or warning
  hypotheses. If the filtered diff is larger than roughly 80 files or 2,000
  changed lines, ask the user to choose a review scope instead of scanning the
  whole repository.
- Do not read every skill listed in a profile up front. Read the agent and
  playbook first, load the primary skill needed to start, then load specialist
  skills only when the filtered inputs show their risk domain is relevant.
- Use compact caveman working notes while analyzing: terse fragments,
  evidence-first notes, no long narrative, and no private chain-of-thought in
  final artifacts. Maintain a context budget: keep a short working summary with
  objective, base branch or PR, issue keys, workspace path, checked evidence,
  open hypotheses, discarded hypotheses, and next checks instead of accumulating
  raw transcripts, full diffs, repeated file dumps, or copied tool output.
  Convert working notes into the structured sections required by
  `docs/standards/agent-skill-output-standard.md`.
