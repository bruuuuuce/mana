# Integrated static transaction views

Read the sequence panels top to bottom, then the DB view for the named cut.
Open the application and mixed views separately. Panels for different participants
do not define a global execution order. All P identities are symbolic and scoped
to their participant. Source and SVG have identical basenames.

| Scenario | Sequence | DB cut | Mixed | Qualified result from S02 |
|---|---|---|---|---|
| A: inverse resource order | [a](A/sequence-a.svg), [b](A/sequence-b.svg) | [common](A/database-common.svg) | [common](A/mixed-common.svg) | CONDITIONAL_CYCLE_RISK; coverage INCOMPLETE |
| B: scoped exclusion | [a](B/sequence-a.svg), [b](B/sequence-b.svg) | [one_wait](B/database-one_wait.svg) | [one_wait](B/mixed-one_wait.svg) | NO_CYCLE_IN_MODELED_SCENARIO; coverage INCOMPLETE |
| C: REQUIRES_NEW | [a](C/sequence-a.svg) | [replacement](C/database-replacement.svg) | [replacement](C/mixed-replacement.svg) | CONDITIONAL_CROSS_LAYER_COMPLETION_RISK |

[Application C](C/application.svg) shows the synchronous frame completion
obligation; A and B have no qualified application edges. In C, P1 stays live but
suspended while independent P2 operates. The return/resume suffix is conditional,
and neither suspension nor END establishes commit or lock release.

B retains structural exclusion within its explicit cut **and** residual unknown
facts. This is neither missing-evidence-as-safety nor universal deadlock freedom.
No example represents an observed lock, runtime wait or confirmed deadlock.

Original read-only inputs: `../transaction-01-t02-s02/{A,B,C}`. Each scenario's
`evidence.json` retains the full validated S02 report and all input digests,
claim IDs, premises, source evidence and typed-relation references. The source
models are referenced rather than rewritten. Use the CLI and rendering commands
in [the contract](../../standards/transaction-visualization-v1.md) to reproduce.
