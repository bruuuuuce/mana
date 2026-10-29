# T01-F01 self-invocation oracles

The three parse-only projects differ solely in transaction interception configuration:
PROXY, ASPECTJ, and absent/UNKNOWN. They are never built or executed. The eight
expectations in `oracles.json` are manually specified from the source calls and
Spring's proxy/weaving rules; the analyzer does not generate expectations.

The active child cases obtain P1 from an intercepted caller in the same trace;
they do not invent an external runtime transaction identity. PROXY self-calls
retain the incoming context even when their annotations declare REQUIRES_NEW.

AspectJ positive cases explicitly stipulate `aspectjWeaving: ASSUMED_APPLIED`.
They test what follows **if transactional weaving applies** to the modeled methods.
They do not demonstrate a working weaver, classpath or running Spring application.
The source annotation alone leaves weaving UNKNOWN. Even an assumed weaver cannot
resolve a missing interception mode. This follows the permitted conditional
scenario contract; runtime weaving evidence remains outside T01.

Run `python3 tests/transaction-self-invocation.py -v`. The original sixteen tests
remain in `tests/transaction-boundaries.py`. Set `MANA_PLANTUML_JAR` to a local jar
for syntax/SVG qualification. Missing tooling is a skip/NOT RUN, never a PASS.
