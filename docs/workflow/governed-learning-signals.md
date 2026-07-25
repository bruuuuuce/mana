# Governed Learning Signals

Mana collects small, auditable runtime observations into project-local
candidate records under `.mana/learning/candidates/`. A candidate is an
observation, not learned truth and never executable content. The pipeline is:

`runtime observation → candidate → reviewed → rejected|archived`.

There is no automatic promotion in this lifecycle. Any future governed
knowledge change is a separate, human-authorized process outside this command.

Supported sources are repeated `evidence.missing`, `guard.triggered`,
`model.escalated`, `tool.blocked`, and `profile.failed` events. Candidate fields
include an ID, profile/service scope, observation and category, sorted and
deduplicated `evidenceReferences` and `executions` JSON arrays, event
references, recurrence, deterministic confidence (`low`, `medium`,
or `high`), counter-evidence, proposed destination, status, and staleness.
Secrets or personal/credential-bearing strings are rejected before a candidate
is written.

Use `mana learning candidates`, `show <id>`, `review <id>`, `reject <id>`, or
`archive <id>`. `review` writes a learning-agent review artifact only. There is
deliberately no promotion command: no confidence value can change a skill,
guard, rule, profile, Service Context, or knowledge card. Candidates are local
to one repository; cross-project promotion is intentionally out of scope.

Conflicting observations are retained as counter-evidence rather than
collapsed. Old observations are marked stale after 90 days. Runtime evidence
answers what occurred during an execution; delivery evidence still establishes
whether a proposed lesson is correct.

`candidate → reviewed`, `candidate → rejected`, `candidate → archived`,
`reviewed → rejected`, and `reviewed → archived` are the only allowed
transitions. Rejected and archived records are terminal for collection.
