# Expected Findings: Ambiguous Story

## must_flag

| # | Finding | Minimum Severity | Owning Skill |
|---|---|---|---|
| 1 | PROJ-102 (15% cap) and PROJ-103 (flat 20% off) contradict each other | blocker | story-quality |
| 2 | AC 2 "fast and smooth" is not observable/testable | warning | acceptance-criteria-testability |
| 3 | Error behavior for invalid, expired, or already-used codes is unspecified | warning | story-quality |
| 4 | Discount service failure behavior (timeout, retry, unavailable) is unspecified | warning | story-quality |
| 5 | Analysis depth asymmetry: UI layout is detailed while validation/error domains are missing | info | story-quality |

## must_not

- Must not invent error handling, timeout, or retry requirements and plan
  against them as if specified.
- Must not mark the story ready for implementation while finding 1 is
  unresolved.
- Must not silently skip the consistency check: sibling stories are present in
  the pack.

## required_gates

- Clarification questions routed to BA/PO for findings 2–4.
- Blocker escalation for finding 1 before planning continues.
