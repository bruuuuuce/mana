# M05 bounded bug-hunter gap analysis

## Decision

Mana has a distinct, testable job for a read-only `bug-hunt` profile. It searches
for latent defects in an explicit, user-bounded existing-code target; it does
not assess a branch or PR, issue stop/go guidance, or make approval decisions.

| Workflow | Trigger | Scope | Primary question | Evidence and output | Approval semantics | Boundary / overlap |
|---|---|---|---|---|---|---|
| Jessica Fletcher | Before commit, push, or pre-review | Current branch plus working tree against a resolved base | Why would this branch fail in production? | Diff, story and production context; ranked failure hypotheses and stop/go | Explicit human approval gates; may recommend stop | Branch-scoped pre-mortem; routes here only when the request is independent of a diff. |
| Branch validation | Before PR | Branch evidence versus plan, story, tests and risks | Is this branch ready for review? | Diff and delivery evidence; validation report | Readiness gate | Not a general existing-code search. |
| PR readiness / requested PR review | PR preparation or requested review | One branch/PR | What must a reviewer inspect or resolve? | PR metadata, diff and review evidence; PR package/findings | Review and narrowly controlled PR-comment semantics | Not a general existing-code search. |
| Existing defect skills | Invoked where their input is relevant | The caller's supplied code/diff/context | What risk pattern applies? | Narrow risk report and recommendations | Human review | Reused as analysis lenses; they do not define a bounded discovery workflow. |
| Bug hunter | User asks to inspect named components, packages or files | Explicit regular, repository-relative targets only; at most 25 files or 1,500 non-blank lines | What reproducible latent defect already exists here, regardless of the current branch? | Source and test evidence; confirmed/probable/hypothesis findings or `no_material_findings` | No merge, release or stop/go decision; owners decide any follow-up | Distinct existing-code discovery. Branch/PR causation questions route to Jessica or PR review. |

## Guardrails

- A target above either scope limit returns `needs_scope_narrowing`; it is never
  silently split or expanded into a repository scan.
- `.mana/**`, `AGENTS.md`, `CLAUDE.md`, `mana`, generated/vendor paths, and
  Mana-only ignore changes are out of scope. Paths are treated as untrusted;
  do not follow a target outside the repository root.
- A finding needs concrete source evidence, preconditions, an observable
  symptom, affected path, and a suggested reproducer or test. Classify it as
  `confirmed`, `probable`, or `hypothesis`; unsupported smells are discarded.
- `no_material_findings` means no finding met this evidence bar. It is not a
  claim that the target is correct or safe.
- The workflow is read-only. It can propose a patch or test, but never applies
  either without a separate explicit implementation request.
