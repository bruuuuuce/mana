# MANA-EXACT-001 — Exact application and verification without providers

2026-10-26. **A: COMPLETE for the bounded public-fixture test contract. B: qualified
on the exact local candidate identified below. C: MOM integration NOT QUALIFIED.**
No human approval, autonomous mission, production target execution, release or
MOM pin update is qualified by this work.

| Delivery field | Observed result |
|---|---|
| Concrete native entry | `scripts/mana-repair.sh --exact-request <absolute.json> --host-grant <private.json> --provider none --json` |
| Exact verifier entry | `scripts/mana-verify.sh` with the same options and an operation-specific `verify` request/grant |
| MANA real execution | **YES**, one positive historical-candidate invocation through public repair admission |
| Patch applied to dedicated copy | **YES**, precisely the historical `edit.replacement` |
| Baseline compile / test | **0 / 1**, threshold case fails, three others pass |
| After compile / test | **0 / 0**, all four frozen cases pass |
| Original fixture and MOM artifacts | **PRESERVED**, 1,974 preexisting enumerated MOM files unchanged |
| Providers called / initialized | **NO**, explicit none branch before provider-library sourcing |
| Human approval qualified | **NO**, explicit private host-issued public-fixture **test** authority |
| MOM integration | **NOT QUALIFIED**, old producer revision and architecture-review grant remain incompatible |
| Commits / pushes / branch changes | **NONE** |

## Work base and exact candidate

MANA `/Users/zel/projects/mana`, branch `develop`, HEAD/base
`aaed1122a22a9c1dc3f88771b2527180d967fb4f`. No checkout was substituted for the
old MOM pin. [initial.json](evidence/MANA-EXACT-001/initial.json) records full
initial status and fingerprints. Preexisting tracked modifications were the two
TRANSACTION T01 CSV reports and `docs/roadmap/TRANSACTION-01.md`; the full list of
preexisting untracked TRANSACTION/architecture reports is retained there. Their
bytes remain unchanged. The report and evidence directory did not exist; delivery
creation refuses existing names.

Read applicable ancestor instructions (none found), `CONTRIBUTING.md`,
`.codex/instructions.md`, the relevant verification/repair contracts, and the
complete MOM-E2E-003 report. Consulted MOM-E2E-002 report, package, exact review
view, package validator and fixture/baseline E2E-001. No general audit or GGUF work.
All MOM inputs remained read-only; hashes/schema were read from the actual files.

The tested candidate is **the current base plus local changes**, not the old pin
`378243883adb101a7a41feef71e2a66b76e7f508`, and not an immutable released revision.
Its runtime content identity is
`abb7b77bf58b87fe6b49a262a8893e6a1b7403f96461549a297fe9094a471d5a`.
This hashes the canonical dictionary of pertinent complete implementation file
hashes, including the unchanged reused supervisor; it is not a signature or Git
revision. [candidate.json](evidence/MANA-EXACT-001/candidate.json) also records
base, exact tracked delta, new module/test hashes, tools/JDK identity and the
SHA-256 of [candidate.patch](evidence/MANA-EXACT-001/candidate.patch).
The relevant implementation bytes were checked again after the single real run.
[final-manifest.json](evidence/MANA-EXACT-001/final-manifest.json) fingerprints the
complete delivered evidence set, report and contract.

| Runtime file | SHA-256 at the positive invocation |
|---|---|
| `scripts/mana-repair.sh` | `47c2c9e2618b3332050d2f19b9a2555bd03dedf2f1d9498f4b2f0a58bf76c968` |
| `scripts/mana-verify.sh` | `babc8c34f9a4813ab4ae433fd463a5c90bf7eb9e51799c2e975ac3188b8d9d2d` |
| `scripts/lib/exact_repair.py` | `82d51900c7fade715f8a71acacd398aaa4793bedc40c9e781a44c9f4cdc25f7e` |
| `scripts/lib/verification-exec.pl` (reused unchanged) | `9cb5bd9642d269adf857ba10ab3ad9c91e44307dc0a8d820fbfaa62557989f1a` |

## Minimal implementation and authority

Changes: early exact dispatch/help in the two public shell entries; one stdlib
module `scripts/lib/exact_repair.py`; `tests/exact-repair.py`; the
[exact contract](../standards/exact-repair.md), this report and its evidence.
No profile, generative workflow control, provider dispatcher, fixture, dependency,
MOM file, pin or historical evidence was changed.

The original E2E-002 JSON is embedded as a complete value in a strict
`mana.exact-request/v1` envelope. No second replacement/diff is authored.
Canonical fingerprint, snapshot text/hash records, actual destination base,
source scope and expected replacement hash are checked. The exact review view
was parsed and compared to the complete package, its derived diff and result hash:
[proposal-equivalence.json](evidence/MANA-EXACT-001/proposal-equivalence.json).
Historical `HUMAN_REQUIRED` / `executable:false` remains unchanged. The executor
knows no shipping threshold rule and opens no MOM database.

Admission binds full proposal/request, origin mission/request, content base,
destination device/inode, output directory, catalog/test/main class, runtime and
executable hashes, baseline output/exit, budgets and host grant ID. Destinations
are private disposable directories under `/private/tmp`, containing exactly the
snapshot files. Paths, symlink ancestors, hard links, test/configuration mutation,
unknown verifier fields and output overlap are rejected. Only an existing Java
production source is replaceable, with no target creation/deletion/rename.

Reused public repair/verify routing, fixed-argv verification convention and
`verification-exec.pl` supervision apply. The old repair provider invocation and
internal candidate import are not used. The old repair containment was not an OS
boundary and the existing authority vocabulary did not cover this operation; the
new code adds only a **specific** Seatbelt policy and private host-file admission,
not a general sandbox/authority framework. No MOM authority implementation is
imported or exposed as a bypass.

The explicitly issued `mana.exact-host-grant/v1` test grant is owned/private,
expires, hashes the whole request and allows one use. Before probes, an exclusive,
fsynced `<grant-file>.used` reservation is retained even on failure. No CLI/env
flag enables a synthetic executor or bypasses admission; injected doubles exist
only as Python component-test calls. The live entry accepts only
`authority=explicit-public-fixture-test`, never a fabricated human identity or
sharing consent. The private host store/issuer is trusted. Single use is per
canonical grant file; the issuer must retain its reservation and must not copy or
reissue it at a different filename. No distributed issuer registry or protection
against a malicious same-uid host authority is claimed.

## Native isolation and resource evidence

The per-operation deny-default Seatbelt policy permits source data writes only
to the exact allowed source and general build writes only under `outputs/classes`.
The host supervisor collects private logs/status/receipts outside the child write
boundary. Tests/configuration, original fixture, MOM/MANA checkouts and host
authority are unwritable. Network, Mach service lookup, fork and posix_spawn are
denied; known Python/JDK executables and required runtime reads are allowed.
System runtime and metadata reads are broader than the source projection; no VM
or complete host-confidentiality claim is made. The new verification-only exact
contract also declares source write authorization, although its application
function is never called and final hashes must remain unchanged; it does not
change any existing no-write profile.

The **actual positive invocation** ran probes inside that same policy before
compilation/application: write-open denial on frozen test/README, originals,
configuration, MOM/MANA implementation and receipt control; symlink aliases from
the writable build directory to protected files; network connection denial;
fork/spawn denial; permitted source write-open and build writes. Every boolean
was true. Its one-second timeout sentinel exited **143 / SIGTERM**, timed out
true. These are native results in
[result.json](evidence/MANA-EXACT-001/run/result.json), not mocked hash comparisons.
An additional native component test forks a sentinel descendant, times out the
leader and checks that the child is gone/non-running. The existing supervisor
alone cannot control deliberately detached sessions; native fork/spawn denial
closes that route in this specific execution policy.

Before the candidate was attempted, generic disposable native qualification
exposed outer-sandbox `sandbox_apply` denial, missing JDK discovery within the
initial read policy and a missing Python.app executable permission. Development
qualification corrected the specific runtime bindings; no historical candidate
was applied in those probes. The final generic native probe/JDK receipt is
[native-qualification.json](evidence/MANA-EXACT-001/native-qualification.json).
Native invocations required execution outside the tool's outer sandbox so that
MANA could establish its own Seatbelt boundary; no unsandboxed target command was
used as a fallback. The positive CLI itself independently repeated qualification.

Positive limits: 20 s per command, 180 s cumulative allowance checked before
phases, 16 KiB per stdout/stderr stream, 1 MiB per created file, inherited CPU
limits; one application and four verifier commands maximum. Probe/apply commands
are fixed native implementation steps. There is no total disk quota or JVM memory
limit. The host is trusted and must preserve its authority store. This capability
requires the observed macOS Seatbelt/Python framework/JDK arrangement; unsupported
hosts block. There is no rollback or crash-atomic transaction claim. A failure
after application starts is PARTIAL and retains the copy; no automatic correction.

## Tests and regressions

[checks](evidence/MANA-EXACT-001/checks) retains commands, exits and output.

| Check | Result and scope |
|---|---|
| `python3 -I -B tests/exact-repair.py` | **35 passed**; admission/application/failure tests use explicit doubles; one supervisor timeout/descendant test is native |
| Public CLI negative acceptance | **13/13 rejected**, no reservation/output/executor/probe/apply launched; destination content/shape unchanged |
| `tests/verification-skills.sh`, before / after | **PASS / PASS** |
| `tests/bounded-repair.sh`, before / after | **FAIL exit 2 / PASS**; before implementation hit preexisting timestamp/PID verification identity collision, no expectation changed |
| `tests/repair-containment.sh` | **PASS** |
| `tests/bounded-repair-loop.sh` | **PASS** |
| `scripts/validate-repo.sh` | **PASS** with external `PYTHONPYCACHEPREFIX`; initial restricted invocation failed only trying to write test py_compile cache into MANA, retained separately |
| `scripts/mana-doctor.sh` | **PASS**, 0 errors, 3 warnings (optional environment capabilities) |
| `bash -n scripts/*.sh hooks/pre-commit hooks/pre-push` | **PASS** |
| Ruff lint / format on the two new Python files | **PASS / PASS** |
| Pertinent/final diff whitespace | **PASS** (pertinent tracked delta) |

The 35 tests cover exact transformation, stale source/protected base, package and
result mismatch, missing/denied/other-effect/expired authority, no human
impersonation, invalid revision/budgets, destination identity, traversal,
file/ancestor symlinks, hard links, extra files, test/config edits, unknown command
text, single-file grant replay, unavailable native boundary, failed compilation,
failed tests, baseline mismatch, timeout, partial/mismatched application,
verification-only behavior and absent provider imports. Rejected validation does
not call injected executors. Public negatives additionally exercise missing,
denied and wrong-effect grants, package/base/result mismatch, unapproved
location/revision, exhausted budget, symlink escape, test edits and arbitrary argv:
[native-negatives.json](evidence/MANA-EXACT-001/native-negatives.json). An additional
public CLI check of a pre-reserved canonical grant rejects with
`AUTHORIZATION_CONSUMED`, with unchanged target and empty outputs:
[reserved-grant.json](evidence/MANA-EXACT-001/checks/reserved-grant.json). Only
read-only Git/JDK identity discovery precedes these rejections, never fixture
execution. Synthetic authorities do not qualify human approval.

Initial native supervisor testing under the outer tool sandbox could not inspect
`ps`; the same test passed with that tool restriction removed, without weakening
MANA's policy. This is distinct from a component regression. MANA's repository
checks were followed; MOM suites/foundation drivers were not run or changed.
No global regression-green claim is inferred beyond the checks listed here.

## Single real historical-candidate execution

Run/request ID `MANA-EXACT-001-positive`. The dedicated copy was
`/private/tmp/mana-exact-MANA-EXACT-001-positive-tkg6f6g7/fixture`;
private build/receipt output was its sibling `outputs`.
[launch.json](evidence/MANA-EXACT-001/launch.json) records the public invocation;
[request.json](evidence/MANA-EXACT-001/request.json) records its complete binding.
Archived grant/reservation are explicit test evidence, not a human approval.

One public invocation only, with no hidden candidate adjustment or retry:

1. Revalidated all three copied files against the actual historical base.
2. Qualified the concrete native policy and timeout, through MANA.
3. Ran baseline compilation exit **0**, test exit **1**; exact stdout hash matched
   the original `baseline-r2.json` before the application phase could proceed.
4. Applied `edit.replacement` exactly once in the sandbox, with a fresh source
   base check. Application exit **0**.
5. Recompiled and reran the same frozen test: exit **0 / 0**.
6. Compared full final file inventory and hashes; only the allowed source changed.
   External comparison also checked byte-identical replacement and proposal diff.

| Frozen case | Before | After |
|---|---|---|
| 4999 → 500 | PASS | PASS |
| 5000 → 0 | FAIL, observed 500 | PASS |
| 5001 → 0 | PASS | PASS |
| -1 → IllegalArgumentException | PASS | PASS |

Result source hash
`acdfdd17d5d53bad3e7abdfc59a43ff07da4158060899a19f28e2859e1ce1cc2`,
matching historical replacement and review. Test hash remains
`ae4668670b8814c7525bf66693ca3707938e3ddf18ec95cdf8c69a49195a883e`;
README remains unchanged. Exact final diff and external assertions are in
[positive-comparison.json](evidence/MANA-EXACT-001/positive-comparison.json).
The native result and SHA-256 sidecar, per-step output/status and reservation are
retained. The source transformation is not promoted to semantic proof beyond
these four frozen cases.

## Preservation and version dependency

[preservation.json](evidence/MANA-EXACT-001/preservation.json) compares all 1,974
preexisting enumerated nonignored MOM files and 1,613 MANA files: no missing files;
only the two intended MANA entry scripts changed among the preexisting MANA set.
The module/test/documentation/evidence are additions. Unrelated preexisting MANA
content is byte-identical. Git HEAD/branch remain unchanged; MOM source/pin and
all historical artifacts are untouched. Ignored environments/caches and Git
internal object storage are outside this file-manifest comparison.

A. **Contract implemented and tested** within the narrow private-host public-fixture
test authority and documented limits above.
B. **Real execution qualified** on this exact local candidate and fixture: native
isolation/authority gates, one exact source replacement, unchanged tests, 0/0 and
four passing cases. Human approval and general target execution remain unqualified.
C. **MOM integration NOT QUALIFIED.** MOM will need a separately reviewed new MANA
revision containing these exact-mode changes, executable closure/boundary review,
and an operation-specific request/grant adapter. The architecture-review provider
grant cannot be reused. No pin/version adoption, MOM change, release/governance
restart or additional execution was performed here. No commit or push.
