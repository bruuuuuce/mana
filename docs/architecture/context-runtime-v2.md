# Context Runtime v2 architecture decision

Status: accepted for staged implementation through CTX-07A.

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
`--context-runtime v2` (or `MANA_CONTEXT_RUNTIME_VERSION=v2`) plus an existing
execution ID. `legacy` remains the default and follows the existing renderer,
agent installation, provider dispatch, output, and artifact behavior. A v2
request with a missing run or capability gap never silently falls back to the
legacy single-session runtime.

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
