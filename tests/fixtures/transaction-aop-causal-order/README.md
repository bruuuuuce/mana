# MR01-F01 AOP and causal ordering oracles

`cases.json` contains 20 supplied IR cases with literal expected verdicts derived
from MR00 sections 2, 5, 6 and D3/D4, plus the existing v1 AOP premises. No engine,
composer, validator or renderer constructs these expectations. The test loader
only copies supplied inputs. O01–O44 and the R1/R4 receipts are unchanged.

A01–A03 and C01 reproduce the four exact payloads of the two R1 findings.
A04/A05/A06 and C02/C03/C05 provide the required nearby positive, legitimate
uncertainty and retained-information controls for each finding. Additional cases
exercise legacy D3, explicit UNKNOWN mode, a second unresolved call, and propagation
of lost body order through a child.
A12/A13 distinguish an impossible APPLIED alternative from a known final-method
PROXY bypass that legitimately preserves P1.

C06 is deliberately accepted: an empty synchronous F02 child can leave the
transaction context UNKNOWN while its body order is established; the subsequent
unannotated sibling inherits UNKNOWN. C07 differs in the relevant premise: the
child body is nonempty and NOT_ASSERTED, so the later sibling lacks an ordering
proof. Neither case infers a physical identity or a successful boundary from U.

Sources and spans are explicitly synthetic supplied premises, not independent
JDK parse results or runtime evidence. A11 uses an exact original v1 artifact.
Run `python3 tests/transaction-aop-causal-order.py -v` for 26 targeted checks.
