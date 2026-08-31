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

Every authority-participating checkpoint contains both `executionId` and
`executionVersion`. `evaluate_checkpoint(checkpoint, authority)` accepts authority only as a
validated `HostAuthorityContext`, never as fields extracted from the
checkpoint. Effective permissions are copied only from that host value. A
requested approval is complete only when checkpoint, host identity, and host
approval record all match on execution ID and execution version, and the record
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

`sourcePayload` and `normalizedRepresentation` distinguish the collected
sanitized source from the representation used for retrieval; `localPath`
remains the normalized representation for compatibility. Content blob paths
are derived from their sanitized-byte digest and are immutable. Source and
normalized blobs use separate namespaces and may be reused by multiple
records. Their digests and byte sizes are verified on reuse and retrieval;
collision or tamper is a hard failure.

Evidence record identity is not raw blob identity. The host derives `E-*` from
canonical metadata binding at least the execution, kind, source system,
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
