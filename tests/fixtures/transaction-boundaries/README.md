# T01 static scenario fixture

`oracles.json` is the hand-authored semantic oracle for the eight required cases.
Each oracle names the entry, expected called method/source expression, physical
and logical identity relation, savepoint/suspension count and UNKNOWN frames.
Source call-site ranges and hashes are retained in the generated example models.

This is a parse-only fixture, not a runnable Spring application. The POM supplies
technology evidence; it is never built. `Config.tx` declares the concrete manager
for conditional resolution but supplies no actual database or initialized context.
`context.json` explicitly assumes synchronous entry through a class proxy, no
incoming transaction, and manager suspend/savepoint capabilities. These premises
are scenario inputs, not source-proven driver/runtime facts. `context-unknown.json`
withdraws savepoint support evidence; the expected result becomes UNKNOWN.

The concrete A/B beans exercise shared REQUIRED, independent REQUIRES_NEW,
NESTED/savepoint, no-transaction entry, inherited nonannotated execution,
self-invocation bypass and unmodeled SUPPORTS. C/intermediate and extra methods
supply class-default precedence, visibility, async, control-flow, repeated-call
and reflective uncertainty negatives without a full application or runtime probe.
