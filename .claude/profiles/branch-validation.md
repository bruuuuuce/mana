# Branch Validation

Use Claude Code to run `jessica-fletcher`, `branch-ready`, and `pr-ready` profiles. Load the relevant profile, run the matching agent, produce Markdown artifacts in the active `.mana` workspace, and request human approval for blockers.

For pre-mortem analysis, ask Claude Code:

> The code introduced in this branch is causing production issues. Find the most likely reasons.

Use `agents/jessica-fletcher-agent/AGENT.md` and route findings into the active `.mana/` workspace.
