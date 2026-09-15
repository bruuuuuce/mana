# Context Runtime v2 contract boundary

CTX-03 defines versioned, host-validated JSON contracts for execution
metadata, context manifests, evidence inventories, phase inputs/checkpoints,
delegation, finding validation, privacy-preserving usage summaries, and the
host authority context. It does not implement a phase runner or evidence store.

## Trust and authority

A model-owned checkpoint is untrusted serialized data. It may carry bounded
facts, assumptions, inferences, open questions, candidate findings, activated
skill IDs, evidence references, approval requests, and one bounded next-action
request. It cannot carry effective permissions, approval records, approval
completion, execution identity, or another control-plane object.

The host authority context is a separate trusted control-plane input. Its
schema is `host-authority-context-v1`; its value contains immutable execution
identity and version, effective permissions, declared human gates, and
host-owned approval records. An approval record binds an approval ID and gate
ID to the execution ID/version and includes human provenance. Schema validation
alone does not authenticate provenance: the runtime must obtain this value from
its trusted host path. CTX-03 deliberately adds no PKI.

Every authority-participating checkpoint contains `executionId`,
`executionVersion`, and `profileId`. `evaluate_checkpoint(checkpoint, authority)` accepts authority only as a
validated `HostAuthorityContext`, never as fields extracted from the
checkpoint. Effective permissions are copied only from that host value. A
requested approval is complete only when checkpoint, host identity, and host
approval record all match on execution ID, execution version, and profile, and the record
also matches approval ID and gate ID. Unknown, mismatched, or evidence-shaped
IDs remain unresolved and convey no effective permission.

The old `--host-governance` boolean is removed. The generic model-data CLI
cannot validate or write an execution envelope as model authority. The CLI
surfaces are intentionally distinct:

```text
context-runtime.sh validate-model <kind> <input.json>
context-runtime.sh validate-structure execution-envelope <input.json>
context-runtime.sh write-model <kind> <input.json> <root> <relative-output>
context-runtime.sh host-validate-authority <authority.json>
context-runtime.sh host-write-authority <authority.json> <root> <relative-output>
context-runtime.sh evaluate-checkpoint <checkpoint.json> [authority.json]
```

`validate-structure` proves only schema conformance. It does not make a
serialized envelope authoritative. The `host-*` interfaces are separate
integration/test surfaces; the caller remains responsible for supplying them
from the trusted host control plane.

## Model fact and evidence semantics

Every model fact has a typed subject through the shared
`model-fact-v1.schema.json` contract. This includes checkpoint verified facts,
inferences, closed hypotheses and candidate findings; delegation-result facts
and inferences; and finding-validation claims. Allowed model domains are
repository, evidence, requirement, test, runtime observation, external
observation, and application. Governance, permissions, approval, control, and
unknown domains are structurally unavailable. This is enforced by schema
metadata, not by parsing words in a claim.

Claim prose is never consulted for permission or approval decisions. A claim
may discuss permissions, but it cannot change the effective authority returned
by the resolver. Verified facts require one or more syntactically valid `E-*`
evidence references. Such a reference is only a pointer: syntactically valid
does not mean that CTX-05 has proven the evidence exists. It is never an
approval record, permission grant, or other authority.

## Bounded payloads

The effective `phase-checkpoint-v1` canonical JSON budget is 16 KiB, centralized
in `MAX_BYTES`. Claims/questions are at most 512 characters, prose is at most
four lines, checkpoint collections have explicit cardinality limits, and
evidence content has no arbitrary JSON/object field. Complete JSON objects or
arrays, unified/full diff structure, repeated structured log lines, copied
speaker threads, and overlong multiline prose are rejected deterministically.
Canonical evidence transport is by `E-*` reference only.

Other CTX-03 limits remain kind/version specific. In particular,
`usage-summary-v1` retains its historical CTX-01 schema version (`"1"`) and
does not receive a new unversioned host-side byte cap.

## Writer containment

Host authority `issuedAt` and approval `completedAt` use the timezone-aware
RFC3339 subset `YYYY-MM-DDTHH:MM:SS[.fraction](Z|+HH:MM|-HH:MM)`. The host
validator parses the values independently of JSON Schema `format`, rejects
calendar-invalid/timezone-less values, and rejects completion before issuance.

The safe JSON reader anchors absolute inputs at the filesystem root (relative
inputs at the current-directory FD), opens every parent with `O_DIRECTORY` and
`O_NOFOLLOW`, classifies the final FD with `fstat`, and re-attests the parent
binding before accepting the JSON object. A symlink in any parent or at the
final component and a non-regular final object are rejected.

The writer rejects absolute/traversing paths, symlink roots/parents/inputs, and
special-file destinations. On supported macOS/Linux Python runtimes it opens
the authorized root and every relative component as directory file descriptors
using `O_DIRECTORY` and `O_NOFOLLOW`, validates descriptors with `fstat`, creates
the temporary file relative to the opened parent, writes and `fsync`s it, and
publishes relative to that same directory FD. An initially absent destination
uses Linux `renameat2(RENAME_NOREPLACE)` or macOS
`renameatx_np(RENAME_EXCL)`, so a late-created entry is preserved and the write
fails. An initially present regular destination uses
`RENAME_EXCHANGE`/`RENAME_SWAP`; the displaced entry is checked against the
previously observed device/inode/type and a mismatch is atomically exchanged
back before failure. There is no plain `os.rename` fallback.

Immediately after publication the writer re-walks the parent from the anchored
root and compares device/inode with the publication FD. A changed binding is a
failure even though the anchored FD prevented outside-root redirection. For an
absent destination, rollback exclusively renames the newly published inode
back to its temporary name, verifies its identity, and removes it. For an
existing destination, rollback exchanges the old entry back, verifies both old
and new identities, and removes only the new artifact.

Publication failure has three distinct outcomes:

1. Before publication, the operation fails, the destination is unchanged, the
   staging temporary is removed, and no recovery artifact exists.
2. After publication with a successful rollback, the operation still fails;
   an initially absent destination is removed or the observed original is
   restored, the staging temporary is removed, and no recovery artifact
   remains.
3. After publication with a failed or unverifiable rollback, the operation
   fails with `RollbackFailure` and can never return success. Containment still
   holds, but the destination may contain the newly published content and the
   original may remain displaced. This is an explicit partial state requiring
   host-owned/manual recovery, not a transactional rollback claim.

A staging temporary contains the not-yet-published new payload and is removed
on successful publication, pre-publication failure, and successful rollback. A
recovery artifact is semantically different: it is a displaced entry retained
intentionally because deleting it after rollback failure could destroy the only
recoverable copy of the original. When the retained entry is the verified
original, it is kept through the anchored parent FD, restricted to mode `0600`,
and identified by a project-relative location. The filename may retain the
writer's private temporary naming form; its declared recovery role and identity,
not that lexical form, determine its lifecycle. The host must not treat a
declared recovery artifact as disposable staging residue.

For an initially absent destination, rollback failure may leave the new content
at the final entry and there is no original recovery artifact. For an initially
existing destination, exchange-back failure may leave new content at the final
entry while the verified original remains at the reported recovery location.
The writer does not delete that displaced original, does not state that it was
restored, does not retry indefinitely, and does not fall back to plain rename.

`RollbackFailure` is a typed `ContractError`. Its validated attributes and
`as_dict()` form expose only bounded recovery metadata: category, operation,
rollback stage, project-relative destination, known destination state,
project-relative recovery/staging locations when present, whether new content
may remain, whether the original is preserved, whether recovery permissions
were restricted, the underlying errno and cause type, and
`manualRecoveryRequired: true`. The original exception remains chained for the
in-process caller. File data, model prompts, payloads, credentials, arbitrary
environment, and absolute sensitive paths are not included. The CLI emits this
same safe structure on stderr and exits nonzero. It does not create a separate
persistent error artifact.

If the required no-follow, directory-FD, no-replace, or exchange primitive is
unavailable—or the filesystem returns an unsupported-operation error—the
writer fails closed. Containment means no attacker symlink is followed outside
the authorized root. Success validity separately means success is returned
only while the expected parent/destination namespace bindings remain valid at
the contract's post-publication attestation point. The tested boundary assumes
hostile concurrent mutation inside the authorized root; it is not a defense
against replacement of the already-open root mount or a hostile kernel.

Containment is guaranteed across all three failure classes: entries outside the
authorized, FD-anchored target are not modified. Cleanup completeness is
guaranteed for pre-publication failures and demonstrated successful rollbacks,
not when the kernel rollback primitive itself fails. In the latter case the
caller owns recovery using the structured state, must re-attest the namespace
before acting, and must preserve the reported original recovery artifact until
the destination has been reconciled. No incomplete rollback is a successful
write.

## Compiled context manifest (CTX-04)

`context-manifest-v1` is model-owned routing data, not a governance envelope.
It records the complete declared candidate set and a disjoint active/inactive
partition, with baseline, static-signal, semantic-request, and deep-load state
kept explicit. Conditional entries expose only signal and skill identifiers.
Active entries carry provider-neutral model tier, risk, execution mode,
delegation group, and parallel-safety metadata. Missing legacy metadata stays
`unspecified` or `null`; it is never guessed into a stronger guarantee.

`modelEscalationSkills` is derived only from active skills whose declared tier
is `full` or whose risk is `high`. `writePermissionRequirements` similarly
reports active write-capable skills, but does not grant permission. Permission,
approval, execution identity, and human-gate fields are structurally absent
from the manifest and continue to come only from the host authority context.

The compiler may expose an `instructionPath` only in `deepLoadedSkills`, and
only for an already active skill. This permits the host to deep-load selected
instructions without putting `skills/index.yaml`, inactive skill bodies, or
the full candidate catalog metadata into a model prompt.

### Context-manifest validation boundary

`validate-structure context-manifest` proves only JSON Schema conformance and
safe bounded fields. `validate-model context-manifest` additionally checks
internal cross-field consistency, but neither operation authenticates profile
semantics. The authoritative operation is:

```text
context-runtime.py authoritative-validate-context-manifest \
  <candidate.json> <framework-root> <profile-id> <execution-id> \
  [--static-signal ...] [--request-skill ...] [--deep-load-skill ...]
```

Runtime consumers use the corresponding
`authoritative-materialize-context-manifest` operation. It performs the same
comparison but emits the canonical in-memory candidate that passed it. Cast,
execution-plan, and run-profile retain those emitted bytes as one immutable
value; they do not validate a pathname and then reopen it for routing or prompt
construction.

It resolves the profile, full skill index, skill front matter, semantic-agent
catalog, and required outputs below the framework root; recompiles the expected
manifest from the host-declared inputs; then requires canonical equality. It
does not accept a profile path, catalog copy, expected manifest, or governance
boolean from the candidate's caller. Any difference in activation, reason,
metadata, execution mode, delegation, parallel safety, artifacts, agents,
fallback mode, conditional mapping, or deep-load set is rejected.

`skill_activation` is declarative only when its present block is completely
valid. Absence alone selects legacy fallback. Present scalar/wrong-shape,
unknown keys, malformed IDs/signals, duplicate signals, duplicate baseline
entries, baseline/conditional conflicts, partial blocks, and multiple signals
for one conditional skill are invalid profiles and never produce a fallback
manifest.

## Host-owned evidence retrieval (CTX-05)

CTX-05 materializes the existing `evidence-manifest-v1` contract below the
local, Git-ignored `.mana/runtime-evidence/` root. Every load passes the full
schema and semantic validator; malformed items, unknown fields or schema
versions, out-of-bound metadata, inconsistent payload metadata, and an
`evidenceId` that does not match canonical record identity are rejected by
list, show, read, extract, and subsequent collection. A failed operation never
publishes a replacement manifest that bypasses those checks.

Each manifest requires a canonical `workspaceId`. The evidence host derives it
from the authorized Mana workspace's manifest-backed kind and name; no CLI or
model data may submit a workspace ID, and no absolute path is persisted as
identity. The identifier participates in evidence record identity, so unchanged
same-workspace evidence retains CTX-05 deduplication while equal execution IDs
in different workspaces do not become interchangeable.

`sourcePayload` and `normalizedRepresentation` distinguish the collected
sanitized source from the representation used for retrieval; `localPath`
remains the normalized representation for compatibility. Content blob paths
are derived from their sanitized-byte digest and are immutable. Source and
normalized blobs use separate namespaces and may be reused by multiple
records. Their digests and byte sizes are verified on reuse and retrieval;
collision or tamper is a hard failure.

Evidence record identity is not raw blob identity. The host derives `E-*` from
canonical metadata binding at least the execution, workspace, kind, source system,
sanitized locator, revision, raw digest, normalized digest, and normalization
version. Status and other record metadata are also bound. The timestamp is not
part of identity. Thus the same provenance and bytes deduplicate to one record,
while a source/locator/kind/revision or normalized representation/version
change produces another record even when a physical blob can be shared. The
caller never supplies an evidence ID.

The evidence store opens the authorized project root once per CTX-03 operation
and uses component-wise `O_NOFOLLOW`/`O_DIRECTORY` traversal, `fstat`, final-FD
reads, parent re-attestation, and the CTX-03 atomic no-replace/exchange writer.
Blob publication is immutable/no-replace. Manifest publication, rollback, and
temporary cleanup remain relative to the already opened parent FD. No
pathname validation is followed by a pathname reopen, replace, or cleanup, and
source inputs cannot escape the authorized project root.

Sanitization precedes every digest, ID, and persisted byte. It covers
Authorization and Proxy-Authorization, Cookie and Set-Cookie, sensitive URI
query fields, URI user information, credential-named JSON/form fields, and
equivalent textual cookie/token/password/API-key assignments. JSON and forms
must parse before they can be complete. XML/YAML and other declared structured
forms without a safe sanitizer fail closed. Neither raw credentials, hashes of
raw credentials, nor an unsanitized locator belong in manifests or output.

`complete` requires validated source and normalized blobs and is the only
retrievable status. `partial` requires an explicit sanitized partial payload,
bounded cause, and one or more bounded gap descriptions. `failed` and
`unavailable` require bounded privacy-safe cause metadata and prohibit payload
fields. A collection timestamp records when Mana collected the record and must
never be read as source freshness; collectors record `revisionId` where the
source offers one.

The evidence API never returns an unbounded payload to a model-facing caller.
Direct reads are UTF-8-only and bounded to 16 KiB; binary and oversized
evidence require an explicit bounded extractor. Line and byte selectors must be
strict subsets; selecting the whole payload is rejected. JSON selectors use
RFC 6901 with only `~0`/`~1` escapes and canonical array indexes (`0` or a
non-zero digit followed by digits). Negative, empty, inverted, and out-of-range
ranges fail without fallback. The post-selection byte cap applies to every
result, and range results preserve evidence ID, source system, sanitized
locator, digest, revision, and status.

## Phase-run directory skeleton (CTX-06A)

The CTX-06A initializer owns one new run directory:

```text
.mana/runtime/runs/<execution-id>/
  execution-envelope-v1.json
  context-manifest-v1.json
  run-directory-v1.json
  run-state-v1.json                 # sole mutable HEAD, added by CTX-06B
  .transition-head.lock             # inode-stable host CAS mutex
  .provider-phase.lock              # CTX-06C whole-run provider mutex
  phases/
    001-<phase-id>/phase-input-v1.json
  transitions/                      # immutable CTX-06B-R1B bundles
    T-<sha256>/
      transition-v1.json
      checkpoint-v1.json
      run-state-v1.json
      phase-input-v1.json           # only when the committed state is active
      authority-v1.json             # only for resume
```

`run-directory-v1.json` is host-generated bookkeeping, with an ordered unique
phase list, canonical phase policies, a workspace/evidence-manifest binding,
and fixed references used by the initial phase input. The only source of that
list is the profile's host-owned `context_runtime.pipeline`; phase IDs have
explicit consecutive ordinals, and
unknown keys, duplicate phases, incomplete policy, or list/ordinal disagreement
fail. The initializer exposes no `--phase` ordering surface and treats a profile
without this declaration as explicitly not configured for runtime v2.

The run record is not a model checkpoint and cannot carry permissions, approval
records, evidence payloads, or provider output. The envelope is structurally
validated and derives its workspace, target, and human gates from host inputs
constrained by authoritative profile metadata. An existing workspace directory
and matching workspace manifest are required. Target nullability follows
`target_kind`; required target metadata cannot be omitted. A profile with
`human_approval_requirement: true` must declare at least one runtime human gate.
CTX-06A grants neither repository nor external write permission. The context
manifest is freshly compiled from authoritative framework sources.
The envelope and run record both carry the same host-derived `workspaceId` in
addition to the project-relative workspace locator. That ID is re-derived from
the authorized workspace whenever a durable run is loaded.

The initial phase input validates against `phase-input-v1` and starts with
`checkpointRef: null`. `G-001` and `M-001` are local run-directory references
to the envelope and manifest respectively, not authority delegated to model
data. Its objective is host-owned, single-line, non-structured, and bounded to
1024 characters. It cannot contain raw evidence, transcript objects, or
authority fields. Evidence references are empty unless the caller supplies the
canonical same-project, same-execution CTX-05 manifest, which the host binds to
the envelope workspace in the run record. The manifest's required `workspaceId`
must equal the re-derived envelope/run identity. Selected IDs must exist there and
match the initial phase's allowed evidence kinds and statuses. CTX-06A does not
create input directories for later phases, so one evidence list cannot be
copied indiscriminately across phase policies.

Role-labelled transcript turns are recognized case-insensitively for `user`,
`assistant`, `system`, `developer`, and `tool` at the beginning of the objective
or after the supported structural separators `;` and `|`. These role markers
are rejected; ordinary prose that merely contains the same words is not.

The final run path is never populated directly. The host creates a private
mode-`0700` staging directory under the authorized runs parent and retains its
inode-attested staging and parent directory FDs while it materializes and
re-validates all five CTX-06A/R1A records. It publishes the whole tree with one FD-relative
kernel no-replace rename, then crosses an explicit host commit barrier. The
final path is therefore either absent or complete; any existing entry, empty
or otherwise, is a collision. A signal guard records `SIGINT`/`SIGTERM` during
the publication critical section. It does not depend on one `sigpending()`
check followed by unmasking. Failure, `KeyboardInterrupt`, and recorded signals
before the barrier abort the transaction. When publication already occurred,
abort first uses the held parent FD and no-replace rename to move the exact
published inode from the final name to a private quarantine/abort name. The
same held directory FD is then recursively cleaned without following links or
using a pathname-based tree-removal boundary. `_published` remains false until
the barrier has been crossed; after it, the run is committed. A subsequent
`SIGINT` or `SIGTERM` retains the committed final run, returns 130 or 143
respectively, and is reported explicitly as post-commit rather than as an
abort. A completed pre-barrier abort leaves no final, staging, or quarantine
residue.

The initializer makes no provider call and does not accept model output.
Checkpoint validation, resume, provider dispatch, future phase materialization,
lifecycle events, metrics, and legacy selection are outside CTX-06A.

## Authoritative state-machine contract (CTX-06B-R1A)

`run-state-v1.json` is host-owned and schema-valid. It contains execution ID,
execution version, profile ID, revision, active/interrupted/blocked/completed
status, current phase/ordinal/attempt, latest checkpoint reference, and the
per-phase attempt map. Non-initial states also carry their deterministic
transition ID and the digest of the exact previous state. Initial state is
fixed at revision zero with both bindings null, attempt one
for phase one and zero for every future phase. Its field set cannot carry
transcript, evidence payload, permissions, approvals, provider output, or
model-proposed transition counters.

Every profile phase declares canonical `retry_limit: 0..16`; the run-directory
projection exposes it as `policy.retryLimit`. The maximum attempt number is one
plus that retry limit. Attempts and revision are reducer outputs only. A state
claiming a future phase attempt, exceeding a phase retry limit, omitting a
materialized prior attempt, or placing revision below the materialized attempt
history is invalid.

`phase-checkpoint-v1` requires `profileId` in addition to execution ID and
version. The R1A reducer accepts separately validated previous state,
checkpoint, envelope, authoritative pipeline declaration, CTX-04 manifest,
optional CTX-05 manifest, and optional typed `HostAuthorityContext`. It never
accepts a proposed next run state. All records must bind to the envelope's one
execution/version/profile. The reducer recompiles the CTX-04 manifest from the
authoritative framework sources and validates the CTX-05 manifest's execution
and workspace identities before using either. A missing workspace binding or a
same-execution manifest from a different workspace fails closed.

All nested factual `evidenceRefs` resolve against CTX-05 and the current phase
evidence policy. Top-level handoff `evidenceRefs` resolve against the requested
target phase policy. An absent ID, wrong collection status, wrong kind, or
cross-execution manifest fails closed.

Approval prose and approval requests remain untrusted. Requests may name only
profile-declared human gates, and only `evaluate_checkpoint` with a matching
typed host authority can resolve them. Terminal completion must request every
declared gate exactly once and receive matching host approval records. An
unresolved approval or model-reported block derives `blocked` state without an
attempt increment. A blocked state can reconsider only its same accepted
checkpoint, with matching authority; authority cannot enlarge `retryLimit`.

`partial` and `blocked` permit only `repeat-current-phase`. `complete` permits
only the immediately next declared phase, or `stop` from the final declared
phase. Consequently `completed` can be derived only at the pipeline terminal.
Completed and interrupted states reject further R1A transitions.

R1A remains the pure validation/reduction boundary. Durable publication is the
separate R1B protocol below. CTX-06C and later provider execution remain outside
this contract.

## Immutable transition publication (CTX-06B-R1B)

`accept-checkpoint` and `resume` never publish checkpoint, next state, and next
phase input as independent authoritative files. The host first derives the
complete operation in memory. It hashes the canonical previous state, canonical
checkpoint, operation kind, and (for resume) typed host-authority snapshot to
derive `T-<sha256>`. It then materializes one private mode-`0700` staging tree,
re-reads every canonical record through held descriptors, and publishes the
whole transition directory with a single kernel no-replace rename. The final
bundle name is immutable: identical publication converges on the existing
bytes, while any digest/content mismatch fails closed.

The bundle manifest records the previous revision, previous state digest,
previous transition ID, checkpoint and authority digests, resulting state
digest, fixed local references, and the reducer's effective-authority result.
The bundled next state names the same transition ID and previous-state digest.
An active result contains exactly one derived `phase-input-v1.json`; blocked or
completed results contain none. A resume additionally contains the validated
host-authority snapshot used by the reducer.

Bundle visibility is not the authority boundary. `run-state-v1.json` is the
single mutable HEAD and is replaced once, using the exact previously read bytes
as the CAS expectation. Writers hold the inode-stable run-local lock while they
re-read that expectation and perform the atomic replacement, so a losing writer
never transiently publishes its state before discovering the conflict. Only the
bundle whose transition ID is named by the
committed HEAD is current; earlier authoritative bundles remain reachable
through `previousTransitionId`. A published bundle that lost or has not yet
reached the CAS is immutable but non-authoritative. Therefore its checkpoint
and phase input cannot become authoritative merely by existing, and a
checkpoint is authoritative only while reachable from the committed HEAD
chain. Consumers must resolve current phase input through HEAD's transition ID,
never by directory discovery.

An exact retry has the same operation digest and transition ID. If its bundle
is already in the committed chain, the operation returns idempotently. If the
bundle is published and its previous-state digest still equals HEAD, the host
replays only the HEAD CAS. `reconcile` applies the same rule and deterministically
selects at most one eligible published bundle; repeated reconciliation after a
commit is a no-op. A reused checkpoint/operation identity with different
checkpoint or authority bytes is a conflicting duplicate and is rejected.
When competing valid operations start from one HEAD, immutable publication may
leave multiple candidates, but only one exact-byte CAS can advance revision;
all losers remain non-authoritative and stale. Concurrent identical resume
operations converge on one deterministic bundle and one committed revision.

R1B performs no provider call and adds no provider dispatch, lifecycle events,
metrics, or CTX-06C+ behavior.

### CTX-06B-R1D post-exchange cleanup

For the existing-destination run-state CAS, atomic exchange leaves the new HEAD
at `run-state-v1.json` and the displaced expected HEAD at the writer's private
temporary name. Immediately after exchange the writer changes the temporary's
tracked identity to the displaced inode, verifies it is the exact observed CAS
expectation, and unlinks it relative to the held run-directory FD with no-follow
classification. Successful operation includes directory synchronization and
leaves no private temporary.

If the process dies after exchange and before unlink, the new HEAD remains the
authority boundary. Reconciliation first validates and replays its complete
immutable transition chain, then derives the exact previous state of the
transition currently named by HEAD. It may delete one run-state temporary only
when that entry is a regular no-follow FD read whose canonical bytes and digest
equal that derived previous state and whose namespace identity remains stable.
The private filename is discovery input only, never deletion authority.
Multiple candidates, malformed names, changed identities, non-regular entries,
unexpected bytes, stale previous states, or an uncommitted relationship are
ambiguous and fail closed without deletion.

## Permanent transition fault verification (CTX-06B-R1C)

R1C adds no state-machine or publication semantics. Its permanent zero-token
fault matrix interrupts checkpoint acceptance, next-phase input construction,
both sides of bundle publication, the publication primitive itself, both sides
of HEAD CAS, the CAS primitive itself, retry, and crash reconciliation. Every
case re-opens canonical HEAD and replays its complete reachable transition chain
before exercising the permitted retry or reconciliation path.

The same matrix injects concurrent resume and rejects resume without matching
authority, forged state/history, foreign CTX-04 and CTX-05 manifests, nested
unknown evidence references, retry beyond the declared limit, and non-terminal
early stop. Assertions distinguish visible immutable candidates from the single
authority named by HEAD; no candidate checkpoint or phase input is treated as
authoritative through directory visibility.

## Fresh provider phase integration (CTX-06C)

CTX-06C adds two consumers above the unchanged CTX-06A/06B authority boundary:

```text
mana-context-pipeline.sh prepare-phase <execution-id> ...
run-profile-v2.sh <execution-id> --project-root <root> ...
```

`prepare-phase` revalidates all run records, workspace identity, the
authoritative CTX-04 derivation, and the entire committed transition chain. It
selects current input only from the initial immutable record or from the
bundle named by HEAD. Its internal phase-execution packet contains canonical
copies of the envelope, context manifest, current policy/input, and optional
previous checkpoint. It contains no provider output, transcript, raw evidence,
permission override, alternate phase selector, or caller-owned path to reopen.

Provider work is serialized by the mode-`0600` run-local
`.provider-phase.lock`. The lock prevents duplicate invocation by cooperating
hosts; it is not a second state authority. `run-state-v1.json`, its exact-byte
CAS, and the reachable immutable bundle chain retain all transition authority.

Before the first model call, the host validates a fresh CTX-02 capability
report for the run's declared provider. `freshInvocation`, `ephemeralSession`,
`explicitModelSelection`, and `hardSubagentDisable` must be `supported`.
Neither `unknown` nor `unsupported` is treated as support. All phase workers
are child-free in CTX-06C, including a declaration of `subagents: optional`;
CTX-07 owns any later provider-managed child adapter. A missing native
structured-output capability may use an explicitly reported host-validation
fallback because every result still passes the same mandatory schema and
semantic validator. Isolation and model-selection capabilities have no prompt-
only fallback.

The provider prompt includes the exact canonical execution envelope on every
invocation, plus only current phase data and the prior validated checkpoint.
The invocation is read-only. Model tier comes exclusively from the current
authoritative phase policy and maps to the configured provider economy/full
model; model output cannot select it. The CTX-06C provider transport accepts
only `phase-checkpoint-v1`. An invalid JSON object, wrong schema, wrong
execution/profile/phase binding, invalid evidence, permission-shaped state, or
illegal next action is rejected before or by `accept-checkpoint` and cannot
advance HEAD. Provider or semantic failures are not automatically retried.

Provider streams and unvalidated final output exist only in private temporary
files. After validation, the checkpoint becomes durable only inside the
immutable transition bundle and only the winning CAS makes it authoritative.
An interrupted later phase therefore leaves the last committed checkpoint and
derived phase input resumable, without retaining a provider transcript.

CTX-06C lifecycle events are additive operational metadata. They expose phase,
ordinal, attempt, model tier, provider, transition status, and evidence IDs,
never prompts, response content, checkpoint claims, source content, tool
payloads, credentials, reasoning, or usage values. Usage remains on the
separate CTX-01 surface. The existing aggregate files stay at:

```text
.mana/runtime/metrics/<execution-id>/usage-summary-v1.{json,md}
```

Per-invocation numeric records are stored below `phases/` and the aggregate
`phases` array records phase ID, ordinal, semantic attempt, invocation number,
provider version, status, numeric totals, and bounded operational counts.
Absent provider values remain `null`; totals do not estimate them. Raw traces
are deleted by default. Explicit debug retention moves each trace to its
matching phase record with mode `0600`.

The public legacy renderer/runner remains selected unless the caller explicitly
requests `v2` and supplies an existing initialized execution. A missing or
invalid run, unsupported phase output schema, provider capability gap, or
runtime error fails closed and never causes an implicit legacy execution.

## Delegation ownership and merge contracts (CTX-07A)

`delegation-plan-v1`, every contained `delegation-task-v1`, and every
`delegation-result-v1` carry the same required binding tuple:

```text
executionId, executionVersion, workspaceId, profileId, phaseId, attempt,
planId, taskId, taskDigest
```

The plan itself omits only task-specific `taskId` and `taskDigest`. `bind-plan`
copies the phase tuple only from the packet selected through CTX-06B HEAD,
derives `questionKey` from canonical question + typed scope + task type +
expected output, derives `ownershipKey` from question key + owner, derives
`planId` from canonical validated plan identity bytes, and finally derives each
`taskDigest` from the canonical fully bound task. Validation recomputes all
values. Absolute paths and sensitive material are not valid identity fields.

Canonical question identity is exact and deterministic. The same derived
`questionKey` cannot occur in two tasks, even with different owners, and a task
ID cannot occur twice. No semantic equivalence between paraphrases is implied.

Task authority is structural. `effectClass` is exactly `read`,
`delegationAllowed` is false, `maxChildDepth` is zero, and `taskType` belongs to
the versioned read-only action enum. A packet explicitly carries typed scope,
skills, expected output, bounded stop conditions, `evidenceRefs`, and
`evidenceGaps`. Unknown fields are rejected, including instructions, commands,
tools, permissions, authority, approvals, transcript/history, ambient context,
or nested delegation. Question prose cannot alter these fields. CTX-07B owns
runtime sandbox and child-tool enforcement; CTX-07A only proves that accepted
contracts request no broader capability.

`evidenceRefs` are canonical CTX-05 IDs. They must exist in the authoritative
manifest, match its execution/workspace, be explicitly available in the
current phase input, and satisfy current phase kind/status policy.
`evidenceGaps` are bounded `{description, kind, impact}` records. They are not
manifest IDs, are not resolved through CTX-05, grant no authority, and cannot
be cited as evidence for a fact.

`bind-result` copies the binding tuple and owner from the validated task. Its
`resultDigest` is SHA-256 over canonical result identity after omitting only
the digest field and repeated `sourceResultDigest` values; the host then writes
that digest into every point-provenance record. Facts, findings, assumptions,
inferences, open questions, evidence gaps, artifact references, and uncertainty
all retain `taskId`, `planId`, `sourceResultDigest`, and pertinent evidence
references. Facts, findings, and inferences require real task-authorized CTX-05
evidence. The schema has no skill activation, scope expansion, permission,
approval completion, owner replacement, transcript, reasoning, or bulk-evidence
surface.

`delegation-merge-v1` is lossless output, not state authority. It preserves the
full canonical result per task plus canonical aggregate collections, exact
point provenance, evidence/artifact references, uncertainty, missing task IDs,
conflicts, and `complete|incomplete|conflicted` status. Result argument order
cannot alter bytes. Unknown or duplicate task results fail; missing or
non-complete results cannot produce `complete`. There is no last-write-wins.

Claims use a host-validated `claimKey` derived from typed subject + predicate
and an `affirmed|denied|uncertain` stance. Affirmed and denied claims sharing a
key create an explicit conflict while both source elements remain present.
Matching stances remain separate; different keys are neither agreement nor
contradiction. CTX-07A performs no model synthesis.

Central transport limits are 64 KiB plan, 32 KiB task, 64 KiB result, and
256 KiB merge; task count is at most 32 and still capped by CTX-04
`directWorkers`. Each result category is capped at 32 entries, task evidence
gaps at 16, normal prose at 512 characters, and gap descriptions at 256.
Schema cardinalities and host canonical-byte checks both fail closed.

No CTX-07A command writes a run artifact, advances HEAD, invokes a provider,
starts a subprocess provider, contacts a model/network, or enables a child.
Those behaviors remain outside CTX-07A.

## Host-owned isolated worker contract (CTX-07B-R2A-E)

`run-context-workers.sh` is the only CTX-07B provider boundary. Its input is a
bound `delegation-plan-v1`; the host reloads the current phase through CTX-06B
HEAD and reuses the complete CTX-07A plan validator before inspecting any task.
The production runner derives its framework root from its canonical installed
location. It accepts no framework-root or model/effort override from CLI,
environment, task data, or provider output. The checked-in routing policy,
skill metadata/bodies, capability metadata, and Mana contracts are therefore
host authority. Test fixtures use a separate, explicitly test-only entry
point. `run-state-v1.json` and its reachable transition chain remain the sole
phase HEAD authority.

One plan task means one new provider process. Before the first process, the
host requires CTX-02 `freshInvocation`, `ephemeralSession`,
`explicitModelSelection`, and `hardSubagentDisable` to be `supported`. When the
host policy requires a reasoning effort, `explicitReasoningEffort` must also
be `supported`. Unknown
or unsupported is a deterministic `needs_model_escalation` failure before invocation.
The worker adapter is read-only, disables provider-managed children and depth,
isolates user configuration where the provider proves it, and never selects an
enabled child path. CTX-07B has no CTX-07C adapter or fallback. An unproven
native output schema alone may use mandatory host validation; isolation and
model selection cannot.

The provider-visible input consists of invariant worker transport rules and
exactly one canonical `worker-context-packet-v1`. Its only payload fields are
the pertinent read-only governance envelope; one validated
`delegation-task-v1`; a task-only CTX-04 projection carrying the digest of the
canonical source manifest; metadata and full body for each task-active skill;
authorized evidence references; the output contract; and host-owned
model/effort selection. It contains no sibling, parent transcript/prompt,
phase input/checkpoint, inactive or candidate skill body, raw evidence,
complete run state, additional authority, or ambient caller context.

Routing uses only typed, host-validated inputs. The full tier is mandatory for
the architecture, contracts, database, operations, and security scope domains,
and for a task containing an active CTX-04 skill whose declared model tier is
full or risk is high. Every other valid read task uses the economy tier. The
versioned policy below `config/context-runtime/` is the sole mapping from
provider/tier to concrete model ID, effort, and allowed scope/risk. Question
prose, ownership labels, result data, provider defaults, CLI flags, environment
variables, and provider-managed child routing are never model-selection
inputs. CTX-07A validates the complete plan before routing; every route is
resolved before the first packet is constructed.

Capability support, Mana admission, and runtime model availability are
distinct. CTX-02 proves the explicit selection mechanism, the host policy
admits a concrete route, and the provider may still reject the model ID at
transport time. Such rejection is a transport failure, never proof that the
capability probe had verified model existence. A missing or duplicate mapping,
or a disallowed full/high-risk route, fails closed before invocation.

Parallel execution is bounded by `contextManifest.limits.directWorkers`; a
caller may lower but cannot raise that host limit. CTX-07A has already proven
that every selected task has unique ownership/question identity, read effect,
parallel-safe skills, no delegation, and depth zero. Thus CTX-07B permits only
independent parallel readers and has no writer surface.

Provider output uses
`contracts/context-runtime/delegation-result-draft-v1.schema.json`. All result
collections are present, but a collection not declared in the task's
`expectedOutput.sections` must be empty; undeclared uncertainty must be the
canonical `none` value. After transport validation, CTX-07A alone adds binding,
owner, plan/task/result digests, point provenance, and the exact evidence union.
The unchanged CTX-07A validator rejects foreign, stale, unauthorized, or
oversized output before merge.

Before invocation the host creates a private capsule containing only the
validated worker packet, governance/manifest projections, active skill bodies,
output contract, and bounded authorized CTX-05 extracts. The capsule contains
no original path locator, run HEAD/state, full evidence store/manifest, sibling
task/evidence, parent transcript, or unmaterialized source. A verified
host-owned read-isolation backend must restrict the provider to the capsule;
unknown, unavailable, or unsupported containment fails closed with zero
provider invocation. No provider-specific content-only fallback exists.

Providers run as leaders of dedicated process sessions. Provider stdout and
stderr are captured separately. Stderr is written only to a per-invocation
temporary regular file with mode `0600` below a private mode-`0700` directory;
it is never inherited, excerpted, or copied to runner stdout/stderr, lifecycle,
usage, aggregates, claims, results, receipts, or public error text. The
temporary is removed on every handled terminal path. A public transport error
is host-generated and bounded to the failure category, provider, invocation ID,
and exit status or signal; it contains no provider-controlled text.

A host-owned timeout
causes TERM of the process group, a bounded host-owned grace, KILL of the
group, and wait/reap. Signals preserve terminal status 130/143; timeout uses
124. Capsule and temporary output are cleaned on every terminal path.

Worker raw trace retention comes only from the versioned
`worker-debug-policy-v1` object below the canonical framework root. The default
is `discard`. Production accepts no retention CLI option, rejects
`MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE` and worker equivalents, and has no task or
model field for retention. The host materializes policy identity, digest, and
decision in its private prepared plan before invocation; a later source-policy
change cannot alter that plan. With explicit `retain`, the raw provider
stdout/event stream is copied to the matching invocation attempt as
`raw-provider-trace`, with mode `0600` under a mode-`0700` directory. Distinct
invocation IDs make concurrent paths collision-free. Complete, failed,
timed-out, and interrupted attempts may retain a trace, and
`rawTraceRetained` is true only when the matching file exists. Reuse creates no
new invocation or trace. Aggregates and lifecycle events contain no raw bytes
or trace path.

The raw trace is a potentially sensitive local debug artifact, not a delivery
artifact or a privacy-safe metric. Provider stderr is a separate temporary
diagnostic stream and the debug policy never retains it.

The deterministic `taskExecutionKey` identifies equal work; a fresh
host-generated `invocationId` identifies each real attempt. Claims are
FD-anchored CTX-03 CAS records. An expired claim is reconciled by CAS, while a
known failure is made terminal immediately. No phase-global worker lock is
used.

After transport/schema checks and CTX-07A bind-result validation, canonical
result bytes are fsynced into an immutable per-invocation attempt artifact.
Only a successful per-task result-HEAD CAS makes that artifact authoritative.
Reuse requires the HEAD-reachable artifact to pass a fresh safe read and full
binding, digest, CTX-04/05, and semantic validation. Conflicting, stale,
foreign, malformed, partial, and orphaned artifacts are never reused. Worker
publication does not advance the CTX-06 phase HEAD.

The worker transaction first persists `attempts/<invocationId>/receipt.json`:
a host-only immutable `worker-receipt/v1` record with terminal claim, validated
result and bounded numeric usage. It is recovery intent, not result authority.
Publication order is receipt, immutable `result.json`, task-result HEAD,
immutable metrics/events, derived aggregate, terminal claim CAS. A short
directory-FD `flock` serializes these state operations per task; it never serializes
provider invocations for different tasks. Recovery validates the receipt using
current CTX-07A authority before replaying any missing step. Exact replay is
idempotent, including event identities and usage. Expired claims without a
receipt close as interrupted with unavailable usage before a new attempt.

An explicit publication failure before HEAD may write immutable `failure.json`
alongside the receipt; it cancels that intent and preserves failure lifecycle
and usage. It cannot cancel a committed HEAD. Fully written staging files are
reconciled against canonical claims/receipts, accepted result semantics and
immutable metric records. Cleanup verifies bytes, inode, link count and parent
binding through held descriptors. Malformed, partial or foreign recovery
candidates fail closed without deletion; names alone never authorize cleanup.

Lifecycle events and per-invocation usage summaries are immutable,
privacy-safe operational metadata rather than authority. Completion occurs
only after task-result HEAD commit. Failure, timeout, interruption, result
acceptance/reuse, and stale-claim reconciliation are distinct. Missing token
dimensions remain null. Reuse creates neither a provider call nor a duplicate
usage record. Aggregates name included invocation IDs and are reconstructed
from immutable per-invocation records.

Accepted results and merge inputs stay in one private temporary directory.
The command emits the unchanged canonical `delegation-merge-v1` on stdout and
does not persist the merge, publish a checkpoint, or advance phase HEAD. Failed provider or
result validation has no retry and no accepted task result; successful sibling
results remain losslessly represented and missing tasks are explicit in the
incomplete merge. No provider transcript is retained by default; raw retention
is controlled only by the host debug policy.

The R2E recovery matrix invokes the provider before each `after-provider`,
`before-bind`, and `after-bind` crash. It proves transport, normalization, and
binding reach their declared boundaries; keeps task-result HEAD absent at the
crash point; reconciles the claim; preserves the crashed invocation metric and
lifecycle without a false completion; and permits exactly one new
authoritative retry. Provider-managed children remain CTX-07C scope.

## Optional provider-managed child contract (CTX-07C)

The production worker runner accepts one host policy:
`--provider-children disabled|prefer|require`. The default `disabled` behavior
is the unchanged CTX-07B selection path. `prefer` may select a provider child
only after the validated CTX-02 report proves all of:

```text
freshInvocation, ephemeralSession, explicitModelSelection,
providerManagedSubagents, childContextInheritanceControl,
childModelRouting, recursiveDelegationPrevention,
maximumChildConcurrency, maximumChildDepth,
structuredOutputSchema, userConfigurationIsolation,
managedChildExecutionAttestation
```

When a host route carries a reasoning effort, both
`explicitReasoningEffort` and `childReasoningEffortRouting` are additionally
mandatory. Every state must be exactly `supported`. The adapter itself must be
implemented for the selected provider. Unknown, unsupported, contradictory,
or absent evidence is never approximated through prompt text.
`managedChildExecutionAttestation` requires an ordered, observable,
provider-native event stream. Canonical integer sequence, not wall-clock time,
drives a finite state machine: one bound root, one child start, one task
binding, then exactly one completed or failed terminal event. Start after
terminal, terminal before start or binding, duplicate start/terminal/sequence,
an event after terminal, equal root/child IDs, foreign or stale execution
binding, and incomplete streams are rejected. Configuration, managed-child
argv, prompt text, agent definitions and root markers are not attestation.

On a `prefer` gap the host selects the complete fresh CTX-07B worker before
claiming or invoking the task and applies its independent worker capability
gate; CTX-07B may execute or fail closed. On a `require` gap it fails closed with
`needs_model_escalation` before provider reach. Environment variables, task or
result fields, question prose, provider defaults, and model output cannot
select either policy. A child attempt that has reached the provider is never
retried through CTX-07B after transport, timeout, interruption, or validation
failure.

Codex, Claude, and OpenCode have no verified provider-native ordered receipt.
Each reports `managedChildExecutionAttestation: unknown` and none has a
selectable production managed-child adapter. The canonical test-only adapter
and provider fixture prove only the generic R2 protocol and cannot be selected
through the production entry point.

After ordered verification, the host publishes a canonical immutable
`managed-child-receipt/v1` artifact with mode `0600` below the current
mode-`0700` attempt directory. It contains a host-derived `receiptId` and
`receiptDigest`, provider/root/child identity, the complete
execution/version/workspace/profile/phase/attempt/plan/task binding, host
invocation and task execution key, terminal status, and ordered event count
and digest. It contains no event payload, raw prompt, reasoning, source,
credential, transcript, or arbitrary provider payload. Publication and every
later read recompute its identities and verify current host authority,
canonical bytes, location, and permissions.

Provider output remains an untrusted `delegation-result-draft-v1` object and
cannot carry `executionTransport`, invocation IDs, `attestationKind`,
`receiptId`, `receiptDigest`, or `executionReceiptDigest`. The public CTX-07A
`bind-result` interface is host-worker only. The worker runtime binds a child
result through a host-owned lookup of the persisted receipt; it never accepts
a caller-selected receipt identifier, digest, path, dict, or authority object.
Result provenance carries the identity derived from the freshly read receipt.

CTX-07C-R3 uses distinct audit and success APIs. The generic
`validate_managed_child_receipt_record` and
`read_committed_managed_child_receipt_record` retain completed and failed
terminal records for audit/lifecycle. The shared
`load_committed_completed_managed_child_receipt` is the only managed-child
success authority boundary. Bind, publication, result reconciliation/recovery,
task-result HEAD validation, reuse, and merge all require it. A valid committed
failed receipt cannot authorize a complete semantic result, including a result
whose caller recomputes coherent semantic/execution digests and provenance.

Python managed-child binding/validation accepts only project-root and host
invocation lookup identity alongside the validated packet/task; the task
execution key and receipt path are host-derived. Merge resolves the invocation
from each committed task-result HEAD and re-reads its committed artifact,
receipt, and global binding. The resolver verifies canonical bytes, mode
`0600`, regular/single-link type, mode-`0700` parent, receipt identity and native
digest, provider/root/child identities, the complete binding tuple, the digest
of the canonical ordered events reconstructed from the receipt, `completed`,
and current run HEAD/task claim/result HEAD invocation binding. Audit reads
remain possible after a failed attempt or phase change.

After receipt publication, a separate no-replace
`managed-child-receipt-commit.json` records its complete canonical artifact
digest, receipt/task/invocation identities, and the device/inode returned by
the same CTX-03 safe-reader FD. A visible receipt without this host commitment
is not committed authority. Every lookup checks that record; deletion,
replacement even with identical bytes, tamper with recalculated fields/digests,
noncanonical content, wrong mode/type, or symlink fails closed. Private reads
verify mode, link count, stable metadata, final-entry identity, and parent
binding through held FDs, without a pathname `lstat` followed by reopening.
The normal CTX-03 reader and publication no-replace/CAS semantics are preserved.

`managed_child_execution_authority(dict)` is removed. `ExecutionAuthority` is
retained solely for CTX-07B host-worker provenance. A manually constructed or
previously materialized child object cannot confer proof to Python bind,
validation, publication, reuse, or merge; these boundaries perform fresh
receipt lookups instead of trusting the object's constructor or copied fields.

`semanticResultDigest` (also the retained CTX-07A `resultDigest` alias)
depends only on result semantics. `executionReceiptDigest` additionally
commits the provider receipt digest and complete host-owned provenance.
Equal semantic content through CTX-07B and CTX-07C therefore has one semantic
digest but distinct provenance and execution-receipt digests.

Before task-result HEAD, the host atomically publishes a global no-replace
binding equivalent to:

```text
receiptDigest -> taskExecutionKey -> semanticResultDigest
              -> authoritativeResultHead
```

An exact publication replay is idempotent. Reuse of the receipt for different
semantic content, task, attempt, execution, host invocation, artifact, or HEAD
conflicts. The binding is recovery intent for its exact embedded HEAD and
prevents any second HEAD from being associated with that receipt. Publication,
reuse, and authoritative merge re-read and validate the receipt, global
binding, result artifact, and task HEAD. The generic CTX-07A merge rejects a
provider-child result without this runtime authority.

CTX-07B claim, worker receipt, result-HEAD, metrics, lifecycle, recovery,
stderr containment, trace policy, process-group supervision, isolation
backend, and merge rules remain in force. CTX-07C adds no provider retry,
writer, phase transition, semantic synthesis, or correctness dependency on
provider-managed children.

## Host-owned compaction and budget contract (CTX-08)

`config/context-runtime/provider-budget-policy-v1.json` is the sole CTX-08
policy input. Its exact versioned field set carries an explicit calibration
state, a versioned compact prompt, and profile-selectable `compact`,
`standard`, and `deep` modes. All current values carry the calibration state
`provisional-no-empirical-baseline`. A policy that claims calibrated values, a
mode outside that set, a non-positive limit, an enabled child setting, or an
active-context warning above its compaction threshold is rejected before
provider reach.

The host resolves the policy from the authoritative framework root and pairs
each requested provider control with its exact CTX-02 tri-state record:
`automaticCompactionThreshold`, `customCompactionPrompt`, `compactionScope`,
`toolOutputRetentionTokenLimit`, `maximumChildConcurrency`, and
`hardSubagentDisable`. Only `supported` may produce provider argv or provider
configuration. `unknown` and `unsupported` produce explicit no-apply records;
they are never replaced by provider defaults, prompt prose, a version guess,
or another provider's feature. A supported control without a checked-in exact
host adapter is also an explicit `host-adapter-unimplemented` no-apply record.
The current phase adapter accepts only the
proven Claude automatic threshold. CTX-06C's pre-existing hard child disable
continues to be required independently of budget policy.

The compact prompt must preserve human goal, immutable governance and
approvals, execution identity, activated skills and reasons, verified facts
with CTX-05 references, open evidence, decisions, closed hypotheses, blockers,
provenance, and next bounded actions. It must distinguish assumptions and
inferences from verified facts. It may discard or summarize raw transcripts,
complete payloads, repeated evidence, resolved exploration, superseded plans,
inactive skills, and already-applied explanatory material. This prompt is
provider configuration only when capability-gated; it is not authority.

The host may emit an advisory when its byte/4 prompt estimate or CTX-01
measured aggregate reaches a configured provisional threshold. It evaluates
cumulative input, cached input, and uncached input separately and retains the
canonical CTX-01 aggregate unchanged. An advisory may recommend evidence
offloading, a narrower task, checkpoint plus a fresh phase, or a human scope
decision. It cannot skip a required skill/specialist/evidence check, resolve a
human gate, alter permissions, change CTX-06 HEAD, or make compaction a
correctness boundary. CTX-05 remains canonical for full evidence regardless of
any provider tool-output retention control.

### CTX-08-R1 authority and immutable mode decision

Production phase and worker runners derive the framework root from their
canonical installation, never from CLI, environment, task, checkpoint or
provider data. `run-profile-v2.sh` no longer accepts `--framework-root`.
The canonical `tests/run-profile-v2-test-only.sh` and
`tests/context-budget-test-only.py` entry points use a fixed fixture root;
production cannot select these through an option or environment value.

Policy and its inline versioned compact prompt are read together through the
CTX-03 trusted-root directory-FD reader: component-wise `O_DIRECTORY` and
`O_NOFOLLOW`, final `fstat`, a 256 KiB bound, stable metadata/single-link
classification, and parent/final identity re-attestation. There is no external
prompt reference in v1; reference fields, missing/outside-root prompt paths,
and provider/capability mapping overrides are rejected. The entire policy
passes its JSON Schema and host semantic validation, including every profile
and every selected or unselected mode. Duplicate fields are rejected.

`NUMERIC_CEILINGS` in `scripts/lib/context-budget.py` centralizes implementation
safety ceilings, mirrored by schema maxima and checked for agreement by the
permanent regression suite. Compaction and active-context ceilings are
10,000,000 tokens each; cumulative, cached and uncached input ceilings are
1,000,000,000 tokens each; tool-output retention is at most 1,048,576 tokens;
child concurrency is at most 32. All limits are positive integers. These are
finite implementation bounds, not calibrated thresholds or provider model
availability claims. Provider rejection remains an explicit transport failure.

The authoritative order is `compact < standard < deep`. Every numeric policy
dimension must be nondecreasing across that order; all child execution values
remain `disabled`. Each profile policy declares `minimumMode`. The default
minimum is `standard`; an authoritative CTX-04 model-escalation skill raises
the minimum to `deep`. This changes budgets only, never task routing, skill or
evidence coverage, permissions, approval, or child transport selection.

Before the first invocation the host publishes one immutable
`provider-budget-decision-v1.json` under the existing CTX-06 run directory.
It contains execution/version/profile/provider identity, policy ID and digest,
minimum/requested/effective modes, technical decision source/reason, and the
canonical validated policy snapshot. `--budget-mode` is only a request from
the observed `human-cli` surface; it is not proof of a human identity. Without
a request the source is `host-policy` or `profile-risk`; a weaker request
preserves the minimum and a stronger initial request raises the budget.
Schema, reconstructed decision, canonical bytes, private modes and a separate
host commitment to the file digest/device/inode are verified on reuse.

Phase resume/retry and workers reuse the same snapshot without reopening the
source policy. A source change cannot affect the current execution. Later
weaker requests preserve the saved decision; a stronger request after
materialization fails explicitly and requires a new execution. Concurrent
materialization is serialized by an FD-attested run-local budget mutex.
This mutex does not replace CTX-06 HEAD or its approval/CAS authority.

### CTX-08-R1 coherent usage and advisories

CTX-01's numeric-only parser and the host budget checker share the supported
integer domain `0..9007199254740991`. Cached and uncached input cannot exceed
total; when all three are reported, cached plus uncached must equal total.
Negative, noninteger, conflicting alias and overflow values are parse errors;
invalid traces have null totals, `usageStatus: unavailable` and nonzero
`parseErrors`. They never become a measured or below-budget decision.
Complete coherent dimensions use `measured`; coherent missing dimensions use
the additive `partial` status. No missing uncached value is inferred.

Phase and worker invocations store separate privacy-safe budget advisory
records, including policy digest, effective mode, reported numeric dimensions,
usage validity/availability, warning and optional byte/4 prompt estimate.
These are budget/metric artifacts, not runtime events or checkpoints. The
run's budget aggregate is reconstructed from unique immutable invocation
records across phases and workers. An unreported dimension retains null when
coverage is incomplete; immutable CTX-01/06/07 records retain every actual
reported value. Invalid usage produces an explicit invalid advisory and may
recommend a human scope decision. Reuse adds no invocation or usage record.

Each new advisory evaluates both `invocationUsageCheck` (only this invocation's
reported usage) and `aggregateUsageCheck` (unique invocation coverage so far).
The runner-facing `usageCheck` retains the invocation's availability/measured
status unless either scope is invalid, and forwards the union of both warning
sets. Invalidity takes priority and recommends a human scope decision; otherwise
a threshold exceeded in either scope recommends a checkpoint and fresh phase.
Missing aggregate coverage never suppresses a measured or partial invocation's
threshold warning, and never turns null aggregate dimensions into estimates.
Existing immutable advisories are reused unchanged rather than rewritten.

Exceeded budgets remain warnings recommending fresh phases or human scope,
without skipping required skills, full/high specialists, evidence or approval,
changing model tier, truncating completion, or claiming a clean semantic
verdict. Compaction remains only a capability-gated optimization. Initial
thresholds remain `provisional-no-empirical-baseline`; future CTX-09/shadow and
pilots will provide calibration evidence, but are not implemented by R1.

## CTX-09A host mode-plan and local hand-off

`scripts/run-profile.sh` exposes only `legacy` (default), `shadow`, `v2`, and
`compare`, selected exclusively by an explicit host `--context-runtime` flag.
Unknown modes and any ambient `MANA_CONTEXT_RUNTIME_VERSION` fail closed.
Runtime mode is not a permission grant, model/provider preference, task field,
checkpoint field, approval, or result-authority update. V2 execution uses only
the CTX-06/07/08 entry point and never falls back to legacy.

The host-local artifact is
`.mana/runtime/comparisons/<execution-id>/mode-plan-v1.json`. Execution IDs
match `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`. Its closed construction persists only
these fields: `schemaVersion` (`mana.context-runtime.mode-plan/v1`),
`executionId`, `mode` (`shadow` or `compare`), `authority` (`legacy` or `none`),
`externalActions` (`disabled`), `permissionGrant` (`none`), and `comparison`
(`deferred-ctx-09b`). Shadow additionally records `publication: disabled`,
`v2Execution: deferred-ctx-09c` and `legacyExecution` with `status`
(`completed` iff exit status is zero, otherwise `failed`) and `exitStatus`
(0–255). After CTX-09B-R1, compare records `artifacts.legacy` and `artifacts.v2`,
each containing a safe project-relative `path`, actual-byte lowercase SHA-256
`sha256`, `fileInstance`, verified `producerRuntime`, `producerReceiptDigest`,
`executionVersion`, `profileId` and `targetKey`. No semantic verdict, equivalence, missed-finding assertion,
prompt, response, reasoning, credential, environment, raw trace, source body,
full diff or raw evidence is included. Serialization is sorted-key compact
UTF-8 JSON plus one newline, without generated diagnostic timestamps or random
persisted IDs; filesystem mtime/ctime are committed local metadata.

Root traversal starts at an absolute anchor and retains no-follow directory
FDs for every ancestor. The project root and relative directory components
must be host-owned; root/parent bindings are re-attested. Absolute/traversing,
symlink (including root ancestors), special-file and multi-link source paths
are rejected. Source reads use the same FD as their hash, are bounded to
16 MiB per artifact, and compare identity, link count, mode, size, nanosecond
mtime/ctime and parent bindings before/after reading. The source is never
written. Shared `.mana/runtime` legacy permissions are preserved; the
comparison namespace and every new artifact directory require `0700`, and
artifact files require `0600`. Insecure existing private directories fail
without chmod or overwrite.

An exclusive namespace FD lock serializes cooperating host registrations;
collision checks precede shadow execution and atomic publication uses the
existing host no-replace rename primitive. A private staged directory holds
the fully written/fsynced file, whose identity, permissions and exact bytes
are checked before publication and commit. The final directory is never
visible partially written. Parent rebinding or handled I/O/signal failure
rolls publication back and cleans identity-matching owned staging using held
FDs, even when a parent moves. Empty directories created by a failed operation
are removed; preexisting state and collisions are preserved. There is no
unsafe publication fallback on hosts missing required primitives.

Shadow requires explicitly read-only activated skills and agents and rejects
mutating tool capabilities; remote update checks are disabled before isolation.
A fixed `/usr/bin/sandbox-exec` host backend on
macOS blocks application/external writes and network before effects, including
HEAD, run-state, approval, and result authority. Only private host scratch and
legacy metrics writes are permitted. Caller backend/launcher overrides are
not isolation authority; unsupported or failed probes abort before legacy.
Legacy stdout and provider exit status remain authoritative. Failure to
register after execution is metadata-only stderr with `handOff: failed`, a
bounded exception category and the preserved legacy status. Helper operations
`shadow-preflight`/`shadow-run` are internal host operations, not additional
runtime modes; direct `shadow` registration requires an explicit host-observed
`--legacy-exit-status` and executes nothing.

This contract relies on host ownership of the private namespace and existing
host atomic rename semantics, not protection against an unrestricted hostile
process running as the host UID. SIGKILL/power loss and hostile replacement
of rollback identities require host recovery; they are not silently reported
as successful registration. CTX-09A itself introduces no CTX-09B comparator.

## CTX-09C-R1A canonical shared input and isolated shadow namespaces

`scripts/lib/context-shadow-input.py` defines the closed canonical
`mana.context-runtime.shared-shadow-input/v1` packet. It contains comparative
and operational identity, profile, target/work item, exact materialized input,
authorized evidence snapshot, compiled context manifest, policy snapshot and
materialized mode decision, and verified SHA-256 digests of actual bytes.
The host constructs it once and validates before execution. Base64 records
preserve exact byte length and digest; duplicate fields, noncanonical encodings,
unknown fields, policy/mode mismatches and changed capsules fail closed.

A local ephemeral 0700/0600 capsule retains a read-only FD and attests inode,
mode, ownership, link count, size, mtime/ctime and actual bytes before each
consumption. Access-time updates are harmless. Both fixed consumers receive
canonical stdin, rather than an ambient path or the original profile argv.
Legacy invokes the captured provider argv as positional array elements with
the exact captured prompt. It never recompiles. Shadow derives declared fresh
phase packets and calls the unchanged CTX-06 checkpoint reducer with no legacy
run/HEAD/checkpoint lookup. There is no semantic retry or recovery protocol.

`comparisonExecutionId` is common; legacy/shadow producer, invocation, lock,
run and metric identities are distinct. Shadow run views and metric roots are
below `.mana/runtime/shadows/COMPARISON/`, with private producer locks.
Existing shared legacy directory modes are not changed. A fixed native macOS
backend proves both an allowed contained write and a denied outside write.
The fixed policy denies network and all writes except shadow scratch/run/metrics.
It strips ambient launcher, approval completion and discovery overrides.
Absent/unknown/nested-denied backends and provider/pipeline capability gaps
produce unavailable with no shadow invocation and no weaker fallback. Legacy
executes independently under its existing provider contract; shadow failures
and metadata publication failures cannot replace its stdout or exit status.

After execution the packet and all raw materialized input/evidence/provider
payloads are deleted or released. Persistent consumption/result/producer records
contain only identity, digest and bounded metadata; raw trace retention is disabled.
Successful sides use the existing CTX-09B publisher and receipt commitments for
closed host metadata projections. Both receipts are verified before registration
and the unchanged offline comparator. These projections do not declare structured
semantics, so a comparison is indeterminate, never equivalent. Missing sides
produce a separate missing-artifact observation. Numeric usage summaries and
null/missing dimensions retain provisional CTX-08 calibration. Tests use only local
provider stubs and a separate fixed fixture consumer, with no production selector.

## CTX-09C-R1B legacy authority barrier and transactional live shadow

R1B makes legacy commit the sole caller-visible authority. The host first runs,
captures, validates and materializes legacy stdout/status, writes an immutable
legacy receipt, and advances a single private `live-shadow-head-v1.json` only
then. R2B supersedes the original stdout-only/R1C projection-based recovery:
the private exact outcome retains both caller streams and status separately
from the CTX-09B projection (see the R2B contract below).

The state is a versioned CTX-06B-style chain: immutable bundles are published
before one exact-byte HEAD CAS. `initialized`, `legacy_committed`,
`shadow_completed`, `shadow_failed`, `shadow_unavailable`,
`comparison_completed`, `comparison_indeterminate`, `completed` and
`manual_recovery_required` are the host-owned stages. A bundle visible without
being named by HEAD is non-authoritative. Existing bytes converge only when
identical; conflicting receipt/result/artifact bytes fail closed.

Legacy failure is authoritative and, by R1B policy, suppresses shadow entirely.
After `legacy_committed`, backend/usage/receipt/comparison failures, malformed
shadow output, timeouts, INT/TERM and harness exceptions can only update the
non-authoritative shadow journal; they never replace caller stdout or status.
Shadow runs in a fresh process session under a host deadline. On normal exit,
timeout or host INT/TERM the host drains the group, sends TERM, waits bounded
grace, sends KILL, and reaps before any result is terminal. Timeout is 124 and
host-observed INT/TERM are 130/143.

Recovery never replays ambiguous side effects. Before a legacy receipt, an
immutable intent without a complete receipt requires manual recovery. After a
legacy receipt, recovery advances only the missing HEAD CAS and continues at
the first missing shadow stage. A complete shadow receipt similarly permits
compare without a second shadow invocation, and a committed comparison report
is reused. A completed run is reusable. Permanent fault points cover input,
legacy exit/receipt, shadow start/exit/artifact/receipt, comparison, HEAD CAS
and final cleanup; each accepts either idempotent receipt-based recovery or an
explicit `manual_recovery_required` state.

## CTX-09C-R1C structured artifacts, privacy and isolated usage

R1C validates each legacy or shadow stdout before it can receive CTX-09B
producer receipt authority, artifact authority or comparison eligibility.  The
only accepted candidate is the bounded closed
`mana.context-runtime.semantic-comparison-input/v1` projection: strict JSON
parsing rejects duplicates/non-finite input; the installed schema validates
its shape; CTX-09B's semantic checks validate identity, uniqueness and
coverage; and a host-owned privacy screen rejects prompt, source, credential,
cookie/token, response, reasoning, provider-stderr, full-diff and raw-evidence
canaries.  A privacy-invalid candidate receives no durable digest.

Malformed, schema-invalid, semantic-invalid, privacy-invalid and failed
publication candidates persist only a host-generated status, bounded byte
count where safe and fixed error category. Neither CTX-09B producer receipts
nor comparison registration are published for invalid candidates. A valid
candidate is canonicalized as the structured comparison artifact. R2B retains
the legacy caller streams separately as a sensitive local recovery/delivery
artifact, including when comparison validation rejects the candidate. That
outcome is never a usage/comparison payload or a privacy-safe projection.
Shadow streams remain ephemeral.

CTX-09B is invoked only when both roles have a valid structured artifact,
committed producer receipt, matching profile/target/runtime identity,
re-attested file-instance commitment and completed status.  Otherwise the
host records comparison `unavailable` or `indeterminate`; it must never infer
`equivalent`.  Invalid shadow output produces `shadow.failed`, never
`shadow.completed`.

Usage summaries are captured from separate, declared legacy/shadow metric
roots and retain side invocation identity, provider status, `parseErrors`,
cached/uncached dimensions and nulls.  Valid complete summaries are
`measured`; valid incomplete summaries are `partial`; absent summaries are
`unavailable`; malformed, identity-mismatched or internally incoherent
summaries are `invalid`.  The comparison calculates a per-dimension
`v2MinusLegacy` only if both summaries are measured and both numeric values
exist.  Every null delta has a fixed reason; missing shadow usage cannot
produce a zero delta.  Reuse adds no invocation or usage record, and archived
attempt metrics are never overwritten.

Lifecycle observations are non-authoritative, post-commit host metadata:
`legacy.started|completed|failed`,
`shadow.started|completed|failed|timed_out|interrupted|unavailable`,
`comparison.completed|indeterminate|failed`, and
`session.completed|manual_recovery_required`.  They contain neither provider
payload nor raw evidence and cannot make an artifact authoritative.  CTX-08
remains `provisional-no-empirical-baseline`: R1C records data only and cannot
calibrate policy, alter budgets, declare an SLO, promote v2 or select a
winner.

Production continues to select only the fixed native fail-closed backend.  A
separate import-only test backend starts a real supervised fixture child for
functional nested-sandbox tests but has no production selection path, command
override or native-containment claim.  Its fixtures explicitly demonstrate
denied publish, network and external-write operations; native probe results
remain reported as native results.

## CTX-09C-R3A current candidate admission and pre-commit privacy

The live host admits an existing producer source only after deriving the
current candidate and comparing its entire private
`records/ROLE-candidate-binding-v1.json` commitment. Schema validity, comparison
identity, an existing path and a valid CTX-09B receipt alone cannot authorize
adoption. The closed binding records comparison execution, actual side producer
execution/version, runtime, workspace identity, profile/target, canonical shared
packet digest, semantic projection digest and the revalidated producer receipt
digest. Legacy additionally binds the exact current sensitive outcome manifest
digest, after re-attesting both streams and matching its stdout to the candidate.
Shadow reprojects the current completed CTX-06 chain and requires byte equality
with the canonical candidate; its workspace comes from that run's envelope and
its chain digest covers the validated HEAD and committed provenance artifacts.
Legacy's host comparison namespace supplies its local workspace identity; this
does not attest the caller's active workspace, which remains R3B work.

Only identical complete candidate bindings permit idempotent reuse. Missing or
different bindings reject the existing projection with `candidate-conflict`;
an output not derivable from current producer authority is
`candidate-binding-invalid`. Rejection neither overwrites forensic bytes nor
registers them for comparison. In particular, current legacy `blocked` and
current shadow `fail` cannot reuse a stale legacy `fail` to claim equivalent.
Bindings contain sensitive exact-outcome commitments and remain host-private;
they are not delivery, usage or CTX-09B inputs.

`context-shadow-privacy.py` is shared by consumer pre-commit admission and
external semantic publication. It screens all checkpoint/result/projection
strings and keys for undeclared environment/credential/Authorization/cookie,
token, prompt, raw response/reasoning/provider stderr/source/diff/evidence
surfaces, including ambient arbitrary environment values. The consumer performs
this check and validates typed observation semantics/identity before calling
CTX-06 `accept_checkpoint`. A rejected first checkpoint creates no transition,
completed HEAD, compare-eligible artifact or producer receipt. Diagnostics are
fixed, host-generated and contain no rejected value or digest. Exact legacy
stdout/stderr/outcome remain a distinct sensitive local surface and are excluded
from this semantic privacy guard.

Real event hooks exercise process exit, exact stream capture, attested private
outcome publication, validated projection, semantic producer publication,
private legacy receipt publication, committed legacy HEAD and shadow invocation
in that order. The host re-reads the legacy HEAD barrier immediately before a
shadow invocation. Pre-HEAD publications remain non-authoritative and the
existing reconciliation protocol remains unchanged.

The production CTX-09A helper accepts no `--test-only-backend` selector and has
no environment-selected permissive fallback. Native denial/unavailability
prevents invocation. CTX-09C preserves authoritative legacy delivery with shadow
unavailable. Offline registration coverage uses only the separate fixed
`tests/context-runtime-mode-test-only.py` harness; it cannot invoke a real
provider. Native hostile-process tests use actual publish/write/read/socket/
service lookup operations, with no cooperating deny flags or successful network
connection. An unavailable native probe is explicitly reported, not credited
as successful containment.

The host captures shadow usage after every reaped invocation, regardless of
completed/failed/timed_out/interrupted execution status. Coherent complete usage
remains measured, coherent incomplete usage partial, missing usage unavailable,
and inconsistent usage invalid. Terminal status remains separate; only two
measured numeric sides produce deltas. R3A changes neither CTX-09B/CTX-08 nor
the general CTX-06/07 runtimes, and adds no workspace attestation, HEAD/bundle
re-attestation or crash-recovery R3B protocol.

## CTX-09C-R3B workspace binding and deterministic recovery

R3B binds every shared packet to the host-derived active Mana workspace. The
closed packet carries explicit comparison, legacy and shadow execution IDs,
execution version, profile and target identities, the CTX-04 manifest, a
CTX-05 evidence manifest, exact workspace-manifest bytes, and separate digests
for the workspace binding, packet identity projection, evidence snapshot, mode
decision and CTX-08 budget decision. The host reopens the named canonical
`.mana/features/` or `.mana/sessions/` manifest and re-derives `workspaceId`
with the CTX-05/06 workspace identity contract before any producer intent or
invocation. The shadow consumer materializes the same workspace manifest in
its isolated run view and verifies the CTX-04 execution/profile, CTX-05
execution/workspace, CTX-06 envelope/run-record/workspace, packet identity and
fixed producer identity. Foreign, missing or copied workspace/execution state
fails before a producer can run.

Each live-shadow HEAD has an immutable per-bundle head commit which seals the
HEAD file instance and current bundle file instance. Reachable bundles seal
their predecessor instances; state seals exact outcome streams and manifest,
producer receipts and commits, candidate bindings, semantic artifacts,
comparison attempt/seal/result, and the comparison-stage ancestry. Every read
requires the committed path, regular single-link type, `0600` mode, device,
inode, size, nanosecond mtime/ctime and content digest. Identical-byte inode
replacement is therefore not reuse for HEAD, tip or previous bundles, outcome,
producer records, projections, comparison attempts or comparison records.

Exact-outcome publication uses identity-owned stage/owner pairs. Reconciliation
opens them FD-relative/no-follow, validates comparison identity, target, parent,
packet and payload digest, then removes an already adopted duplicate or aborts
an incomplete isolated stage. Unowned, foreign, special, linked or conflicting
entries fail closed. A fully published and re-attested exact outcome may be
sealed after a pre-receipt crash without replaying legacy; an incomplete
pre-link stdout stage remains ambiguous and is never replayed.

A completed CTX-06 shadow chain supersedes a bare process-intent ambiguity.
Recovery replays and re-attests that chain, reconstructs the missing CTX-09B
projection, publishes or adopts the shadow receipt, adopts or performs the one
reserved comparison, advances the single live-shadow CAS chain and returns the
original exact legacy streams/status. It never invokes the provider again.
Only incomplete, conflicting or non-reattestable chain state may enter manual
recovery.

The native backend scratch is a private comparison-local invocation directory.
An owner record is written inside it, a matching host registration precedes
invocation, and an immutable cleanup receipt makes removal crash-reconcilable.
Completion, failure, timeout, interruption, retry and reuse remove a verified
scratch tree using FD-relative/no-follow traversal. An unregistered but valid
owner is an abortable pre-invocation orphan; foreign or special contents are
ambiguous and are preserved by fail-closed recovery.

R3B changes neither CTX-09B verdict semantics nor CTX-08 budget status or
calibration. Legacy remains the sole delivery authority; shadow and comparison
remain local, diagnostic and side-effect-disabled.

## CTX-09B deterministic semantic comparison

### CTX-09B-R1 producer publication and local identity

The only producer flow is runtime host publication → committed producer receipt
→ CTX-09A registration → CTX-09B comparison. `context-runtime-mode.py` supplies
fixed host publication entry points `publish_legacy_artifact` and
`publish_v2_artifact`; the latter requires the host execution version (integer
≥ 1), while legacy has no execution version and records null. These functions
publish bytes, not attest an existing caller-selected file. There is no producer
CLI, `--producer`, receipt dict or caller-selected receipt path. The runtime
role is fixed in host code, outside model output. The import-only producer
harness under tests is explicitly test-only and is not installed or dispatched
by either comparison command. This is publication plumbing, not a semantic
exporter or a live shadow harness; unsupported existing outputs remain unsupported.

Publication traverses and re-attests the anchored CTX-03 ancestry, writes a
0600 staged regular single-link file below 0700 directories, fsyncs and checks
its bytes through its actual FD, and uses the kernel FD-relative no-replace
rename. It retains that FD through receipt commitment; collisions are never
overwritten. Both bytes and local object identity are checked before commit.

For an artifact path P in execution X, the host derives K = SHA-256(UTF-8(P))
and uses only `.mana/runtime/producers/X/K/producer-receipt-v1.json` and
`.mana/runtime/producers/X/K.commit/producer-commit-v1.json`. All producer
namespace descendants require host ownership and 0700; records require 0600,
regular/single-link type, closed canonical sorted-key UTF-8 JSON and a newline.
Receipt schema version is `mana.context-runtime.producer-receipt/v1`. Its
fields are `receiptId`, `producerRuntime` (legacy/v2), `executionId`,
`executionVersion`, `profileId`, `targetKey`, `artifact` (path, sha256,
fileInstance), and `producerContractVersion`
(`mana.context-runtime.artifact-publication/v1`). `receiptId` is SHA-256 of
canonical receipt bytes with that field omitted. The separate immutable
`mana.context-runtime.producer-commit/v1` record commits receiptId, the full
receiptDigest, executionId and artifactPath. Each record is privately staged
and atomically published with no replacement. A receipt without its commit
is an orphan, never producer authority; partial failed publications require
host recovery and cannot be relabeled or reused.

`fileInstance` contains integer device, inode, mode (including file type), size,
mtime_ns and ctime_ns from fstat on the real publication FD. The content SHA-256
and file-instance commitment serve distinct purposes: bytes and the local
filesystem object. This identity is local to the filesystem/run, not a universal
content address and not portable by copying files to another host/filesystem.
Unchanged files/receipts yield byte-identical diagnostics across repeated reads;
independent publications carry distinct local commitments even with identical bytes.

Compare registration requires expected host profile and target identity
(`--profile-id` and `--target-key` on the internal helper; the public profile
command binds its selected profile and requires `--comparison-target-key`).
It resolves both receipts autonomously, checks the role against producerRuntime,
execution/profile/target, receiptId and the independent committed receipt digest,
and verifies both artifact digest and fileInstance. The registered roles are
requirements to verify, never producer identity by themselves. Old path/digest-only
registrations, missing/uncommitted/foreign/stale/tampered receipts, role swaps,
digest mismatches and altered local objects fail closed with exit 2 and no report.

The comparator re-resolves each receipt/commit and checks every registered binding,
including execution version and receipt digest. All bindings are re-attested
before registration/comparison. Each supported native artifact's declared
`profileId` and `targetKey` must also match its own verified producer receipt.
A mismatch yields `indeterminate`, `complete: false`, with `profile-mismatch`
and/or `target-mismatch`, even when both artifacts declare identical foreign
headers or contain a known semantic difference. Unsupported formats remain
indeterminate without inferring identity from free text. Artifact reading checks the
expected fileInstance using fstat before and after the same FD read/hash/parse
capture, named-file metadata and root/parent path bindings. Receipt and commit
are read again after artifact reading to reject receipt mutation during the read.
A new inode with identical bytes, mutation of bytes/metadata on the same inode,
path rebinding, symlink/hardlink/special file or altered commitment is rejected.
No evidence payloads, model prompt/response/reasoning or raw provider payload
occur in receipts, commits, registration or reports. This retains the existing
local host-UID/kernel/power-loss threat boundary; it is not cryptographic proof
against an unrestricted hostile process capable of rewriting all host state.

### Boundary and invocation

`scripts/mana-context-compare.sh EXECUTION_ID --project-root PROJECT`
is a separate offline consumer, not a fifth mode and not an automatic action
of `run-profile.sh --context-runtime compare`. CTX-09A registration gains only
the producer/object bindings above; legacy/default execution and shadow/v2 dispatch remain unchanged.

The command accepts only an existing execution ID and a host-owned project
root. It derives the private CTX-09A mode-plan path, requires its exact closed
canonical compare/v1 shape, and reads only its two registered sources. It
rejects shadow hand-offs, arbitrary source/output paths, unknown fields,
duplicate JSON keys, non-finite values and forged or stale registered digests.
Fixed installed JSON Schemas are the only additional local reads; their
references cannot select arbitrary files or fetch a schema from the network.
No HEAD, run-state, provider output stream, environment override, approval
authority or checkpoint is read or mutated.

Exit 0 means a diagnostic was generated, including `different` and
`indeterminate`. Exit 2 means a safety/contract/IO rejection and emits no report
body. Neither exit status is a release gate or approval.

### Provider-neutral semantic projection

`contracts/context-runtime/semantic-comparison-input-v1.schema.json` defines
`mana.context-runtime.semantic-comparison-input/v1`: a bounded (256 KiB), closed
local projection containing `profileId`, an opaque SHA-256 `targetKey`, and
explicit semantic dimensions. This phase supplies curated local projections,
not a model call, Markdown extractor, runtime exporter or migration. Existing
artifacts that do not carry this contract produce an indeterminate diagnostic,
even when their bytes are identical. Malformed declared native input fails
closed. The same profile and target are required before semantic matching.

The dimensions are status, blockers, warnings, evidence references, requirement
coverage, approval gates, activated risk domains, high-risk escalation,
unresolved questions, final artifact completeness, human usefulness disposition
where explicitly available, and observed external-write policy. Each dimension
has explicit `complete`, `partial` or `unavailable` coverage, bounded records
and typed uncertainty/gap codes. Omission is unknown, never an empty collection.
Only human disposition can explicitly be `not-applicable`, with no records or
gaps; it is not inferred from absent data. Complete singleton observations
require their canonical key. An empty artifact-completeness collection cannot
establish equivalence. The projection's complete collection declarations are
input assertions, not independent proof that a review found every real issue.

Findings and questions match by typed subject (domain/kind/identifier) and
predicate, not free-text similarity or provider-local finding ID. Evidence
matches by stable `sourceKey`; requirement, gate, domain and artifact IDs are
stable semantic identities. Duplicate local IDs or canonical semantic atoms
are rejected rather than overwritten, merged or silently deduplicated.
Predicate/subject changes cannot be interpreted as paraphrases.

CTX-09B-R1 also builds a global semantic claim index across all structured
assertions, independent of presentation dimension. The current contract carries
stance-bearing findings in blockers and warnings; its key is canonical typed
subject plus predicate, with no label/local ID/dimension/severity in the key.
All occurrences are retained, including their original dimension, JSON pointer,
stance, uncertainty and provenance. Identical compatible stances may coexist in
different dimensions. Affirmed and denied for the same key conflict; no dimension
precedence or last-write-wins is applied. `contradictory-evidence` uncertainty
explicitly declares an unresolved conflict, without interpreting free text.
The report's `conflicts` collection is sorted by side and semantic key and
preserves every conflicting observation. Any internal unresolved conflict forces
aggregate status `indeterminate`, `complete: false`, and reason
`unresolved_internal_conflict`, even if both sides contain identical contradictions
or a known difference exists elsewhere. Input uncertainty is never a resolution.

Typed stance (including negation), severity, validation, status, gate state and
requirement, coverage, risk tier/domain, escalation, question disposition,
artifact schema/state, evidence metadata and observed write policy are
semantic values. JSON property/array presentation order, explicitly declared
sets, inert single-line `label` annotations and local finding/evidence aliases
are representation only. A label is not a normative claim: all meaning must
be encoded in the typed value. No arbitrary prose normalization or semantic
inference from a label occurs.

### Outcomes, uncertainty and provenance

`contracts/context-runtime/semantic-comparison-v1.schema.json` defines the
bounded (1 MiB), closed diagnostic report. Dimension and record order is stable,
reasons and set fields are sorted, and canonical sorted-key UTF-8 JSON has one
trailing newline. Identical registration/source bytes produce identical report
bytes across repeats with the same committed local files. File-instance identity
is local, so independent copied publications have different bindings. No diagnostic timestamps or random IDs
occur in the report. Presentation changes legitimately change source digests
and original JSON pointers, but not the semantic outcome.

Records preserve only actual observations: original IDs, JSON pointers, typed
values, uncertainty and evidence references/metadata. A missing counterpart
is `null` plus `one-sided-observation`, never an invented finding or an inferred
missed-finding verdict. A one-sided observation is different only when both
collections are complete and the available observation is sufficiently known.
Partial/unavailable collections cannot prove absence.

Equivalent findings require usable declared provenance: referenced evidence
must exist inside the registered projection, have complete collection coverage,
no uncertainty/gaps and non-null revision/SHA-256. Evidence references with
different usable metadata are surfaced, not erased. Evidence bodies, URLs or
files named by evidence records are never followed/read. Evidence SHA-256 here
is declared metadata; registration, committed producer receipt and source-artifact SHA-256 are verified
against actual bytes. The report explicitly scopes provenance accordingly.

Unknown values, uncertainty, declared gaps, open questions, missing/invalid final
artifacts, absent provenance and unavailable/unspecified required escalation
prevent equivalence. Known value differences may remain `different` while
other dimensions are incomplete; `complete: false` preserves that limitation.
If no known difference exists and any necessary data is unavailable, the
aggregate is `indeterminate`. Byte identity is reported separately and never
short-circuits semantic validation. `representationOnly` is true only for an
equivalent structured result with differing source bytes.

Every report fixes `authority: none`, `permissionGrant: none`,
`externalActions: disabled`, `executedRuntimes: []`,
`humanReviewRequired: true`, `nonDegradation: not-established` and equivalence
scope `declared-structured-semantics-v1`. Approval and write-policy values are
observations, not capabilities. Equivalence does not establish evidence truth,
artifact-schema compatibility, human readiness or overall non-degradation.
The comparator neither chooses nor publishes an authoritative output.

### Filesystem, privacy and tests

The shared CTX-09A reader captures and hashes the same bytes, checks regular
single-link/host-owned files, size/identity/mtime/ctime before and after reading,
named bindings and the complete anchored root/parent ancestry. Root, parent,
intermediate and final symlinks, traversal and special files fail closed.
Mode-plans require 0600, and the comparison namespace/registration directories
require 0700. Shared existing `.mana/runtime` permissions are never changed.

Default output is stdout only. Optional `--write-report` derives only
`.mana/runtime/comparisons/EXECUTION_ID/semantic-comparison-v1.json`, beside the
unchanged mode-plan. A private 0600 staged regular file is fsynced and attested
before host atomic no-replace publication. Parent/root and exact bytes are
re-attested after publication and before commit. Collisions of every type are
rejected, never overwritten. Handled failures/signals roll back and clean the
operation's identity-matching staging file with held descriptors, including
parent rebinding; no directory creation or outside-path writes occur. The
CTX-09A SIGKILL/power-loss/hostile same-UID host-recovery limitations still apply.

Reports persist only typed diagnostic/provenance metadata and registered
relative paths/digests, never labels, prompt, response, reasoning, credentials,
arbitrary environment, raw trace, source body, full diff or raw evidence.
Failures use a fixed diagnostic without echoing input/error payloads.

`bash tests/context-runtime-comparison.sh` exercises the curated semantic corpus,
representation-only changes, known blocker/gate/risk regressions, partial and
missing inputs, unsupported formats, uncertainty/provenance, deterministic bytes,
schema parity and adversarial IO/publication. It is registered in the complete
zero-token suite and uses only local fixtures. CTX-09C has its own local stub
harness regressions. CTX-09G false-equivalence release audit, CTX-10+, PRC-*
and MIG-* are not implemented. Independent phase gating remains separate from
implementation tests.

## CTX-09C-R2A committed comparison projection and read isolation

The real shadow consumer materializes the captured host packet into a private
CTX-06 run and commits each checkpoint through CTX-06 publication and HEAD CAS.
The comparison exporter reads only the bundles named by that HEAD, replays their
host transitions, requires completed matching execution/profile/version and
re-attests HEAD after reading. Each exported provenance digest is checked against
the same canonical artifact bytes validated for the projection; a changed
checkpoint or merge aborts export. Orphan bundles, transcript and provider streams
are never comparison sources. Export cannot commit or become run authority.

A checkpoint may add `comparisonProjection`, a closed CTX-09B observation
contract. Its bytes are committed with the checkpoint. This additive integration
carries typed findings, gates, questions, coverage, uncertainty, evidence metadata
and artifact completeness without interpreting claim prose. Missing dimensions
are unavailable; untyped CTX-06 claims remain references in `provenance.unprojected`
and constrain affected dimensions. Earlier declared uncertainty and one-sided
observations survive the final handoff. Host projection provenance fixes authority
to none and records actual HEAD and committed object digests and relative refs.
Provenance is diagnostic metadata, not a semantic atom or permission grant.

Production native containment denies file reads (including metadata) except immutable stdin,
shadow scratch/run/metrics, explicit installed host code/contracts and system
loader/runtime paths. Ancestor directories can be opened for host FD traversal;
this does not authorize their descendant files. Project evidence is consumed only
from the captured authorized packet, never by following a locator. Legacy HEAD,
run-state, bundles, metrics, receipts, output and other comparison namespaces are
outside the read allowlist. Shadow read roots reject symlinks and multiply linked
files before launch. Native admission additionally attempts actual forbidden
reads, traversal, preexisting and newly created symbolic/hard-link escapes, publish, external write, network
and service lookup; it requires all denies plus an allowed input read. Admission
failure is unavailable, including a nested native sandbox rejection.

The import-only test launcher uses the same kernel policy and real supervised
process, accepts only fixed installed fixtures, and has no production selector
or cooperating deny flags. Timeout is `timed_out`, INT/TERM is `interrupted`, a
provider nonzero is `failed`, and absent/unproven backend is `unavailable`.
R2A does not define legacy outcome/recovery or comparison exactly-once;
the separate R2B contract defines exact caller delivery.

When a phase has a CTX-07A merge, `comparisonMergeRef` binds its fixed
`phases/NNN-PHASE/delegation-merge-v1.json` path and actual digest inside the
committed checkpoint. Export rejects missing, changed, noncanonical or foreign
merge artifacts and verifies execution/version/workspace/profile/phase/attempt.
Its artifact reference preserves the original point provenance, questions,
findings and uncertainty; incomplete/conflicted merges constrain comparison
coverage. Fields absent from CTX-07A (for example finding validation) remain
unknown rather than being inferred. A merge outside committed HEAD ancestry is
never read.

## CTX-09C-R2B exact legacy outcome authority and caller convergence

The recovery host publishes `.mana/runtime/shadows/COMPARISON/recovery/`
(0700, host-owned), with single-link, host-owned 0600 `stdout.bin`,
`stderr.bin` and `legacy-outcome-v1.json`. Streams are exact bytes, without
UTF-8 conversion, JSON reconstruction, canonicalization or comparison size
limits. The closed outcome manifest contains only stdout/stderr file records
(fixed relative path, actual-byte SHA-256 and file-instance commitment), exit
status, termination kind and producer invocation identity. Termination is
`exited`, `signaled`, `timed_out` or `interrupted`; shell-compatible status is
preserved, including legacy exit 23. The outcome is a **sensitive local
recovery/delivery artifact**, not privacy-safe.

The outcome is local and Git-ignored with the generated `.mana/` namespace.
Only the recovery host consumes it. R2A's native read boundary excludes it
from the shadow read allowlist. Permissions enforce host-user access, not
separation from other processes already running as that user. No stream,
outcome locator, raw-byte digest or file-instance commitment enters public
comparison, lifecycle, usage or result/receipt payloads. The private host
`records/legacy-receipt-v1.json` binds the outcome manifest's actual bytes and
file instance; HEAD/bundles bind this private receipt. CTX-09B producer receipts
bind only the separate bounded, structured, privacy-screened projection.

Legacy commit requires a complete re-attested exact outcome, a valid committed
comparison projection when available, the private producer receipt, immutable
state/bundle and authoritative HEAD. A process exit or orphan bundle alone is
not committed. After the HEAD barrier, every handled exception—including
RuntimeError, backend/shadow/usage/artifact/receipt/comparison failures and
non-destructive recovery or context cleanup failures—returns cached exact
stdout, stderr and exit status. Advisory metadata never goes to caller stderr.
Legacy nonzero commits and replays identically and suppresses shadow.

On rerun, the host takes the same comparison lock, reads HEAD and its bundle,
re-attests the receipt, manifest and both streams (digest and file instance),
and delivers the original bytes. It never reconstructs delivery from the
comparison projection. A second concurrent caller blocks on that lock and
then reads committed HEAD: only the winner invokes legacy, and both callers
return byte-identical stdout/stderr and the same status. A receipt published
before HEAD permits only the missing legacy commit, after full attestation.

Missing/tampered outcomes or receipts, identical-byte file replacement,
unsafe permissions and inconsistent commitments require
`manualRecoveryRequired`/`manual_recovery_required`. No legacy side effect is
automatically replayed and no substitute legacy output is fabricated. An
unattestable outcome raises the explicit recovery error; the CLI exits 2 with
only a fixed recovery diagnostic, not a claimed legacy result. A shadow-only
manual handoff still delivers an attested committed legacy outcome.

Retention is explicit: sensitive outcome files and their private receipt are
retained for the lifetime of the comparison identity, including failed/manual
handoffs; no automatic expiry or success cleanup removes replay authority.
The owner may clean up only after all callers have finished, while holding
the comparison lock, and must retire the entire comparison namespace as one
unit. Partial deletion requires manual recovery and does not authorize reuse
of that identity. Backups/exports/public diagnostic bundles must exclude the
recovery directory and private authority journal/receipt. R2B adds no expiry
daemon, new recovery stage policy, comparison exactly-once or promotion logic;
R2C/R2D and CTX-09G+ remain outside scope.

## CTX-09C-R2C full re-attestation, exactly-once comparison and crash reconciliation

R2C strengthens the private R2B journal, without adding a public mode or
promotion policy. Every HEAD read verifies canonical state, execution and
packet identity, the recomputed bundle ID, the complete immutable bundle and
each reachable predecessor down to `initialized`. Previous edges commit both
the state digest and the predecessor bundle's fixed path, byte digest and file
instance. Revisions and permitted stage transitions must match; inherited
receipt/attempt commitments cannot change. An incomplete or foreign chain,
missing referenced artifact or unexpected stage is rejected before reuse.

Every reachable state's producer sources are re-resolved through the installed
CTX-09A producer reader: receipt and producer commit, producerRuntime,
execution/version/profile/target, artifact digest and file instance must all
match. Private journal commitments additionally bind the file instances of
the producer receipt and commit themselves. The private legacy receipt,
sensitive outcome manifest and both exact streams are re-attested on every
reuse, including `completed`. Shadow receipts must agree with the state's
artifacts, outcome, validation and usage. Missing, modified or identical-byte
inode replacements fail closed. An invalid authoritative chain raises
`manualRecoveryRequired`; it is preserved, rather than publishing a guessed
replacement HEAD whose predecessor cannot be verified. After a successfully
attested legacy barrier, R2B's cached exact delivery still covers advisory and
cleanup exceptions within that invocation.

`records/comparison-intent-v1.json` reserves the sole comparator invocation
under the comparison lock. The immutable
`records/comparison-attempt-v1.json` binds the comparison execution, input
receipt digest (the validated host packet digest), both producer receipt
digests, the ordered legacy/v2 pair identities, both private side receipts,
the complete schema-validated CTX-09B report and its bounded result. The
separate immutable `records/comparison-attempt-commit-v1.json` seals the
attempt's byte digest and file instance, input/pair/producer identities and
report/result digests before the pre-HEAD publication boundary. A replaced
or incomplete orphan attempt cannot be adopted by recapturing its new inode.
HEAD additionally binds the seal's own bytes and file instance. The
comparison stage in `live-shadow-head-v1.json` is the comparison HEAD/CAS:
it commits the attempt's exact bytes and file instance, plus the separate
bounded comparison record. There is one authoritative chain for all stages.

If an attempt is published before its HEAD, the next lock holder verifies its
identity, receipts, pair, report registration/sources, outcome and schema,
then adopts it by the missing CAS. It invokes no comparator. A committed
comparison HEAD likewise reuses the attempt with zero further invocations.
An intent without a complete valid attempt is ambiguous and becomes terminal
`comparison_indeterminate`; an invalid orphan attempt is deterministically
excluded from authority with the same terminal observation. Its forensic
bytes may remain private, but never authorize reuse or another invocation.
Failures before an invocation reservation may produce the same terminal
diagnostic. Comparison remains non-authoritative; the original legacy outcome
is delivered unchanged. A shadow intent without a complete receipt similarly
requires manual recovery, never a repeated shadow process.

The live host materializes the packet at the single private fixed path
`input/shared-input-v1.json` beneath the comparison namespace. `initialized`
commits its path and input digest before publication. Its directory is 0700
and its single-link host-owned file is 0600. Under the comparison lock,
reconciliation first deletes any prior packet and abandoned HEAD CAS
temporary, then re-attests the complete authority chain. Active sessions
materialize only the caller's validated identical packet. Every normal or
handled failure exit removes the packet and its empty directory. Abrupt death
can leave only this state-referenced packet; the next lock holder removes it
before retry, reuse or a terminal recovery error. A terminal reuse creates no
new packet. Sensitive R2B outcome/receipt retention remains unchanged.

`tests/context-runtime-r2c.py` uses real forked hosts, fixed local subprocess
producers, the real offline comparator, filesystem publications, flock and
`os._exit(99)`. The crash matrix covers packet publication, input
materialization, legacy artifact/receipt before HEAD, legacy HEAD, shadow
artifact/receipt before HEAD, shadow HEAD, comparison attempt before HEAD,
comparison HEAD CAS and comparison HEAD before cleanup. It verifies real
invocation counters, no duplicate side effects, packet references/modes,
zero residual packets/CAS temporaries after reconciliation, an unchanged
outside tree, and two concurrent callers converging on the same exact legacy
outcome with one legacy, one shadow and one comparison committed in one
validated chain. Ambiguous deaths during either producer or inside the
comparator, terminal legacy failure, foreign stages/chains and tampering of
each reachable authority artifact are covered separately. Native containment
is verified by the separate R2A/live-shadow canaries; the process fixture
does not claim a native containment pass. R2D and CTX-09G+ remain outside scope.
