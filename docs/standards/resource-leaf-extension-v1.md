# Resource Leaf Extension v1 — T02-S01-D02-F02

Status: implemented, conditional static scenario; pending independent review.
This additive capability belongs to Transaction Model v1. It does not change
MR00 boundary effects or the causal cut of `UNRESOLVED_CALL`.

## Explicit activation and compatibility

Add this optional field to the existing transaction scenario JSON:

```json
"resourceLeafPolicy": "JDBC_LITERAL_V1"
```

Omission or `DISABLED` retains legacy traversal. The flag selects an authoritative
catalog and its explicit scenario premises; it cannot supply custom rules,
signatures or `safe=true` classifications. Unknown policies are rejected.
Both T01 and T02 CLIs use this same context input. No additional CLI, target
execution or activation infrastructure is introduced.

An enabled report retains `schema: mana.transaction-model/v1` and adds exactly:

```json
"resourceLeafExtension": {
  "schema": "mana.transaction-resource-leaves/v1",
  "sourceFacts": {"classes": [], "errors": [], "sources": {}}
}
```

The shown empty facts are illustrative; real reports contain the bounded parser
snapshot. The extension and facts are required even if no leaf qualifies.
Existing IR without this capability remains valid. Legacy artifacts and MR00
oracles are not rewritten. Newly parsed invocation facts additionally record
`statementCall`, a boolean indicating that the AST invocation is itself a
top-level expression statement in the enclosing method; old facts without it
cannot justify a new leaf.

Consumers must validate the extension version and all event kinds before
interpreting a report. An older T01 validator rejects `RESOURCE_LEAF_CALL` as an
unknown event; that failure must not be ignored. Older renderers that skip
validation are unsuitable for this extension. The updated Mana renderer validates
enabled reports and rejects unsupported event kinds/versions. Unknown events must
never be silently discarded to infer a normal continuation. Removing leaves
from a report is not a supported downgrade. Legacy mode is a fresh analysis with
the policy disabled; it preserves the first unresolved frontier and unplaced suffix.

## Event and witness

The new event is distinct from `UNRESOLVED_CALL`:

| Event field | Contract |
|---|---|
| `kind` | `RESOURCE_LEAF_CALL` |
| `sequence`, `frame` | Existing contiguous T01 event order and owning method frame |
| `callSite` | Actual invocation source path, SHA-256, line and UTF-16 span |
| `receiver`, `method` | Exact parsed invocation receiver and method name |
| `witness` | Required `mana.resource-leaf-witness/v1` object below |

| Witness field | Contract |
|---|---|
| `schema` | `mana.resource-leaf-witness/v1` |
| `rule` | `{id: spring-jdbc-template-literal, version: 2}`; fixed Mana rule |
| `signature` | Exact catalog owner, name, argument and erased return type |
| `receiverType` | `org.springframework.jdbc.core.JdbcTemplate` |
| `callSite`, `methodEvidence`, `bindingEvidence`, `argumentEvidence` | Source-linked invocation, enclosing method, allocated field and literal argument |
| `sourceCallOrdinal` | 1-based ordinal among the enclosing method's parsed calls |
| `t01Sequence` | Must equal the event's causal sequence |
| `normalReturnDependencies` | Sequence IDs of all earlier resource leaves on this single modeled path |
| `transactionContext` | Exact current T01 `{kind, physicalId, manager}` at invocation |
| `premises`, `limits` | Fixed catalog premises and limitations; not caller-authored assertions |

The library callee is terminal for exploration: no fictional source method frame
is created. The caller can continue only on the normal synchronous return path.
Each later leaf depends on all earlier leaves returning normally, including leaves
in resolved child calls. Subsequent frame/closing events are also on that same
conditional normal path. There is no prediction that an operation executed,
returned, completed successfully, committed or rolled back.

An exception does not reach that path's suffix. This increment does not enumerate
exception branches, catch/finally or physical outcomes; `outcome` remains UNKNOWN.
Normal-return premises cannot erase a later `UNRESOLVED_CALL` or legalize steps
after it. Leaf events occur inside completed frame boundary opening/closing and
require known current context. Known P must be live and unsuspended. Leaves do not
allocate P/L/SP/S, suspend, resume or terminate anything. Propagation and child
return context remain owned by the existing T01 engine and MR00 validator.

## Closed recognition catalog

Supported standard implementation overloads:

| Name | Resolved catalog signature |
|---|---|
| execute | `JdbcTemplate#execute(java.lang.String):void` |
| update | `JdbcTemplate#update(java.lang.String):int` |
| queryForList | `JdbcTemplate#queryForList(java.lang.String):java.util.List` |

These signatures are documented by the [Spring JdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
This is a versioned analysis rule, not identification of the target's installed
Spring binary or certification of every compatible implementation.

Positive certification requires both **TYPE_BINDING_PROVEN** and
**DISPATCH_PROVEN**. These are conceptual obligations, not new witness fields.
Rule version 2 replaces the original rule; the event and witness schemas stay v1.
A compatible spelling, import, signature or selected policy alone proves neither.

The deliberately small certifiable subset is a direct `private final JdbcTemplate`
field, without annotations, initialized at its declaration by exactly
`new JdbcTemplate()` (no arguments, anonymous body or alternate spelling).
`JdbcTemplate` must come from one explicit, nonstatic single-type import of
`org.springframework.jdbc.core.JdbcTemplate`. The owning class has no parents,
is a concrete top-level class, and has no omitted lexical scope. The allocated
class and the declared field type must bind through that same import. The library
declaration/API on the target classpath is an explicit authenticity premise; the
adapter does not identify or qualify the installed Spring binary.

The AST screen rejects all class or method type parameters, static or ambiguous
imports, application homonyms, unresolved parents, omitted nested/member/local/
anonymous classes and initializers. Generic bounds are not resolved: even a
Spring bound does not prove the exact allocated implementation. A type parameter
must not be replaced by an imported declaration; such field facts instead carry
`UNKNOWN_TYPE_PARAMETER:<name>`. Existing `dispatchHazards` carry the scope limits.
The screen still excludes source subtypes, implementation factories and unmodeled
wiring annotations conservatively over the whole source inventory. It does not
claim that this inventory contains all runtime implementations.

A fully qualified Java type is examined but remains uncertifiable in this bounded
adapter: package/type prefix attribution against the target classpath is absent.
Even when a separate javac oracle proves that particular fixture's binding, this
producer does not infer that proof from a dotted spelling. Wildcard-only imports,
generic aliases/bounds, inheritance and overload attribution are also UNKNOWN.
This intentional coverage reduction avoids a general Java resolver.

A directly allocated exact class, retained by a private final field, excludes
application receiver subclasses and their virtual overrides on ordinary Java
execution paths. An injected receiver, factory/proxy/decorator result, mutable
field or merely Spring static type does not establish that identity and remains
`UNRESOLVED_CALL`. Reflection/Unsafe mutation, bytecode rewriting, external advisors
and classpath substitution are outside the declared scenario. This is not a
closed-world assumption about Spring bean implementations. The earlier premise
that standard dispatch could simply be assumed for injected fields is withdrawn.
Library/driver/database behavior remains conditional as below; no concrete bean,
connection or datasource runtime identity is inferred.

The existing call restrictions also apply: a public nonstatic/nonabstract
zero-argument method, catalogued annotations, no AST hazards, receiver exactly
`field` or `this.field`, a standalone invocation, exactly one AST string literal
argument, and the supported API/SQL combination. With an exact receiver class and
a String literal, only the listed catalog overloads qualify; arbitrary overloads,
callbacks, dynamic expressions and unsupported methods remain unresolved.

Only the supported SELECT/UPDATE/INSERT/DELETE forms qualify. SQL demarcation,
DDL, stored procedures, compound SQL and SQL outside the closed grammar do not.
No SQL success, execution, datasource identity, lock or runtime transaction effect
is proved. Normal synchronous return conditions any continuation; unmodeled
transaction-context changes by library, driver or database are excluded by the
fixed scenario premises. Async, unknown annotations/interception/context and
unsupported control flow retain the original T01 frontier and causal cut.

## Verification and trust boundary

Both validators use the same authoritative catalog and binding/dispatch screen.
For any claimed leaf, `validate_model` also reparses the bounded source snapshot
from `sourceFacts.sources`, checks its UTF-8 byte hashes against the report's source
evidence and compares all regenerated AST facts. The original target is neither
read nor built during imported-JSON validation. The adapter parses only, disables
processors and never attributes, generates or runs target classes. Its helper is
compiled in an external temporary directory. Cached reparsing is keyed by source
content, not producer hashes or proof booleans. T01's derived `bindingEvidence`
pointers are separately checked against the receiver field before comparison.
Initializer shape and field modifiers are necessary internal AST facts; neither
conceptual proof property is added as a public assertion to the witness.

A valid report with rule-2 leaf events means certification is supported within
these premises. A valid report with `UNRESOLVED_CALL` and a
`RESOURCE_LEAF_TYPE_BINDING_UNPROVEN`, `RESOURCE_LEAF_DISPATCH_UNPROVEN` or source
screen reason means the invocation is recognized but uncertifiable. A claimed
leaf with missing/incompatible source proof or a forged witness raises the
existing validation error (CLI error behavior/exit codes are preserved). A policy
flag cannot turn the second or third result into certification. Old injected
leaf artifacts must be reanalyzed; they are no longer accepted as certified.
Legacy IR without the extension remains valid.

Validation also checks source method identity, containment, exact witness equality,
call prefix order/completeness, current T01 context, dependencies and physical
lifetimes. T02 validates T01 before projection and uses the identical source facts.
A source scope blocker rejects a standard witness even when its shape is valid.
An unresolved invocation preserves its known frontier context and cuts the suffix.
A type-parameter receiver's untraversed syntax is retained as an UNKNOWN observation.

Embedded source bytes and their hashes are consistency evidence, not independent
authentication of a coordinated replacement of source, hashes, facts and IR.
The read-only CLI checks one fresh source/context snapshot before publication.
Imported reports requiring source authenticity must be regenerated against the
original project. No Spring/database runtime, classpath attribution or bean
resolution is claimed. A future dedicated Java semantic frontend could provide
classpath-backed type/overload identity; runtime implementation selection would
still require allocation or wiring evidence beyond the static type alone.

Facts are embedded only for the enabled capability. Existing 4 MiB publication
limits still apply; the larger representation can hit that budget sooner and is
rejected rather than truncated. A path admits at most 128 resource leaves, bounding
the explicit dependency lists. The next eligible invocation becomes an unchanged
UNRESOLVED_CALL frontier with `RESOURCE_LEAF_BUDGET_EXCEEDED`; the known prefix is
retained and its suffix is not traversed. Validation rejects more than 128 leaves.

T02 places a recognized operation immediately before its authoritative leaf event
with `placement.status: T01_RESOURCE_LEAF` and the original
`beforeT01Sequence`. It copies current context and preserves normal-return
premises/dependencies in `premises`, without inventing T01 events. Datasource,
runtime resource identity, JDBC enlistment, acquired lock and granularity remain
UNKNOWN. FOR UPDATE is still request syntax, not a lock acquisition.

Run `python3 tests/transaction-resource-leaves.py -v` and `python3 tests/transaction-resource-binding.py -v`, plus the existing T01/S01
suites. The additional fixture oracles are hand-authored in
`tests/fixtures/resource-timeline/resource-leaf-oracles.json`.
