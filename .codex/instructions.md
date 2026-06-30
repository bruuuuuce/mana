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
