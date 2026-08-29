# Context Runtime v2 architecture decision

Status: accepted for staged implementation (CTX-00). This document changes no runtime behavior.

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
