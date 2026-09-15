# Context Runtime v2 architecture decision

Status: accepted for staged implementation through CTX-07C.

## Decisions

Mana will use host-owned, finite orchestration: declared phases, bounded retrieval/retry limits, and host-enforced permissions. It will not create an autonomous planning loop.

Fresh provider invocations at phase and worker boundaries are the reliable isolation boundary. Provider-managed subagents are optional optimizations and cannot be required for correctness.

Every phase will receive an immutable, host-generated governance envelope. Models may report gates and permissions but cannot amend, grant, or weaken them.

Raw evidence will be stored once by the host and exposed through stable bounded references. Handoffs carry references and validated facts, not transcripts.

Phase handoffs will be structured checkpoints, schema-validated and evidence-backed. They retain uncertainty and cannot increase permissions.

Usage accounting will be a separate, privacy-preserving metric surface: no prompt, response, tool payload, source content, credentials, or private reasoning is persisted.

The legacy runtime remains available through rollout. Context Runtime v2 is additive until profile-specific equivalence and human release gates pass.

## CTX-00 baseline contract

`scripts/mana-context-baseline.sh` is local-only and deterministic for unchanged inputs. By default it emits JSON to stdout and creates no project or `.mana` state. `--output` is explicit opt-in for a file artifact; `--project-root` optionally supplies a project whose existing Service Context can be measured read-only. Sizes are bytes plus a clearly labelled `bytes_divided_by_4_estimate`; they are not measured provider tokens. Provider capabilities remain `unknown` until CTX-02 establishes their contract.

## CTX-02 provider capability contract

`contracts/context-runtime/provider-capabilities-v1.schema.json` is the
provider-neutral capability contract. Every named capability is explicitly
`supported`, `unsupported`, or `unknown`; `unknown` is an evidence gap and is
never promoted to support. Reports are derived from the installed provider's
version/help/config probe, or from equivalent deterministic fixtures. They do
not use version-range guesses and are not cached. Each adapter recognizes its
own authoritative help grammar. A token mentioned in prose is not evidence of
support, missing declarations in a partial or unexpected help surface remain
`unknown`, and `unsupported` requires an explicit negative declaration on a
recognized surface (or an equivalent structured negative probe result).

Provider-managed children remain optional. A report of support for child agent
definitions does not prove fresh child context, effective child model routing,
or recursive-delegation prevention. Those properties remain `unknown` unless a
local provider surface proves them. Host-launched fresh invocations remain the
reliable future isolation and model-routing boundary.

Adapters collect positive and authoritative negative evidence independently
for every capability, retaining safe probe provenance until one provider-neutral
resolver applies `0/0 -> unknown`, `1/0 -> supported`, `0/1 -> unsupported`, and
`1/1 -> unknown`. Provider help declarations are evaluated as complete semantic
blocks, so a positive prefix followed by a same-line or continuation-line
refutation cannot produce support.

Composite capabilities are resolved in a second, mechanically separate step.
Their required prerequisites are first resolved atomically to `supported`,
`unsupported`, or `unknown`; the composite consumes only those states and
cannot reopen raw evidence. All required states supported produces support, an
authoritatively unsupported required state produces unsupported, and otherwise
uncertainty propagates as unknown. Direct evidence about the composite itself
is resolved separately, and a contradiction with the derived state becomes
unknown.

The legacy `--no-codex-subagents` and `--no-claude-subagents` flags select
provider-specific mechanical denies in addition to the matching prompt policy
and an effective maximum child count of zero. OpenCode selects a unique inline
primary with `permission.task: deny`; that configures the built-in Task entry
point, but does not prove runtime recursive-delegation prevention. Merged
user/project configuration also means complete hard disable and user-config
isolation remain `unknown`. Claude safe mode proves only its declared custom
command/agent scope, so complete user-config isolation remains `unknown` there
as well. Disabled Claude and OpenCode paths do not create or rewrite persistent
managed orchestrator files.
This is an isolation correction only; CTX-02 does not introduce fresh phase
execution, delegation packets, context manifests, evidence stores, or
compaction budgets.

## CTX-03 authority and checkpoint boundary

Model checkpoints are untrusted data, while permissions, immutable execution
identity, human gates, and completed approval records remain host-owned control
plane inputs. The host validator represents these as separate types: validating
a checkpoint cannot construct host authority, and effective permission or
approval state is derived exclusively from a separately supplied host authority
context. Model prose is never interpreted as a permission or approval decision.

Every model-owned fact surface uses the shared typed subject contract;
governance, permissions, approval, control, and unrecognized domains are not
representable. Application facts may discuss approval-shaped text, but claim
prose is inert. Evidence IDs are bounded references, not proof that evidence
exists and never authority. Checkpoints are bounded reference-and-claim
documents, not carriers for raw logs, full diffs, complete API payloads, or
copied conversations. Authority evaluation binds checkpoint, host execution,
and approval record to the same execution ID and execution version. Host
issuance/completion timestamps are timezone-aware RFC3339 values, and an
approval completed before issuance is invalid.

Contained JSON reads and artifact writes use no-follow, directory-FD-relative,
component-by-component traversal. Publication of an absent destination uses a
kernel no-replace rename. Replacement of an observed regular file uses atomic
exchange, verifies the displaced inode/device/type, and rolls back an identity
mismatch. After publication the writer re-attests the parent from the trusted
root and rolls back if that namespace binding changed. Linux uses `renameat2`
with `RENAME_NOREPLACE`/`RENAME_EXCHANGE`; macOS uses `renameatx_np` with
`RENAME_EXCL`/`RENAME_SWAP`. Other platforms, missing libc entry points, and
filesystems that reject the required operation fail closed; plain rename is
never a CAS fallback.

Containment and success validity are separate guarantees. Anchored FDs prevent
an attacker symlink from redirecting the write outside the authorized root.
Post-publication attestation additionally prevents success from being returned
when the write landed in a parent directory that was renamed out of its
authorized path during the operation. This boundary covers hostile namespace
mutation within the authorized root; it does not claim protection against
kernel or mount-level compromise.

Failure atomicity is conditional on the kernel rollback primitive succeeding.
A pre-publication failure leaves the destination unchanged and removes staging;
a post-publication validation failure with successful rollback restores the
absent/original state and removes staging. If rollback itself fails, the writer
returns a typed, non-success `RollbackFailure` with safe project-relative
recovery metadata and `manualRecoveryRequired`. It does not claim transactional
cleanup: new content may remain published, and an exchanged original is retained
as a mode-`0600` recovery artifact rather than deleted as a temporary leak.
Containment outside the anchored target remains intact, while destination
reconciliation becomes an explicit host responsibility. This exceptional
contract does not weaken the normal no-replace/exchange publication protocol.

## CTX-04 profile compilation and activation authority

The host compiles the profile document graph before model invocation. The
top-level `skills:` list remains the complete candidate catalog, while
`skill_activation.baseline` and `skill_activation.conditional` define the
authoritative activation graph. Initial model-tier escalation is calculated
from baseline work only. A conditional skill becomes active only through a
declared host signal or a classifier request that the compiler validates back
to a declared conditional mapping.

The compiled manifest separates candidates, baseline skills, host-signal
activations, semantic requests, active skills, inactive skills, remaining
conditional signals, and explicitly deep-loaded instruction paths. Routing
metadata is copied only for active work. Full skill bodies and the complete
skill index are not part of the manifest. An instruction path can be exposed
for deep loading only after its skill is active.

Activation describes required work; it is not authority. In particular,
`executionMode: write` produces a `writePermissionRequirements` entry but no
permission or approval field. Effective permissions remain exclusively in the
separate host-owned governance/authority inputs defined by CTX-03.

Profiles without `skill_activation` use an explicit `legacy-fallback`: every
declared candidate remains initially active and the compiler/legacy renderer
emits a migration warning. This preserves existing single-run behavior while
making non-migrated profiles visible. The legacy renderer remains available;
CTX-04 adds no phase runner, evidence store, or runtime-v2 default.

CTX-04-R1 makes the compiled manifest the single routing input:

```text
profile + authoritative catalogs + host signals/requests
  -> compile canonical context-manifest-v1
  -> structural validation
  -> authoritative comparison against a host-derived expected manifest
  -> cast/execution-plan
  -> run-profile prompt and runner-class routing
```

`execution-plan.sh` no longer derives selected work, escalation, model tier,
risk, execution mode, delegation group, or parallel safety from the full
profile candidate list. `cast.sh` compiles once, publishes the same canonical
bytes after the execution boundary, and passes that immutable manifest to
`run-profile.sh`. A directly invoked runner compiles one manifest itself. The
runner validates any supplied manifest against the framework root, profile ID,
execution ID, static signals, semantic requests, and deep-load requests before
materializing the accepted canonical bytes into one immutable in-memory value
used by both execution-plan and prompt construction. It never reopens the
caller-owned candidate pathname after validation. A caller cannot supply
alternate profile, skill-index, agent, or expected-manifest documents to make
candidate data authoritative.

Structural schema validation and authoritative semantic validation are
separate operations. Cross-field consistency is defense in depth only;
semantic anti-tampering is the byte comparison with a fresh expected manifest
derived from host-resolved framework sources. This covers skill membership and
provenance, active metadata, execution mode, artifacts, semantic agents,
fallback mode, conditionals, and deep loading.

Activation parsing has exactly three outcomes. An absent `skill_activation`
key selects `legacy-fallback`; a present valid block selects `declarative`; a
present malformed, partial, duplicate, conflicting, or unknown-key block is a
hard failure. Mapping one conditional skill from more than one signal is
invalid, so activation evidence is never discarded by choosing one trigger.
The deterministic legacy warning is present in the manifest and emitted on
stderr while canonical JSON remains isolated on stdout.

The host compiler may read the complete skill index and authoritative agent or
artifact metadata. The model prompt receives the compiled manifest, selected
semantic workflow documents, and only explicitly deep-loaded active skill
bodies; it is not asked to inspect the complete index or inactive candidates
to reconstruct routing. This is CTX-04 progressive loading only and introduces
no CTX-05 evidence store or CTX-06 phase runtime.

## CTX-05 host-owned evidence store and bounded retrieval

`mana evidence` is a provider-neutral local API for collecting evidence once
and retrieving it by stable `E-*` reference. It writes only under the
Git-ignored `.mana/runtime-evidence/` root. Each execution owns an
`evidence-manifest-v1` inventory bound to a canonical `workspaceId`. The host
derives that identifier from the authorized Mana workspace kind/name recorded
by its manifest; callers cannot supply an identifier and no absolute path is
persisted as identity. Immutable source and normalized content blobs
are stored separately and deduplicated by the digest of their sanitized bytes.
An evidence record is a different identity layer: its deterministic `E-*` ID
also binds execution, kind, source system, sanitized locator, revision, raw and
normalized digests, normalization version, media type, sensitivity,
relationships, collection status, and `workspaceId`. Unchanged bytes with unchanged
provenance return the prior record; shared bytes with different provenance or
normalization remain distinct evidence records without duplicating blobs.

Collection redacts credential-shaped values and authorization headers before
any digest, record ID, payload, or source locator is produced. The policy covers
authorization/proxy authorization, cookies, credential-named JSON and form
fields, textual credential assignments, URI user information, and sensitive
query parameters. JSON must parse before a `complete` record can be written;
structured media that cannot be sanitized safely is rejected. Digests and IDs
therefore describe only the sanitized persisted bytes and metadata. Collection
time is operational metadata, never a claim of source freshness; `revisionId`
records source freshness only when the collector has it.

All evidence I/O reuses the CTX-03 root-FD boundary: component-wise no-follow
traversal, directory FDs, final-FD classification, parent re-attestation, and
the kernel no-replace/exchange writer with anchored rollback and cleanup.
Input, manifest, blob, publication, and enumeration paths do not use a
check-then-reopen pathname sequence. Evidence input is confined to the
authorized project root.

The manifest makes all collection outcomes explicit. `complete` has validated
source and normalized blobs and permits retrieval. `partial` has a sanitized
partial payload plus bounded error and gap metadata, but is never retrieved as
complete. `failed` and `unavailable` contain bounded privacy-safe cause metadata
and no payload; retrieval is rejected.

`read` emits only UTF-8 text, enforces a 16 KiB output cap, and rejects binary
or oversized content. `extract` (and the compatibility `read --lines` form) is
the explicit bounded path for a strict-subset line, RFC 6901 JSON Pointer, or
byte-range selection. Full line/byte ranges, non-canonical array indexes,
invalid pointer escapes, empty/inverted/out-of-range ranges, and implicit
full-payload fallback are rejected. Every range result carries the originating
evidence provenance and is capped after selection. CTX-05 adds no phase runner,
model call, permission, or approval surface.

## CTX-06A phase-run directory contract

`scripts/mana-context-pipeline.sh initialize` is the deliberately narrow first
slice of the fresh-phase runner. It creates a new, provider-neutral directory
at `.mana/runtime/runs/<execution-id>/` with a host-generated immutable
`execution-envelope-v1.json`, the CTX-04 authoritative
`context-manifest-v1.json`, one `run-directory-v1.json`, and one bounded
`phase-input-v1.json` below `phases/<ordinal>-<phase-id>/` for only the initial
declared phase. Phase identity, ordinal, and policy come solely from the
host-owned `context_runtime.pipeline` profile declaration. The CLI has no phase
selection or ordering option. A profile without a complete v2 declaration,
including explicit target, workspace, human-gate, and per-phase evidence
policy, is not configured and fails closed. `requested-pr-review` deliberately
has no such declaration until PRC-03.

The initializer derives the envelope from trusted host inputs plus the profile
declaration. The requested workspace must be an existing, FD-contained
canonical Mana feature/session workspace whose manifest matches its path.
Target presence and shape follow the declared target kind, and a profile that
requires approval must declare the human gate IDs copied into the envelope.
Permissions remain the fixed read-only CTX-06A capability. None of these fields
is accepted from a model-owned phase input.

Publication is transactional. A private mode-`0700` staging directory is
created below `.mana/runtime/runs/`; envelope, compiled manifest, run record,
and initial input are materialized and validated there through the same held
staging and parent directory descriptors. One kernel no-replace,
directory-FD-relative rename publishes the complete directory, followed by an
explicit host commit barrier. Any pre-existing final entry, including an empty
directory, is a collision. A signal guard records `SIGINT` and `SIGTERM`
throughout this critical section instead of relying on a pending-signal check
and unmask sequence. Before the barrier, failure, `KeyboardInterrupt`, or a
recorded signal aborts the transaction. If the final name is already visible,
the host first renames that exact inode atomically to a private abort name
through the held parent FD, then removes it through recursive
FD-relative/no-follow cleanup. `_published` is set only after the barrier.
After the barrier the run is committed. A later `SIGINT` or `SIGTERM` does not
abort or remove it: the CLI retains the final run, returns 130 or 143
respectively, and reports explicitly that the signal arrived after commit.
Successful pre-barrier abort leaves no final, staging, or quarantine entry.

When a canonical same-project and same-execution CTX-05 evidence manifest is
supplied, the host requires its host-derived `workspaceId` to equal the
envelope and run-record identity before binding it to the workspace.
Initial evidence references must exist in it and satisfy the initial phase's
declared kind and collection-status policy. Without that manifest the reference
list is empty. The bounded objective is one host-owned line and structured
transcript payloads are rejected. Case-insensitive role labels (`user`,
`assistant`, `system`, `developer`, or `tool`) are rejected at the start of the
objective or after the supported structural separators `;` and `|`; ordinary
prose containing those words remains valid. The initializer performs no provider
invocation, lifecycle event, metric collection, checkpoint acceptance, resume,
or future phase input creation. Those behaviors remain outside CTX-06A; the
legacy runner is untouched.

## CTX-06B-R1A authoritative state machine and transition validation

R1A adds the host-owned `run-state-v1.json` initial record and a pure checkpoint
reducer. Initial state is revision zero: the first declared phase is on attempt
one and every future phase is on attempt zero. Each phase declaration owns an
explicit `retry_limit`; neither checkpoint data nor a caller-supplied next-state
document can supply attempts, revisions, retry limits, phase position, or run
status. The reducer derives the entire next state from the validated previous
state and one permitted transition, increments revision once, and increments an
attempt only when it actually selects a new phase attempt.

The reducer binds checkpoint, execution envelope, CTX-04 context manifest,
CTX-05 evidence manifest, previous state, and optional typed host authority to
one execution/version/profile. The CTX-04 manifest is recompiled and compared
against authoritative framework sources. The CTX-05 manifest must belong to
the same execution and host-derived workspace. Every `evidenceRefs` list is checked: nested factual
references use the current phase policy and top-level handoff references use
the requested target phase policy.

`evaluate_checkpoint` is the only approval evaluator. Requested gates must be
declared by the profile; terminal completion requests every declared gate, and
all requests must resolve to matching host approval records. An unresolved or
model-reported block produces host `blocked` state without consuming another
attempt. That checkpoint can be reconsidered only with matching typed host
authority. Authority cannot override an exhausted retry limit.

Partial or blocked checkpoints may request only a bounded repeat of the current
phase. A complete checkpoint may select only the immediately following phase,
or may request `stop` when the current phase is the final declared phase.
`completed` is therefore derivable only from a complete terminal checkpoint
whose human gates resolve. Completed and interrupted states accept no R1A
checkpoint transition.

R1A itself remains pure; CTX-06B-R1B composes its result into the durable
publication protocol below. Provider invocation, lifecycle events, metrics
integration, and legacy selection remain outside CTX-06B; CTX-06C and later
behavior is unchanged.

## CTX-06B-R1B immutable transition publication

The run's root `run-state-v1.json` is the only mutable HEAD. Every accepted
checkpoint or approved resume is first materialized as one complete immutable
bundle below `transitions/T-<sha256>/`. The transition ID hashes the operation,
canonical previous-state digest, checkpoint digest, and optional typed authority
digest. A private staging directory contains the checkpoint, derived state,
optional current phase input, optional resume authority, and a digest-bound
manifest; one FD-relative kernel no-replace rename publishes the complete tree.

Publication alone grants no authority. The host advances HEAD once with an
exact-byte compare-and-swap from the state used by the reducer to the bundled
state. An inode-stable run-local lock serializes the exact-byte check and atomic
replacement, preventing an optimistic losing swap from becoming transiently
visible. The committed state names the winning transition ID and previous-state
digest. That reference plus each manifest's previous transition ID forms the
authoritative chain. Bundles that are visible after a crash or that lose a CAS
remain non-authoritative, so neither their checkpoint nor their future input is
selectable by consumers.

Identical operations derive identical IDs and converge on one bundle. A retry
recognizes an already committed transition or completes the pending HEAD CAS;
`reconcile` performs the latter idempotently. Reusing an operation/checkpoint
identity with different canonical inputs is rejected as a conflicting
duplicate. Competing transitions from one HEAD are linearized solely by the
single CAS, including concurrent resume: exactly one next revision becomes
authoritative. This is not an ordering inversion of three independent writes;
checkpoint, state, and phase input have no independent authority surface.

## CTX-06B-R1C permanent transition fault matrix

R1C freezes the R1A reducer and R1B publication protocol behind a permanent,
zero-provider fault suite. It injects failures before, during, and after bundle
publication and HEAD CAS; across checkpoint acceptance and next-phase input
creation; and while retrying or reconciling a crash-visible bundle. After every
injection the suite re-loads canonical HEAD and replays the digest-bound history
to prove there is exactly one authoritative, recoverable state.

The matrix also covers concurrent and blocked resume, authority-present and
authority-absent paths, forged state/history, foreign CTX-04/CTX-05 manifests,
nested unknown evidence references, retry exhaustion, and non-terminal early
stop. This is verification-only scope: provider dispatch, lifecycle events,
metrics, and all CTX-06C+ behavior remain unchanged.

## CTX-06B-R1D HEAD cleanup and workspace binding hardening

After a run-state exchange, the final name is the new authoritative HEAD and
the private temporary name denotes the displaced old HEAD. The writer updates
that tracked identity immediately, verifies it against the CAS expectation,
and removes it only through the held directory FD without following links. A
normal successful CAS leaves no private temporary.

A process death after exchange can leave the committed new HEAD plus that old
entry. Before accepting later work, reconciliation replays the authoritative
bundle chain and derives the exact previous state of the transition named by
HEAD. It deletes exactly one private candidate only when its canonical bytes,
inode/type, previous-state digest, and committed transition relationship all
match. A malformed, tampered, duplicated, stale, or otherwise ambiguous
candidate fails closed and is retained; filename shape alone never authorizes
deletion.

R1D also carries the host-derived `workspaceId` through the execution envelope,
authoritative run record, and CTX-05 manifest. R1A/06B transition validation
requires execution and workspace bindings together. This hardening changes no
reducer, retry limit, approval decision, transition identity, immutable bundle,
single-HEAD, concurrency, or provider behavior, and introduces no CTX-06C work.

## CTX-06C provider execution, lifecycle, metrics, and legacy selection

`scripts/run-profile-v2.sh` consumes an already initialized run and launches
one host-owned provider process for each authoritative active phase. Before a
model call, `prepare-phase` validates the run directory, re-derives the CTX-04
manifest from framework sources, replays the complete committed CTX-06B chain,
and selects the phase input only through HEAD. It returns canonical objects,
not caller-reopenable artifact paths. A run-local advisory lock serializes
provider work for the whole run; it prevents two hosts from duplicating a
phase invocation, while immutable bundles and the run-state CAS remain the
only state authority.

Every prompt is rebuilt from the invariant phase kernel, the exact immutable
execution envelope, the authoritative context manifest, only the current
phase policy/input, and the immediately previous validated checkpoint when
one exists. It contains evidence IDs but no evidence payload or provider
transcript. A future phase never receives an earlier phase policy or prompt.
CTX-06C currently accepts `phase-checkpoint-v1` as its provider output contract;
profile-specific terminal artifact transports remain owned by their later
profile migration phases.

The runner probes the installed provider through the CTX-02 contract before
execution. Fresh invocation, ephemeral session, explicit root-model selection,
and hard child disable must all be proven `supported`; `unknown` and
`unsupported` fail closed. Codex uses its read-only sandbox, ephemeral/user-
isolated process, native schema file, separate final output, and both child-
feature disables. Claude uses print/no-persistence/safe mode, native JSON
Schema output, and explicit denial of child, shell, write, and network tools.
The present OpenCode report cannot prove hard child disable, so its phase
adapter is not selectable. Even a phase declared `subagents: optional` runs
without children here; provider-managed child execution belongs to CTX-07.
If native structured-output enforcement is not proven but all isolation gates
pass, the runner reports an explicit host-validation fallback and still
rejects any invalid checkpoint before publication.

Provider output is held in a mode-restricted temporary file. A valid canonical
checkpoint is handed to `accept-checkpoint`; only the resulting immutable
bundle and winning HEAD CAS make it authoritative. Invalid output, semantic
transition failure, and provider failure perform no automatic retry. On an
interruption, the last already committed checkpoint/phase input remains the
resume point and no provider stream enters the run directory.

Phase lifecycle is recorded as additive privacy-safe runtime events. CTX-01
usage summaries are archived per phase/attempt/invocation and aggregated at
the existing execution metric path. The records contain only numeric usage,
bounded operational counters, phase identity, attempt, provider version, and
status. Raw event streams remain deleted by default; explicit debug traces are
kept per invocation with mode `0600` and never enter checkpoints or events.

`scripts/run-profile.sh` selects this path only with
`--context-runtime v2` plus an existing
execution ID. `legacy` remains the default and follows the existing renderer,
agent installation, provider dispatch, output, and artifact behavior. A v2
request with a missing run or capability gap never silently falls back to the
legacy single-session runtime.

## CTX-09A host mode plumbing

The public modes are exactly `legacy`, `shadow`, `v2`, and `compare`.
Only the host CLI `--context-runtime` selects a mode; an ambient
`MANA_CONTEXT_RUNTIME_VERSION` is rejected, including when an explicit CLI
mode is present. Model/task/checkpoint/provider data cannot select a mode.
Default and explicit legacy share the same runner, output and allowed effects,
including propagation of provider failure status; they create no mode hand-off.
V2 dispatch is exclusive, explicitly selected, and has no legacy fallback.

Shadow runs legacy once and forwards its stdout and exit status. Admission
rejects publish/discovery flags, mutating plans and unspecified skill/agent
effect authority. No remote update check runs before isolation. A fixed macOS
host sandbox denies application writes and
network for the whole legacy process tree; only private scratch and the
existing legacy metrics namespace are writable. Its capability probe precedes
legacy execution; unsupported hosts fail closed, without a prompt-only or
caller-selected backend fallback.

## CTX-09C-R1A canonical shared input and isolated shadow namespaces

The host captures the compiled manifest, exact legacy prompt and provider argv,
target/work item, authorized evidence snapshot, and materialized CTX-08 policy
and mode decision in one versioned canonical packet. A private temporary capsule
uses 0700 directories and 0600 files; held read-only descriptors and actual-byte
digests attest every consumption. Both fixed consumers receive the same canonical
stdin bytes. Legacy executes the captured prompt/argv without recompiling;
v2 derives fresh phase packets and uses the unchanged CTX-06 pure reducer.
Source replacement after capture cannot change their materialized input.

The shared comparison identity has separate legacy/shadow producer, invocation,
lock, run and metric identities. Shadow state is ephemeral, and its metrics
live beneath its separate private run view below `.mana/runtime/shadows/`.
Shadow never reads/resumes the legacy run, HEAD or aggregate. Shared existing
`.mana/runtime` permissions are preserved. Native sandbox-exec admits only proven
containment: writes are limited to shadow scratch/run/metrics, and network is
denied for the whole shadow tree. Backend absence, unknown proof, nested denial
or provider/pipeline capability gaps produce `shadowStatus: unavailable` with
no shadow invocation or weaker fallback. Legacy always runs independently and
its stdout and exit status remain authoritative, including on shadow failure.

Only identity, actual-byte digests and bounded metadata survive. Packets, prompts,
raw input/evidence and provider outputs are not delivery artifacts and are not
persisted. Numeric usage comparisons retain null/missing dimensions and the
provisional CTX-08 calibration. R1C replaces the metadata-only projection with
an admission boundary: stdout must be a bounded, privacy-safe, schema-valid and
semantically valid CTX-09B input before producer publication. Invalid candidates
retain only a host category/status and safe bounded count, never raw bytes or a
secret correlation digest. Both valid receipts, identities and file-instance
commitments are required before the offline comparator can run; otherwise its
outcome is unavailable/indeterminate, never equivalent. The test-only backend
remains outside production selection and supplements, rather than masks, the
native containment probe. Profile pipeline migration remains out of scope.
The local fixture framework is reachable only through a separate test entrypoint,
never a production framework/backend selector.

## CTX-09C-R1B legacy authority and recovery journal

The live-shadow host now has an authority barrier: legacy is executed and
committed before shadow admission. Its immutable receipt binds exit status,
the separate sensitive local exact stdout/stderr outcome and bounded metadata; the corresponding
single live-shadow HEAD is the only current state. Thus a later shadow,
usage, receipt or comparison error cannot influence caller output/status.
Nonzero legacy is the explicit R1B policy boundary and suppresses shadow.

Each comparison namespace has immutable transition bundles and one CAS-replaced
HEAD. Recovery accepts only receipts whose artifact bytes/digests validate,
then advances the missing HEAD or continues from shadow/compare. An incomplete
intent is ambiguous and becomes manual recovery rather than replaying legacy.
R2B re-attests an exact outcome independently of the comparison projection;
concurrent callers serialize on the comparison lock and replay both original
streams and exit status. The post-HEAD authority barrier covers RuntimeError
and host context cleanup as well as shadow/comparison failures. Missing or
tampered exact authority requires manual recovery without side-effect replay.
See the [R2B contract](../standards/context-runtime-contract.md#ctx-09c-r2b-exact-legacy-outcome-authority-and-caller-convergence)
for private receipt commitments, permissions and retention/cleanup.
R2C walks and re-attests the complete reachable bundle chain and every producer,
receipt, file-instance and outcome commitment before HEAD reuse or CAS. One
immutable comparison attempt reserves the sole offline invocation; a valid
pre-HEAD attempt is adopted after a crash, while an ambiguous attempt is
terminal and never re-executed. The comparison HEAD is a stage of this same
single CAS journal. A fixed private packet locator is committed before input
publication; the next lock holder reconciles it and all handled exits remove
the packet. See the [R2C contract](../standards/context-runtime-contract.md#ctx-09c-r2c-full-re-attestation-exactly-once-comparison-and-crash-reconciliation)
for the real fault matrix, caller convergence and deterministic cleanup.
The shadow provider runs in a new session with a host-owned deadline and full
TERM/grace/KILL/reap group cleanup. The CTX-09B comparator remains unchanged
and remains diagnostic-only.

Compare only registers two host-published project-relative regular single-link
files with committed host producer receipts, verified runtime roles and both
actual-byte SHA-256 and local file-instance identities. Registration binds the
selected host profile and explicit `--comparison-target-key`; labels cannot
make an artifact a legacy or v2 producer. It invokes neither runtime,
does not modify either source, and produces no semantic result or authoritative
output selection. Its registration command still produces no semantic result;
the separate CTX-09B offline consumer is described below. See the [CTX-09A contract](../standards/context-runtime-contract.md#ctx-09a-host-mode-plan-and-local-hand-off).

## CTX-09C-R3A admission boundaries

The live host compares any preexisting semantic artifact against the current
derived candidate, using a private binding of side execution/runtime/workspace,
comparison/profile/target, shared packet, projection and producer receipt. The
legacy binding includes the current exact outcome; shadow is reprojected from
its current completed CTX-06 chain. A missing or different binding rejects reuse.
The exact legacy outcome is published and attested before semantic projection
and producer receipt publication; only the subsequent legacy HEAD barrier
permits shadow invocation.

The shadow consumer uses the shared semantic privacy guard before each CTX-06
checkpoint commit. Rejected data cannot reach a completed HEAD or an eligible
producer artifact. Sensitive exact legacy streams remain a separate local
delivery surface. The production mode helper has no permissive backend selector;
offline registration fixtures live under tests. Shadow usage is captured even
after failure, timeout or interruption, independently of execution status.
Caller workspace binding and further HEAD/bundle re-attestation/crash recovery
remain outside R3A; the general reducers and offline comparator are unchanged.

## CTX-09C-R3B bound recovery graph

The shared packet now anchors the comparison to one host-derived Mana workspace
and to its CTX-04/05 identities before either producer boundary. The isolated
shadow view recreates that exact workspace identity and the CTX-06 envelope,
run record, evidence manifest and context manifest all agree on execution,
version, workspace and profile.

The recovery graph has three independently sealed surfaces: exact legacy
delivery, the completed CTX-06 shadow chain, and the CTX-09B comparison attempt.
Per-revision HEAD commits bind both HEAD and tip bundle instances; descendant
bundles bind predecessors and state binds every outcome, producer, projection
and comparison instance. Recovery can therefore adopt a complete publication
without blessing a same-byte replacement. A complete shadow chain can regenerate
only its missing semantic projection and receipt; it cannot cause another
provider invocation.

Exact-outcome stages and backend scratch carry explicit comparison/invocation
owner records. Reconciliation validates those records and removes only the
corresponding held-FD tree or stage. Unknown pattern matches are not cleanup
authority. The comparison lock plus the existing single HEAD CAS yields one
winning recovery while all callers replay the same exact legacy outcome.

## CTX-09B deterministic semantic comparison

`scripts/mana-context-compare.sh EXECUTION_ID --project-root PROJECT` consumes
only the two existing local sources registered by a canonical CTX-09A compare
mode-plan. It reopens the registration and both sources with the shared
FD-relative/no-follow reader, hashes the exact captured bytes subsequently
parsed, resolves the host-derived producer receipt/commit paths again, and
rejects any runtime/receipt/content/object binding mismatch. There is no runtime,
provider, worker, model, service discovery or publication invocation.

The provider-neutral, closed semantic input contract records typed finding
subjects/predicates, observations, coverage, uncertainty and evidence metadata.
Display labels, JSON formatting/order, declared set order and provider-local
finding/evidence IDs are not semantic meaning. Negation, severity, validation,
status, requirement coverage, approval, risk/escalation, evidence identity,
questions, artifact completeness, available human disposition and observed
write policy are semantic data. No free-text claim/paraphrase inference occurs.
Existing Markdown and phase artifacts without this explicit projection remain
indeterminate; there is no exporter, migration or model-assisted fallback.

CTX-09B-R1 indexes all structured stance-bearing claims globally by typed subject
and predicate across presentation dimensions. Compatible repeated stances remain
valid. Affirmed/denied contradictions and explicitly contradictory uncertainty
retain all original dimensions, pointers and provenance in an ordered `conflicts`
collection and force `indeterminate`, `complete: false`, reason
`unresolved_internal_conflict`, including identical contradictory inputs.

Fixed legacy/v2 host publication APIs atomically publish local bytes and then
canonical immutable producer receipts and separate receipt-digest commitments.
No comparator/registration producer flag or caller-selected receipt is accepted.
Native artifact profile/target declarations are individually bound to their
verified receipts; mismatches yield incomplete `indeterminate` diagnostics even
when both artifacts agree on the same foreign identity.
The file-instance commitment is obtained via fstat on the real publication FD
and contains device, inode, type/mode, size and nanosecond mtime/ctime. It is
verified before/after captured reads together with CTX-03 path re-attestation;
replacement with a new inode and identical bytes fails closed. Content SHA-256
still binds the bytes. Object identity is local to the filesystem/run, not a
portable universal content address. The producer harness is explicitly test-only;
this repair adds no live shadow harness or semantic exporter. See the
[publication contract](../standards/context-runtime-contract.md#ctx-09b-r1-producer-publication-and-local-identity).

Every observation retains its original JSON pointer and record/evidence IDs.
An absent counterpart is only a one-sided observation; partial collections
cannot prove a finding was missed. Missing/unknown data, unusable provenance,
unresolved questions or required unavailable escalation prevent equivalence.
Known mismatches can coexist with explicit incomplete dimensions. Equivalence
is limited to declared structured semantics, not evidence truth, readiness or
non-degradation approval. Human review is always required.

Default output is canonical JSON on stdout with no filesystem writes.
`--write-report` optionally creates only the derived private local
`semantic-comparison-v1.json` beside the registration, atomically/no-replace;
source artifacts and the mode-plan are unchanged. Neither diagnostic chooses
an authoritative output or grants permission. No generated diagnostic timestamp/random ID, prose,
raw evidence, diff, prompt/response/reasoning, credential or arbitrary environment
is persisted. CTX-09G release audit and CTX-10+ remain outside this phase. See the [CTX-09B contract](../standards/context-runtime-contract.md#ctx-09b-deterministic-semantic-comparison).

## CTX-07A delegation contracts, ownership, and merge boundary

CTX-07A adds no worker invocation, provider model routing, or provider-managed
child adapter. `bind-plan` accepts only an unbound task intent and obtains
`executionId`, `executionVersion`, `workspaceId`, `profileId`, `phaseId`, and
`attempt` from the current phase packet resolved through the CTX-06B
authoritative HEAD. `planId` is `P-` plus SHA-256 of the canonical validated
plan identity projection, excluding only derived plan/task digest fields.
Each `taskDigest` is SHA-256 of the canonical bound task excluding only that
digest. A caller-supplied bound plan is accepted only when all identities
recompute exactly against the same current packet, which rejects foreign and
stale-attempt replay.

Each task has structural read-only policy: a read-only `taskType` enum,
`effectClass: read`, `delegationAllowed: false`, and `maxChildDepth: 0`.
Typed scope, active read/parallel-safe CTX-04 skills, expected output,
stop-condition enums, CTX-05 evidence references, and bounded evidence gaps
are explicit. Generic instructions, commands, tools, permissions, ambient
context, prompt history, transcripts, nested tasks, and authority or approval
fields are absent and rejected. Free-form question text is non-authoritative.
Operational sandbox enforcement and the absence of child tools are CTX-07B
responsibilities; CTX-07A ensures no valid contract can request broader
authority.

`questionKey` is host-derived from the NFC/whitespace-canonical question,
typed scope, task type, and expected-output contract. `ownershipKey` is then
derived from that question key and the single owner. Reusing one canonical
question for another task or owner fails. This is canonical identity, not a
claim that semantic paraphrases can be recognized.

`evidenceRefs` resolve to existing records in the authoritative CTX-05
manifest and must match its execution/workspace binding plus the current phase
kind, status, and explicit input policy. `evidenceGaps` are separate typed
descriptions of unavailable evidence; for example `missing recovery test` is
a valid bounded gap and is never looked up as an evidence ID or accepted as
proof of a fact.

`bind-result` adds the exact plan/task/current-phase binding and a canonical
`resultDigest`. Every fact, finding, assumption, inference, open question,
evidence gap, artifact reference, and uncertainty record carries point
provenance with `taskId`, `planId`, `sourceResultDigest`, and its pertinent
evidence references. Results cannot activate skills, widen scope, add
permissions, complete approval, change owner, or transport transcripts,
reasoning, or bulk evidence.

`merge-results` rejects unknown or duplicate results, represents missing tasks
as `incomplete`, and emits canonical task-sorted bytes independent of result
argument order. The lossless output retains full results by task and separate
canonical collections for facts, findings, assumptions, inferences, open
questions, gaps, artifacts, evidence references, uncertainty, missing task
IDs, conflicts, and merge status. `claimKey` is derived from typed subject and
predicate. Opposite `affirmed`/`denied` stances for one key produce
`conflicted` without resolution; compatible or structurally incomparable
claims remain preserved. The merge performs no semantic synthesis, creates no
facts or severity, writes no run artifact, advances no HEAD, and invokes no
provider. Fresh workers/model routing remain CTX-07B; provider-managed children
remain CTX-07C.

## CTX-07B-R2 host-owned isolated worker runtime

`scripts/run-context-workers.sh` consumes one CTX-07A bound plan that still
matches the active phase selected through CTX-06B HEAD. It does not take a
phase-global worker lock: deterministic per-task claims serialize equal work
while unrelated read-only tasks remain parallel. The
canonical plan remains host-private. Every provider process receives one
versioned, host-built worker context packet. The packet contains the pertinent
read-only execution envelope, exactly one validated CTX-07A task, a task-only
CTX-04 projection with the canonical source-manifest digest, metadata and full
body for only the task's active skills, authorized evidence references, the
output contract, and the host-selected model/effort route. It excludes parent
transcript/prompt, siblings, phase input/checkpoint, candidate and inactive
skill bodies, raw evidence, complete run state, and additional permissions.

The framework root is derived from the canonical installed runner and is not a
CLI, environment, packet, or manifest input. Policy, skill metadata/bodies,
capability metadata, and schemas are read component-by-component without
following links. Model routing is fully materialized before invocation; a
later policy mutation cannot rewrite the selected packet or provider argv.

Each real attempt starts a separate provider process. The CTX-02 gate must prove fresh
invocation, ephemeral session, explicit root-model selection, and hard child
disable before any worker call. Codex and Claude use the same read-only,
user-isolated, child-free controls as CTX-06C through a worker-specific adapter.
The current OpenCode capability report still cannot prove hard child disable
and is rejected. Unknown and unsupported isolation capabilities fail before a
model call with `needs_model_escalation`; there is no prompt-only fallback and
no provider-managed child path in CTX-07B. Native structured output is used
when proven, while the existing mandatory host validation is the only allowed
fallback for that transport capability.

Model routing is a pure host derivation. A task routes to `full` when its typed
scope is architecture, contracts, database, operations, or security, or when
one of its CTX-04-authorized task skills declares `modelTier: full` or
`riskLevel: high`. Other bounded read tasks route to `economy`. A checked-in,
versioned Mana policy maps provider, tier, concrete model ID, reasoning effort,
and admitted scope/risk. Worker CLI flags, environment variables, task fields,
question prose, and provider output cannot select or weaken the route.

CTX-02 proves only explicit model and, when required, effort selection
mechanisms. Mana policy admission is separate; neither proves that a concrete
model ID exists at runtime. Provider rejection of a host-selected model is an
explicit transport failure. Missing full/high-risk mappings fail closed. The
complete CTX-07A validator runs before policy resolution or packet creation.

The host may run independent plan tasks concurrently, capped by both the
CTX-04 `directWorkers` limit already enforced by CTX-07A and an optional lower
host concurrency setting. Every accepted task is structurally read-only and
parallel-safe, so CTX-07B has zero writers. Each worker may retrieve only the
task's authorized CTX-05 references through the bounded evidence API; evidence
content is materialized only as bounded authorized extracts in a private mode
`0700` capsule. The provider runs with that capsule as its cwd under a verified
host isolation backend. Absence or uncertainty of that backend fails before
provider invocation; there is no content-only fallback. The provider receives
neither project/run/evidence-store paths nor sibling evidence. Capsule files
are regular, single-link, read-only inputs. The capsule and default-discard raw
trace are removed on success, failure, timeout, and interruption; only an
already materialized host debug-policy decision can retain the trace.

Each provider is the leader of a dedicated process session. Host-owned timeout
and grace values drive TERM then KILL of the entire process group, followed by
wait/reap. Timeout, SIGINT, and SIGTERM remain distinct terminal outcomes.
The group is also drained when its leader exits successfully or fails before
its descendants. The watchdog owns and reaps its timer processes. Backend
selection uses the fixed OS path `/usr/bin/sandbox-exec`, never caller `PATH`.
The OS probe uses physical capsule paths and the minimal dyld bootstrap reads;
system runtime reads do not grant access to project or evidence content.
Failure to prepare metric storage stops transport before provider execution.

The provider emits a `delegation-result-draft-v1` object. The host validates
the transport schema and declared output sections, then delegates all binding,
digest, provenance, evidence, ownership, and semantic validation to the
unchanged CTX-07A `bind-result` implementation. Canonical results are published
first as immutable per-invocation attempt artifacts and become authoritative
only when a per-task result HEAD is committed with CTX-03 CAS. Reuse requires
safe reread, full CTX-07A validation, task/execution/digest binding, and HEAD
reachability. Attempt artifacts not reachable from the task-result HEAD are
not authoritative. The CTX-06 phase HEAD is never changed by worker result
publication.

The host creates a unique invocation ID when it acquires the deterministic
task-execution claim. Known terminal failures close the claim immediately;
expired active claims can be reconciled by CAS. Privacy-safe immutable events
cover claim, start, result acceptance/reuse, completion, failure, timeout,
interruption, and reconciliation. Immutable usage artifacts are keyed by
invocation ID and retain null for unavailable token dimensions; reuse creates
no invocation or usage duplicate. A deterministic aggregate names every
included invocation and is rebuilt from those immutable artifacts.

Before result publication, the host writes an immutable per-invocation receipt
containing the already bound result, safe numeric usage, and terminal claim.
Under a short FD-anchored per-task state lock, recovery replays attempt, HEAD,
metrics, deterministic lifecycle events, aggregate, and finally claim closure.
The lock is never held during provider execution. Replaying a receipt cannot
invoke a provider or advance phase HEAD. An explicit publication failure before
HEAD records a separate immutable failure receipt, preventing the original
intent from becoming authoritative on retry. A committed HEAD is irreversible.
Claims validate exact fields, host identity and the code-owned lease duration.
Recovered staging is removed only after canonical/semantic validation and a
fresh FD-relative inode/byte check; ambiguous or hostile artifacts fail closed.

A provider or validation failure receives no retry, contributes no accepted
result, produces an incomplete merge, and returns nonzero. The worker runner
writes no delegation artifact into the run, advances no HEAD, grants no
authority, and performs no semantic synthesis. Optional provider-managed child
adapters and their capability fallbacks remain exclusively CTX-07C.

CTX-07B-R2E captures provider stdout and stderr as separate streams. Stdout is
the untrusted transport object. Stderr exists only in a per-invocation
temporary mode-`0600` file below a mode-`0700` private directory; it is deleted
after every handled terminal outcome and is never copied to runner output,
lifecycle, usage, aggregate metrics, claims, results, receipts, or public error
text. A transport failure exposes only a bounded host-generated category,
provider, invocation ID, and exit status. Provider-controlled diagnostics are
never excerpted.

Raw trace retention is separate from stderr. The versioned host policy at
`config/context-runtime/worker-debug-policy-v1.json`, loaded from the canonical
framework root, defaults to `discard`. Production exposes no CLI, environment,
task, manifest, or provider-output retention switch. The host materializes the
policy identity, digest, and boolean decision before invocation, so a later
source-policy change cannot affect the current prepared plan. Explicit
`retain` preserves the provider stdout/event trace on complete, failed,
timed-out, and interrupted attempts at
`worker-executions/<taskExecutionKey>/attempts/<invocationId>/raw-provider-trace`.
The file is mode `0600`, its attempt directory is mode `0700`, and its immutable
invocation metric reports the actual filesystem state. Concurrent invocations
use distinct IDs and paths; reuse creates neither an invocation nor a trace.
Lifecycle and aggregate metrics contain no raw bytes or trace path.

A retained raw trace is a local, potentially sensitive debug artifact. It is
not privacy-safe and is not a delivery artifact. The debug policy does not
retain the separate provider stderr stream.

The permanent R2E recovery fixtures exercise real boundaries. `after-provider`
invokes and reaps the provider before crashing ahead of normalization;
`before-bind` completes normalization before crashing; and `after-bind` creates
a valid CTX-07A-bound result before crashing ahead of task-result HEAD
publication. Each proves provider reach, absent result HEAD, unchanged CTX-06
HEAD, stale-claim reconciliation, exactly one new successful invocation,
immutable metrics and truthful lifecycle for both attempts, and no recovery
temporary residue.

## CTX-07C optional provider-managed child adapter

`run-context-workers.sh` preserves CTX-07B as its default and correctness-
critical transport. The additive `--provider-children disabled|prefer|require`
host policy is evaluated only after the complete CTX-07A plan and host routing
have been materialized. `disabled` is the default. `prefer` selects a managed
child only when the current CTX-02 report proves every required property and
otherwise selects CTX-07B before any provider invocation. `require` reports
`needs_model_escalation` and invokes no provider on the same capability gap.

The enabled gate requires fresh and ephemeral root invocation, explicit root
model selection, provider-managed children, controllable isolated child
context, effective child model routing, recursive-delegation prevention,
enforced child concurrency and depth, native structured output, and complete
user/project configuration isolation. Root and child effort routing are also
required whenever the host policy supplies an effort. `unknown` and
`unsupported` are both gaps. Provider prose, task text, environment variables,
and version assumptions cannot enable the path.

CTX-07C-R2 requires `managedChildExecutionAttestation`: an ordered,
provider-native event stream. The adapter validates canonical sequence numbers
and a finite `root.started -> child.started -> child.task.bound ->
child.completed|child.failed` state machine. It rejects reordered, duplicate,
foreign, stale, incomplete, post-terminal, or ambiguously identified events;
wall-clock timestamps are not ordering authority.

After verification the host publishes an immutable, canonical mode-`0600`
managed-child receipt below the current mode-`0700` attempt directory. It binds
provider root/child identity, execution/version/workspace/profile/phase/attempt,
plan/task identity, terminal status, and the ordered-event digest to the
host-owned invocation. It contains no provider event payload, prompt, source,
reasoning, credential, or arbitrary response data. The model result cannot
supply transport, invocation, attestation, receipt, or execution-receipt
fields. CTX-07C-R3 separates terminal audit validity from success authority.
`validate_managed_child_receipt_record` and
`read_committed_managed_child_receipt_record` accept both `completed` and
`failed`; neither grants result authority. All managed-child bind, publication,
recovery, result-HEAD validation, reuse, and merge paths use
`load_committed_completed_managed_child_receipt`, which requires `completed`.
A committed `child.failed` remains readable for lifecycle/audit but cannot
authorize a semantic result, even with self-consistent fabricated provenance,
digests, result artifact, global binding, and task-result HEAD.

Managed-child authority is a fresh host-owned lookup. Python bind/validation
take project-root and host-invocation identity and derive the task execution
key from the validated current packet/task. Merge selects each invocation from
the task's committed HEAD. The resolver reads canonical private receipt bytes
through CTX-03 and checks the ordered-event digest, all identities and task
bindings, current run HEAD, current task claim, and any existing result HEAD.
An immutable no-replace `managed-child-receipt-commit.json` binds the complete
receipt digest and device/inode obtained from the same safe-reader FD. A
missing commitment, deletion, replacement (including identical bytes), mode
change, symlink, tamper, or noncanonical bytes fails closed on the next lookup.
There is no `managed_child_execution_authority(dict)` factory. Manually
constructed `ExecutionAuthority` objects cannot authorize managed children;
that API remains only for CTX-07B host-worker provenance. No receipt dict,
isolated digest, caller-selected receipt path, or cached provenance is proof.

Publication commits a global no-replace receipt/result record before the
per-task result HEAD. The record binds `receiptDigest -> taskExecutionKey ->
semanticResultDigest -> authoritativeResultHead`; an exact retry is
idempotent, while another semantic result, task, attempt, execution, invocation,
or HEAD conflicts. Reuse and authoritative merge re-read the receipt, binding,
result artifact, and HEAD and revalidate all CTX-07A authority. The semantic
digest remains transport-neutral; `executionReceiptDigest` additionally commits
the host-owned provenance and provider receipt digest.

Codex, Claude, and OpenCode continue to report
`managedChildExecutionAttestation: unknown`, and production contains no
selectable managed-child adapter for them. The complete positive and negative
transport is exercised only by a canonical test-only adapter and provider
fixture. `prefer` therefore selects CTX-07B before production provider-child
reach, and `require` fails closed. After test-only managed-child provider reach,
transport or validation failure is terminal and never falls back to CTX-07B.
No CTX-06 phase HEAD is changed and no provider-managed child is necessary for
runtime correctness.

## CTX-08 compaction and provider budgets

CTX-08 adds a versioned host policy at
`config/context-runtime/provider-budget-policy-v1.json`. It resolves a
per-profile `compact`, `standard`, or `deep` advisory budget before a CTX-06C
provider invocation. The policy contains a versioned compact prompt and
separate active-context, cumulative-input, cached-input, uncached-input,
tool-output, and child-concurrency values. `deep` raises only the budget
values; it neither grants permissions nor enables a child path.

The runner first validates the current CTX-02 report, then produces a private
control plan. Each provider setting is applied only when its exact capability
is `supported`. `unknown` and `unsupported` remain visible warnings and do not
become a guessed flag, prompt convention, or configuration fallback. Presently
the proven Claude auto-compaction threshold can be passed as `--autocompact`.
Custom compact prompts, compaction scope, retained tool-output limits, and
provider child concurrency remain absent unless a future report proves their
specific controls. Existing CTX-06C hard child disable remains mandatory and
is not relaxed by this policy.

Prompt-size estimates are advisory byte/4 planning estimates, never reported
as provider token usage. After CTX-01 archives each invocation, CTX-08 checks
the privacy-safe invocation summary and the unique invocation aggregate
separately, forwarding cumulative, cached, and uncached threshold warnings
from either scope. Incomplete aggregate coverage retains null dimensions and
cannot hide an invocation's reported exceedance. Provider compaction does not
reset reported cumulative input. A warning recommends a
checkpoint and fresh phase or a human scope decision; it never advances HEAD,
changes activated skills, drops canonical CTX-05 evidence, bypasses a required
specialist, or weakens a human/high-risk gate.

Fresh CTX-06 phase construction remains the sole deterministic context-disposal
boundary. Provider compaction is a safety net and cannot prove that a directive
was removed. The checked-in thresholds are explicitly
`provisional-no-empirical-baseline`: no real CTX-01 measured profile execution
exists in the repository. Calibration requires at least one measured profile
run with separately reported cached and uncached input before values may be
tuned or described as calibrated.

CTX-08-R1 removes the production phase runner's alternate framework root and
uses the CTX-03 FD boundary for the complete policy/inline prompt. Every profile
and mode passes schema, finite implementation ceilings and
`compact <= standard <= deep` validation. A private immutable run budget
decision records minimum, request, effective mode and technical provenance,
plus a policy snapshot/digest and host commitment. Fresh phase, resume, retry
and worker execution reuse this snapshot. A human CLI request can raise the
initial budget but cannot lower the host/profile-risk minimum or weaken any
semantic or approval requirement.

Numeric accounting now distinguishes complete, partial, unavailable and
parse-invalid usage. Phase and worker advisories share the same validity and
budget checks and a reproducible invocation aggregate. Invalid/unavailable
usage is reported explicitly rather than interpreted as below threshold.
The legacy path creates none of these CTX-08 artifacts. See the CTX-08-R1
contract and `tests/context-runtime-budgets.sh` for the permanent regression
matrix. R1 introduces no shadow execution or later roadmap phase.

## CTX-09C-R2A real projection and native read boundary

Shadow phases now commit their real CTX-06 checkpoint chain. The exporter replays
only authoritative HEAD ancestry and emits CTX-09B typed observations with
uncertainty, unavailable dimensions and committed-object provenance. Optional
`comparisonProjection` observations are checkpoint-digest-bound; prose is never
converted into semantic predicates. The result remains non-authoritative.

The fixed production sandbox permits file data reads only from shadow roots,
materialized input and explicit installed host/runtime code. Legacy and other
CTX-09C namespaces are denied for reads as well as writes. Native admission runs
operational read/escape/write/network/service canaries. Fixed import-only test
fixtures use this same enforced kernel boundary and real process supervision;
nested native denial cannot select a weaker launcher. See the
[R2A contract](../standards/context-runtime-contract.md#ctx-09c-r2a-committed-comparison-projection-and-read-isolation).
