# Type dependency fixtures

Each case is a separate Java 8 source inventory. Entry is deliberately reused;
these files must not be parsed together as one application. The Python suite adds
an explicit synthetic Config/Sink inventory and a conditional context. No fixture
is a target service, and none is executed.

- Positive: three member declarations (static and inner), unused on zero/six
  parameter transaction paths; use in another method does not poison those paths.
- StaticUse, InnerUse: a static call and an inner receiver field require omitted types.
- ExternalBase, InterfaceUse: real unresolved inheritance required by body dispatch.
- NestedExtends, SelfSubtype, ForeignSubtype: an omitted type owns its inheritance;
  potential override/wiring effects retain UNKNOWN, including in another owner.
- Ambiguous: member Sink hides the top-level Sink; no bean or parameter type binding.
- Relevant: six arguments, local result type and exception allocation in unsupported
  statements, matching the relevant shape of REAL-01 without target code.
- LocalAnonymous, Initializer, ConstructorUse: explicit execution dependencies
  cannot disappear just because the extracted method call list is empty.
- OracleTypes: independent compiler fixture; javac emits Java 8 bytecode and javap
  verifies static/inner, extends/implements, local and anonymous metadata. No main
  method or target build is used. The expected outcomes are hand-written assertions.

Diagnostic sentinels must stay absent from default AST output. Full snapshots are
internal inputs to the local S01 validator and are never printed by this suite.
