# SS07 human acceptance checklist

Use this checklist with the sanitized SS00 Story Start topology and the
generated `planning/story-start-scope-v2.md` report. Reviewers approve scope;
the report does not approve it for them.

- [ ] **Chief/PO:** Does the base plan contain only the change requested by the
  approved acceptance criteria?
- [ ] **Architect:** Is every required enabler genuinely unavoidable, with a
  named failing criterion or mandatory constraint and causal evidence?
- [ ] **Architect/PO:** Do conditional branches correspond to real unresolved
  decisions, with mutually exclusive options kept separate?
- [ ] **Chief/PO:** Are independent pre-existing defects, risks, and optional
  improvements correctly excluded from original story scope?
- [ ] **Chief/PO:** Are base effort, mandatory deltas, conditional deltas,
  approved-expansion deltas, and readiness calendar effects understandable and
  sensitive to unresolved decisions?
- [ ] **All reviewers:** Was any discovered issue silently promoted into base or
  mandatory scope without the required evidence and approval?
- [ ] **Architect:** Did Mana surface relevant repository, branch, constraint,
  configuration, or causality evidence that a simpler plan missed?
- [ ] **All reviewers:** Does the report support an explicit human scope
  decision without selecting architecture, approval, or scope implicitly?

Record the reviewer, disposition, unresolved questions, and any approved scope
expansion in the project-owned decision evidence. An expansion must leave the
original classification intact and appear as a separate
`approved_scope_delta`.
