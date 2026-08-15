# M06 pilot utility-evidence audit

## Existing mechanisms assessed

| Mechanism | Existing purpose | Reused? | Why |
|---|---|---:|---|
| Runtime events | Operational audit of an executed profile | No | The envelope deliberately omits human review outcomes and must not become telemetry. |
| Behavioural evals | Deterministic framework fixtures | No | Eval results prove governed-plan structure, not whether a human found a finding useful. |
| Governance report | Local inventory and eval coverage | No | Its counts are framework coverage, not pilot dispositions. |
| Delivery metrics / learning agent | Human-confirmed lifecycle metrics | Not directly | Their promotion and story-level semantics differ from a per-finding pilot disposition. |
| Run identities and PR artifacts | Stable local references | Yes | Pilot feedback records opaque run/finding references supplied from those artifacts without copying content. |

## Decision

Use the separate, opt-in `mana pilot-feedback` command. It writes narrowly
validated, local JSON records below `.mana/pilot-feedback/` and produces only
aggregate JSON, CSV, or Markdown. It neither changes runtime/eval/governance
contracts nor invokes a model or network service.

Raw data includes opaque references, workflow name, human disposition, two
outcome questions, category, bounded one-line note, timestamp, and capture
metadata. Aggregates intentionally omit raw references and notes. The command
does not infer unrecorded feedback, saved time, ROI, correctness, or individual
performance.
