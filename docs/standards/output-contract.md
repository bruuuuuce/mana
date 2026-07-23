# Output Contract

Every Mana artifact must contain:

- `status`: `complete`, `blocked`, `ambiguous`, `needs_human_decision`, or
  `needs_model_escalation`.
- findings separated into blocker, warning, and info when applicable.
- evidence references with file paths, issue/PR identifiers, commands, or
  artifact paths; distinguish facts from inference and missing evidence.
- required human approvals, owner, and next action when a gate is reached.
- concise artifacts and summaries only. Do not include private reasoning, raw
  logs, full diffs, complete Jira payloads, or copied PR threads.

Use the detailed [Agent And Skill Output Standard](agent-skill-output-standard.md)
only when designing templates, changing policy, or resolving an output-format
ambiguity.
