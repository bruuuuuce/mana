# MANA-META-SKILL-00-R1 — Independent Review

## Verdict

**NEEDS_FIX. No commit created.** Review date: 2026-10-19.
The existing implementation and historical delivery report are preserved.
The no-target-writes requirement fails for temporary validation staging even
though all 12 existing regressions pass. No TRANSACTION-01 implementation,
candidate approval/activation, Familiar or REL-01/A changes were performed.

## Scope And Preservation

Verified branch `feature/mana-meta-skill-00`, HEAD
`ad8730ebe70f494ac24a80fbf32fcf2b30cdef35`, and an initially empty index.
Reviewed all 15 original changed/untracked files, including the generated index,
CI/suite wiring, source, tests, contracts, example and documentation. No unrelated
change was identified. Initial file hashes and modes are retained in the
[review evidence](MANA-META-SKILL-00-R1-results.json); all 15 remain identical.
Only this report and its evidence receipt are added by R1.

## Findings

1. **P1 / blocking — temporary writes inside the analyzed project.**
   `scripts/mana-skill-factory.py:207` calls `TemporaryDirectory` without choosing
   or checking its parent. Python honors `TMPDIR`/`TEMP`/`TMP`; these paths never
   pass through `candidate_location`. Using the existing disposable Spring fixture
   and a fresh interpreter with those variables pointing at the target, observed
   two staging directories containing `skills/java-spring-transaction-analysis/SKILL.md`
   inside that target. Generation exits 0. Cleanup restores the original content
   snapshot, hiding the writes from existing before/after assertions. This is a
   deterministic environment case, not a concurrent-filesystem attack.
   Required correction: validate a staging parent outside the target and discovery
   roots before creating anything, or block before writing. Apply this to both
   generation and validation. Add an observation-based regression to the existing
   suite; final snapshot equality alone is insufficient.

2. **P2 / architectural gap — specialization remains coupled to the factory.**
   The implementation is a fixed Java/Spring template generator with evidence,
   not a general specialist generator. Generic helpers exist, but there is no
   explicit adapter/recipe boundary. Identity/template constants at lines 17–18,
   Java/Maven detection at line 62, specialist manifest fields at line 146,
   staging identity at line 211, exact-template validation at line 264 and CLI
   request choices at line 315 all encode the same specialization. A new domain
   requires editing these core paths. Extending it is feasible; extension without
   changing the factory is not demonstrated. A small trusted adapter/recipe
   interface could separate detector, request matching, template, tools and domain
   declarations from packaging/governance validation. No universal plugin system
   or second production domain is requested here.

3. **P2 / robustness — small nested JSON escapes structured rejection.**
   `scripts/mana-skill-factory.py:264` parses untrusted JSON without a depth guard;
   the exception boundary at line 327 does not catch `RecursionError`. A 4,011-byte
   candidate JSON with 2,000 nested arrays produces a traceback and exit 1 instead
   of the documented blocked JSON/exit 2. This does not grant trust or execute a
   candidate. Bound nesting or handle parser recursion as blocked input within
   existing validation; no new security infrastructure is needed.

## Architectural Assessment

| Layer | Actual behavior |
|---|---|
| Generic mechanism | File hashes/limits, output path checks, bundle writes, fixed pending/untrusted state and native validator invocation are reusable helpers |
| Technology adapter | Maven direct-dependency and conventional Java source detection is a dedicated function, but has no selectable adapter contract |
| Specialist template | Candidate Markdown is copied byte-for-byte from one curated Java/Spring template |
| Project-derived knowledge | Observed dependency coordinates, representative Java path and hashes; no inferred transactional semantics, project-specific tool selection or generated specialist knowledge |
| Future extension | Needs separation of specialization data/detection from core manifest, validation and CLI paths before the R1 extensibility criterion is demonstrated |

Native skill metadata, `validate-skills.sh`, output conventions, index generation,
profile allowlists and existing generated-trust policy are reused. No duplicate
registry, provider runner, verification executor or approval service was found.
The factory-specific closed-manifest check is a candidate integrity contract,
not a replacement native registry. Approval/promotion is deliberately absent.

## Candidate And Verification Results

PetClinic remains at `500158f732419217507c7656904b8e6aa1bcc0d6`, with clean Git
status before/after. Fresh generation and validation of the delivered candidate
both exit 0. Both generated files match the delivered files byte-for-byte.
The 132-file content digest remains
`7cd602986575faa0589f0b9e2177c45ecd682ceae6fd97d04666c0da36b91851`.

Direct Spring Boot coordinates and same-module Java source hashes substantiate
the candidate's narrow declaration/source-presence claim. They do not establish
resolved versions, actual transactional methods, manager/proxy behavior, nesting
support or runtime execution. All six requested analysis capabilities are
explicitly future/`not_implemented`; limits and prerequisites are declared.
`trusted`, `registered` and `executable` stay false; approval stays pending.

| Check | Result / scope |
|---|---|
| Existing 12 factory regressions, rerun verbosely | PASS, exit 0 |
| `scripts/validate-repo.sh` | PASS, exit 0; includes native skill, verification-contract, output and index checks |
| `tests/profile-skill-activation.sh` | PASS, exit 0 |
| Ruff check / format check | PASS, exit 0 each |
| Generated index comparison / `git diff --check` | PASS |
| Alternate Java/Spring case | PASS using existing `FactoryTests.setUp` / direct `spring-context`; target unchanged and Markdown identical to PetClinic |
| Unsupported coordinates | PASS: existing fixture changed to `com.example`, exit 2, no output or target changes |
| Target wrapper/instruction execution | No execution path found; existing executable wrapper sentinel remains unexecuted; project data only enters evidence, not instructions |
| Output containment | Existing canonical-path, target-subtree, discovery-path, overwrite and symlink cases PASS; temporary staging FAIL as above |
| Approval bypass through supported factory operations | No bypass found: tampered approval/trust/tools rejected, no approval/register/activate operation, native compiler rejects undeclared candidate |
| Global impossibility of manual installation | NOT CLAIMED; factory does not mediate unrelated manual filesystem/registry edits |
| Deep untrusted JSON | FAIL: uncaught recursion, exit 1 |
| Full zero-token suite / remote CI | NOT RUN; no new QA campaign |

Raw logs, return codes, probe observations and preservation hashes are retained in
[the evidence receipt](MANA-META-SKILL-00-R1-results.json). The receipt includes
the bounded reproduction source; it is evidence, not an installed test service.

## Consolidation And Recommendation

The commit condition is unmet. Nothing was staged or committed; HEAD and index
remain unchanged. Commit SHA, signature, parent and committed-tree verification
are **NOT APPLICABLE — no commit**. No new worktree, merge or push was performed.

Correct the staging isolation defect and malformed-input handling, and establish
the small adapter boundary, in an explicitly scoped follow-up. Reuse the existing
tests and validators, then repeat R1 before signed consolidation. Keep
TRANSACTION-01 at proposal status until this foundation is accepted. Its parser,
propagation and diagram analyzers remain entirely unimplemented; this review
does not approve the PetClinic candidate or authorize its activation.
