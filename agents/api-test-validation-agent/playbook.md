# API Test Validation Agent Playbook

Read the API policy and testing policy. Propose `tests/api/api-testbook.proposed.yaml`.
Require approval for target, data references, and each entry. Run only explicit
IDs via `scripts/run-api-testbook.sh`; retain JSON, JUnit, and logs in
`tests/api/runs/`. Report product, contract, data, dependency, and environment
hypotheses separately. Update or reference `agent-memory/story-trace.md` when
applicable.

Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman mode and a context budget; never copy raw
payloads, credentials, or logs into reports.
