# Public artifact privacy remediation — HEYBRUC-228

**Status: BLOCKED — specialized secret scanning is unavailable; independent review of this clean reconstruction is pending.**

## Baseline and method

Pinned baseline and direct parent of the clean candidate branch: `c61d21f7f83192aa659957d3615af4b015f44e84`. A separate local branch, `fix/heybruc-228-clean-candidate`, was created from that commit after confirming the source checkout was clean. The existing remediation branch was preserved and not modified. The reconstruction uses the 48 changed sanitized artifact contents and two audit documents from the reviewed local candidate; one of the 49 inventoried artifacts already matched the baseline byte-for-byte. The two intermediate remediation commits are not ancestors of this candidate. No remote fetch was performed.

The prior targeted scanner enumerated tracked files and reachable blobs at the pinned baseline and checked home/cache/temp absolute paths, private-key headers, common GitHub/AWS token forms, credential assignments, email-shaped values, private IPv4 ranges, and private host suffixes. No specialist secret-scanning tool was installed (`gitleaks`, `trufflehog`, `detect-secrets`, `git-secrets`, `secretlint`, `ggshield`, `noseyparker`, `ripsecrets`, `semgrep`, and `trivy` were unavailable); none was installed or configured. A specialist scan of this candidate tree and reachable history is therefore **BLOCKED / NOT RUN**. The prior targeted scan is not a complete assurance. No matching path contents or email values are reproduced here.

## Sanitized inventory and remediation

| Classification | Baseline findings | Local disposition |
|---|---:|---|
| Potentially identifying home-directory paths | 305 occurrences in 47 report/evidence files | Reissued with a stable redaction marker |
| macOS user-cache paths | 17 occurrences in those report/evidence files | Reissued with a stable redaction marker |
| Intentional test home-path fixtures | 6 occurrences across 2 test files | One fixture account-like component normalized to a stable synthetic home placeholder; remaining values are explicit synthetic placeholders retained for test meaning |
| Standard macOS system path in `scripts/lib/context-shadow-backend.py` | 1 occurrence | Classified as an OS allowlist path; unchanged |
| Temporary absolute paths under the OS temp root | 1,448 occurrences across 89 files | Classified as technical temporary-path evidence; unchanged; no user-home component was implicated by this signature |
| PEM/GitHub/AWS/credential-assignment/private IPv4 signatures | 0 | No credential confirmed by these targeted checks |
| Email-shaped values | 25 | Located in examples, test fixtures, sample configuration, and a recorded patch; no personal address or credential was confirmed. Values omitted. |
| Private-suffix candidates | 71, all `.local` | Classified as local development/schema/test host examples; no `.corp`, `.internal`, or `.lan` match |

The earlier “48 files / about 305 occurrences” is reconciled as 47 report/evidence files plus one standard OS-path source reference; 305 counts `/Users` paths in the report/evidence set. The two test files account for six additional home-path fixture matches: three user-home-root and three Unix-home-root matches.

The public machine-readable manifest contains sanitized artifact digests for 48 changed artifacts only. The private inventory verifies 49 artifacts; one unchanged test artifact is omitted from the public manifest because its sanitized digest would equal its original digest. All 49 original SHA-256 values and Git blob IDs remain in a private local evidence file, not in this report or public manifest. Original path-bearing blobs remain reachable in baseline history; the remediation does not erase those historical objects. The previous remediation branch also retains two intermediate commits whose manifests exposed original blob-reference metadata; neither commit is an ancestor of this clean candidate. The 48 sanitized artifact contents are byte-identical to the reviewed candidate contents. The two audit documents intentionally differ to record the clean ancestry, omit the unchanged artifact digest, and mark specialist clearance BLOCKED. No history rewrite was performed.

## Git object accounting and historical exposure

At the pinned commit, `git rev-list --objects` yields 5,054 reachable objects: 203 commits, 1,887 trees, and 2,964 blobs. Across all locally available refs, the object database contains 5,066 objects: 212 commits, 1,887 trees, 2,964 blobs, and 3 tags. The previously reported 4,854 equals the non-commit subtotal (2,964 blobs + 1,887 trees + 3 tags), so it is not a complete total-object count. No remote fetch was made; these are local object-database counts.

The reachable history contains 167 unique blob contents with scanned path signatures (317 home-directory matches, 20 macOS cache-path matches, and 1,596 OS-temp-root matches across unique blobs). These are blob-content counts, not occurrence counts per commit. The first affected report commit was identified as 2026-10-19; four report files in that commit contained eight home-root and 16 cache-root matches. Its exact commit reference and per-file evidence are kept privately to avoid pointing this report at unredacted history. Reissuing the current files does not remove original blobs from public history. No history rewrite or deletion was performed.

### History decision recommendation

Recommendation: **do not rewrite public history in this remediation.** The confirmed finding is local path information; the targeted scan did not confirm a credential. A rewrite would still be substantial and cannot recall old objects from existing forks and clones. It would change descendant commit IDs, break external commit references, invalidate affected commit signatures, and require retargeting or re-signing affected annotated tags. Four local release tags were observed (one lightweight and three annotated). On the pinned history, Git reported signature status `E` for 172 commits (signature verification could not be completed locally) and `N` for 31 commits (no signature); this is not a cryptographic validity result.

This recommendation leaves a documented public-history privacy residual. The owner has directed that history not be rewritten. Any acceptance of the historical path exposure for a future release remains a separate decision. A coordinated history procedure would be necessary only if that direction changes; it would need to account for signed commits/tags and external refs and inform clone/fork owners. No such operation was performed. The local candidate and current-tree remediation do not constitute historical cleanup or release clearance.

## Public PR description

Public PR #24 was closed and merged. On 2026-11-06 its description was corrected: the absolute Familiar-root argument is now `<FAMILIAR_ROOT>`, while the command and recorded PASS for 11 Familiar tests were preserved. A fresh read of the PR body found zero home/cache/temp absolute-path signatures.

## Verification and limits

Verification on this reconstruction: `env PYTHONDONTWRITEBYTECODE=1 python3 tests/mana-catalog.py` PASS; `env PYTHONDONTWRITEBYTECODE=1 python3 tests/context-runtime-delegation.py` PASS (91 cases); all 40 JSON files in the candidate diff and manifest parse; all 48 changed artifact files match the reviewed sanitized candidate byte-for-byte. A separate local check verified all 49 private original/sanitized hash pairs; Sol did not inspect the private inventory, so that pair verification is not independently reviewed. The original-identifier scan found no new original blob or SHA-256 references relative to the baseline; an unchanged artifact's original digest was removed from the public manifest. `git diff --check` PASS. In the changed files, the path signature scan found one home-root match in an existing synthetic test fixture and zero macOS cache-root matches; the two audit documents have no home/cache path signatures. The whole tree has six synthetic home-root fixture matches, as classified in the inventory. Specialist secret scanning remains BLOCKED / NOT RUN because no scanner is available. Sol independently confirmed the changed artifact comparison, public manifest, clean ancestry boundary and scanner limitation; the reviewer did not inspect the private inventory. No runtime behavior changed; one test fixture component was normalized to a stable synthetic value.

## Owner decisions and residual risks

- PR #24 description correction is complete and verified.
- History rewrite remains out of scope by owner direction; decide separately whether the documented path-only historical exposure is acceptable for any future release. Current remediation does not erase reachable Git objects.
- The owner must decide whether the documented path-only historical exposure is acceptable; the unavailable specialist scan leaves credential clearance unproven.
- HEYBRUC-228 remains open; HEYBRUC-233 remains blocked. No push, merge, release, tag change or issue transition is authorized or performed.
