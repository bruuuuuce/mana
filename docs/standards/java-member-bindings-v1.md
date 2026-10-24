# Bounded Java member bindings — HYBRID-01

This optional producer implements the first increment in
[REAL-01 D02](../reports/TRANSACTION-REAL-01-D02.md): a local javac attribution
witness for selected static member dependencies of one entry declaration.
It does not change Transaction Model v1, Resource Timeline v1, the Wait Dependency
sidecar, VIS-01, parser snapshots, or any traversal/transaction rule.

## Explicit invocation

`python3 scripts/mana-java-member-bindings.py --project-root PROJECT
--request REQUEST.json --output-dir CANONICAL_EXTERNAL_OUTPUT`

The request has exactly four fields. For the independent Good fixture:

```json
{
  "sources": ["Good.java"],
  "entry": "fixture.Good#run",
  "dependencies": ["fixture.Good.Result", "fixture.Good.Failure"],
  "environment": {
    "jdkHome": "/absolute/path/to/selected/jdk",
    "release": "8",
    "classpath": []
  }
}
```

Only explicitly listed Java files are read. Package paths and original basenames
are preserved in an external stage. No source discovery, build, resident service,
network access or dependency download occurs. Classpath is an ordered explicit
list of existing offline JAR files; empty means an empty classpath. Directory
classpath entries and JAR manifest Class-Path references are rejected. Callers
must supply necessary related sources/JARs; the producer never searches Maven,
Gradle, the repository or the host for substitutes. JAR bytes are copied into the
stage and fingerprinted. A missing input remains unresolved.

The host JDK is explicit, with launcher, release, compiler/runtime modules/JARs
and native-library fingerprints. Java 8 uses its matching compiler with source
and target 8; newer JDKs use --release. Requests accept releases 8/17/21, subject
to the chosen JDK actually supporting that release. This delivery qualifies only
the tested Corretto 8 macOS toolchain; other releases/OSes are NOT RUN.

The supplementary helper uses public [JavacTask](https://docs.oracle.com/javase/8/docs/jdk/api/javac/tree/com/sun/source/util/JavacTask.html)
and [Trees](https://docs.oracle.com/javase/8/docs/jdk/api/javac/tree/com/sun/source/util/Trees.html) APIs, calling parse() then
analyze(), never generate() or call(). Annotation processing and implicit source
compilation are disabled. Target binaries are read by the compiler, never loaded
as application classes. Only the fixed Mana helpers are compiled and run.

## Witness and verification

`member-bindings.json` uses the new standalone `mana.java-member-bindings/v1`
envelope. It is not a T01 field and cannot authorize a transition or traversal.
`cost.json` is separate because wall-clock measurements are nondeterministic.
CLI stdout contains only status, reason and NOT_ASSERTED. Exit 0 denotes a complete
static snapshot, never successful transaction analysis; incomplete, conflicting or
blocked snapshots return 2 and preserve their explicit frontier when replayable.
Publication uses existing external/canonical/non-overwrite factory path rules.

The snapshot records source hashes, producer hashes, environment fingerprints,
limits and the exact entry evidence plus requested canonical nested identities.
Types retain owner, modifiers, containment, their own declared supertypes, method
signatures and declaration provenance. Unresolved members retain declared signature
syntax separately from a null attributed identity. Relationships distinguish TYPE_CONTAINMENT,
TYPE_INHERITANCE, TYPE_REFERENCE, VALUE_PRODUCTION and EXECUTION_DEPENDENCY.
Invocation targets are compiler-selected declaration signatures; inherited method
owners are retained. This does not identify runtime implementations or dispatch.
All positions are original UTF-16 offsets with exclusive ends, line and source hash.
Generated/default constructors without complete source spans remain unresolved in
the member catalog. Local/anonymous class bodies are not expanded.

States distinguish VERIFIED, UNRESOLVED and ABSENT facts, and CONFLICT versus
BLOCKED snapshots. All compiler errors invalidate every positive semantic binding
in this increment, including bindings that javac recovery appears to provide.
Diagnostic codes/lines preserve ambiguity versus missing-input evidence without
compiler message text. Nonstatic members, generic variables/captures and unsupported
value producers remain unresolved. Finding a declaration alone never resolves its
uses. COMPLETE covers the requested snapshot only; it is not execution completeness.

Python callers use `semantic.member_bindings(..., parse_facts=...)` with explicit
source bytes, entry evidence, dependency identities and environment. The parser
snapshot is independently reparsed by the existing leaf verifier before attribution;
a contradiction yields CONFLICT with no preferred target. Neither input is mutated.
`verify_member_snapshot(..., parse_facts=..., request=PINNED_REQUEST)` repeats the
adapter with caller-supplied source bytes, environment and separately pinned request,
then compares the whole normalized witness. Altered bindings, hashes, environment,
producer, request or limits are not silently upgraded. This proves reproducibility
against those inputs, not authenticity of a same-user host. Historical parse-only
snapshot verification remains unchanged. No unverified witness enters T01 or S01.

## Operational bounds and privacy

Defaults: 1–64 sources, 2 MiB combined; at most 16 requested identities; 20,000 AST
visits and depth 64 across bounded source scans; 32 classpath JARs/32 MiB compressed.
Each JAR is limited to 10,000 entries, 128 MiB expanded metadata and a 64 KiB manifest.
JDK fingerprinting is limited to 2,048 relevant files/512 MiB. The supplemental
compile-plus-attribution subprocess stage shares a 60-second deadline. JVM heap is
128 MiB and thread stack 1 MiB. These are JVM bounds, not a process RSS guarantee.
Output reads are capped at 4 MiB. Limits can only be lowered by Python callers.
A hit retains BLOCKED/UNKNOWN and clears all positive relations.

Parser extraction/reverification retains its existing separate 60-second timeout
per JDK invocation and 128 MiB parser heap. The CLI performs extraction, parser
reverification, attribution, and dedicated semantic replay; it does not claim that
this entire sequence or toolchain fingerprint filesystem I/O takes at most 60 seconds.
The supplementary helper first bounds AST size/depth before analyze(); compiler
internals are bounded by the stage deadline/heap, not by the AST scanner counter.
Operational timeout outcomes depend on host load; successful normalized semantic
witnesses are deterministic for fixed inputs/toolchain. Cost metrics are separate.

Compiler diagnostics are allowlisted code/line records. No bodies, argument values,
annotation expressions, receiver expressions or source snapshots are emitted.
Subprocess streams remain in private temporary files and are discarded; errors do
not echo exception text. Source-bearing parser data is used only inside the local
verification boundary. The CLI publishes symbol/position/hash metadata only.

No new third-party library is distributed. The existing externally provisioned JDK
remains required only for this optional adapter. The tested Corretto build is
8u442, Amazon distribution, OpenJDK GPLv2 with Classpath Exception; its local digest
manifest is recorded in each witness. No JDK or application dependency was downloaded
or bundled. Windows/Linux and JDK 17/21 distribution behavior remain unqualified.
