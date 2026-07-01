# Junie Guidelines

- Implement one technical subtask at a time.
- Read generated planning files from the active `.mana` workspace before coding.
- Read `.mana/global/engineering-guards.md` before changing code and stop if the requested edit violates a guard.
- Use `.mana/global/service-mission.md` and `.mana/global/architecture.md` to understand service intent and boundaries.
- Write local test evidence and fix-loop notes into the active `.mana` workspace.
- Run local tests after each change.
- Never modify files outside the approved source-impact map without asking.
- Do not perform broad autonomous refactoring.
- Do not edit the same branch concurrently with Codex-generated changes.
- Follow `docs/standards/agent-skill-output-standard.md`. Instruction priority
  is current human instruction, profile YAML, agent `AGENT.md`, playbook,
  loaded skill `SKILL.md`, then global service context. Never weaken safety,
  external-write, or human-approval rules.
- Use the Mana operating loop: identify the human decision, resolve inputs,
  workspace, requirement source, branch or PR target, and diff base; inventory
  evidence; classify risk domains; load only needed skills; then report status,
  findings, evidence, artifacts, and approvals.
- Exclude Mana framework/bootstrap noise from production findings and evidence:
  `.mana/**`, `AGENTS.md`, `CLAUDE.md`, `mana`, and Mana-only `.gitignore` or
  env ignore changes. Mention them only as operational setup notes when relevant.
- Use compact caveman working notes while analyzing: terse fragments,
  evidence-first notes, no long narrative, and no private chain-of-thought in
  final artifacts. Maintain a context budget: keep a short working summary with
  objective, base branch or PR, issue keys, workspace path, checked evidence,
  open hypotheses, discarded hypotheses, and next checks instead of accumulating
  raw transcripts, full diffs, repeated file dumps, complete Jira payloads, full
  PR threads, full skill files, or copied tool output.
  Convert working notes into the structured sections required by
  `docs/standards/agent-skill-output-standard.md`.
