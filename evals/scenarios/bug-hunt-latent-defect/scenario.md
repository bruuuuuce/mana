# Scenario: Existing-code latent defect

**Profile:** `bug-hunt`
**Exercises:** explicit existing-code scope, evidence-backed defect discovery.

## Intent

The target is an existing idempotency handler not changed on the current
branch. Fixture evidence describes a duplicate-delivery path and a proposed
reproducer. The run must select concurrency analysis and declare the structured
finding artifacts; it must not require branch or PR evidence.
