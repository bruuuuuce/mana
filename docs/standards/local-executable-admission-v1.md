# Local Executable Admission v1 — entry proof only

This opt-in additive T01 extension implements the single increment authorized by
[ADMISSION-D01](../reports/TRANSACTION-REAL-01-T01-ADMISSION-D01.md), section 8.
It establishes one **conditional Java entry**, with a source-linked cut at the
callee body entry. It grants no authority to the ordinary T01 causal trace.
`mana.transaction-model/v1`, its frames/events/states, and the static
[dependency catalog](executable-dependency-contract-v1.md) keep their meanings.

## Representation and compatibility gate

The optional top-level `localAdmissionExtension` has discriminator
`mana.local-executable-admission/v1`, scope
`CONDITIONAL_LOCAL_JAVA_ENTRY_ONLY`, a pinned `requestedSite`, zero or one `entries`,
a reason, fixed INCOMPLETE completeness, NOT_ASSERTED negative authority, NONE
causal-trace authority, fixed limits, and the complete source-free evaluation
witness. `transactions/local_admission.py` is the semantic validator; like T01,
this contract uses a Python validator rather than a JSON Schema.

An admitted record preserves caller/target canonical signatures, source hash,
UTF-16 site/declaration spans and the existing catalog's source-site ID algorithm
(SHA-256 of sorted compact ASCII JSON `[callerIdentity, siteEvidence]`). It contains
`ENTRY_JUSTIFIED_UNDER_PREMISES`, named premises, the evaluation proof, UNKNOWN
completion/return value, NOT_OBSERVED runtime execution, UNKNOWN transaction context,
NOT_ASSERTED interception, and a frontier at `CALLEE_BODY_ENTRY` with
NOT_ASSERTED body traversal and UNKNOWN continuation. The declaration span locates
the callee; it does not claim the first callee statement has executed.

| Proposition | Authority of this increment |
|---|---|
| Call statically present/bound | Source attribution plus canonical source-linked site |
| Conditionally reachable | Implication from entry into the caller's available instance body |
| Entry justified | Only when the closed evaluation rule and pinned request/site agree |
| Call completed / return value | UNKNOWN, including empty or apparently simple callees |
| Runtime observed | Never; NOT_OBSERVED |

No `FRAME_ENTER`, `FRAME_EXIT`, unresolved-call event, child, entity or physical
identity is added for this proof. A proof's local ordering has its own source
coordinates, **not** a T01 event position. In particular, FRAME_EXIT in the legacy
trace cannot be used to claim the new local callee returned. A legacy
NOT_ASSERTED root and a positive local implication can coexist: the former asserts
no body path in the causal trace; the latter has precisely the bounded authority
above. STRAIGHT_LINE is never reinterpreted as partial traversal.

Ignoring this extension discards a local positive fact and retains the original,
more conservative execution projection. No legacy conclusion needs the new fact
as a premise. Existing validators still reject children in NOT_ASSERTED bodies;
the new validator additionally rederives the certificate. Old-input/new-consumer
and new-input/old-consumer cases are tested with actual HEAD T01/S01 validators.
This is not permission to add events or to let a legacy consumer certify the
extension. A future use of this proof to position resources, close a call or
propagate a context requires another compatibility decision.

## Closed frontend rule

`PRIVATE_SELF_PREFIX_V1` runs in the existing attributed JavacTask, after global
attribution. It is not a second semantic resolver, a general interpreter or CFG.
The source inventory, classpath, JDK, parse-snapshot replay and all existing
budgets remain explicit. No target bytecode is generated or executed.

The only accepted prefix is zero to 32 local declarations of exact primitive
`int` initialized by an AST INT_LITERAL. The next statement must be a direct
method-call expression or a local declaration whose entire initializer is that
call. Only the first such call can qualify; there is no skipping an earlier call,
conditional branch, return, allocation or effectful initializer.

The caller must be an instance method with a body. The receiver must be implicit
`this` or explicit unqualified `this`; the selected target must be private,
nonstatic, nonsynchronized, nonnative and declared in the same owner. Varargs and
explicit generic invocation are rejected. Every argument must be an AST read of
a caller formal or a boolean literal, with exactly the corresponding target
parameter type: no boxing, unboxing, application conversion, field dereference,
allocation or nested invocation. Symbol identity fixes each formal's index.
Receiver and arguments are evaluated before entry, arguments left to right.

These accepted steps do not initiate class initialization or construct an
instance. The premise is **entry into an already available instance's caller
body**, not successful Spring startup, completed global initialization or absence
of lifecycle effects. An effectful initializer before the selected call blocks
that call. An owner field initializer outside the caller body cannot be silently
promoted to harmless: its execution lies outside this conditional implication.
Synchronized/native callee entry needs additional monitor/linkage premises and is
blocked, even with a private binding.

The frontend emits expression/statement evidence, canonical symbols and the
closed rule result in a separate `mana.java-local-entry-evaluation/v1` witness.
Existing EXEC-01 recovery and MODEL-EXT-01 catalogs remain static-only. Matching
catalog sites must agree on identity, declaration and exact DIRECT binding; the
catalog itself still does not assert admission.

## Verification and use

1. Build the ordinary T01 and, when available, its verified dependency catalog.
2. Call `evaluation_witness` with the explicit source/entry/dependency/environment
   inputs and canonical parse snapshot.
3. Call `attach_local_admission` with that witness and a **separately pinned**
   request and requested site. It copies the model, reattributes the witness,
   validates the full result and enforces the existing 4 MiB payload limit.
4. After transport, call `verify_local_admission` with the original pinned inputs.

Structural validation checks source inventory, spans/containment, prefix/argument
order, exact projection, fixed levels, and canonical catalog agreement. It does
not authenticate an imported witness or prove omitted syntax absent. A coordinated
forgery of witness and certificate can pass structural checks; pinned source
replay rejects it. Tests demonstrate both the trust boundary and rejection. Loss
or contradiction of a required premise produces no admission; tooling/attribution
failure is rejected, not converted to a positive or negative fact.

The premises are entry into the caller instance body, ordinary synchronous Java
evaluation, and no assertion about additional runtime instrumentation. Transaction
interception, wiring, manager/P identity and runtime occurrence remain independent.
No Spring propagation rule, proxy interception or physical transaction is derived
from the private Java entry. This first increment deliberately retains UNKNOWN
context even when an independently qualified richer context might be possible.

## Consumers and frontier

S01 validates T01 and preserves the certificate exactly. It creates no observation
or timeline position from it and cannot place producer operations or the suffix
from the root context. S02 consumes the unchanged causal projection: no wait edge,
NO_CYCLE, resource absence or observed dependency follows from this certificate.
INCOMPLETE and globalRiskAbsence NOT_ASSERTED remain required. VIS-01 retains its
existing frontier rendering; no new renderer semantics or complete path is added.

The producer's body, completion, result assignment and following getters require
independent evidence. There is no implicit normal-return dependency, successor
promotion, negative inventory proof or global completeness claim.
