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
