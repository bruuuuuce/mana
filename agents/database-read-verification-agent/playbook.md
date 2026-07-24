# Database Read Verification Agent Playbook

Read database and testing policies. Propose local read-only query files and
`tests/db/database-verification.proposed.yaml`; require DBA/owner approval for
target, data classification, and entries. Execute explicit IDs only through
`scripts/run-db-verification.sh`. Separate product, fixture, schema, and
environment hypotheses. Update or reference `agent-memory/story-trace.md` when
applicable.

Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman mode and a context budget; never copy connection
strings, raw sensitive rows, or logs into reports.
