# Learning Loop

Post-merge incidents, recurring bugs, review comments, and flaky tests feed known pitfalls, rule updates, and skill improvements.

## Operating Principles
- Skills are atomic and reusable.
- Agents orchestrate skills and produce phase artifacts.
- MCP access is governed, audited, redacted, and least-privilege.
- Humans remain accountable for clarity, design, implementation, approval, and correctness.
- AI reduces churn by surfacing gaps early and preserving evidence.

```mermaid
flowchart LR
    Requirements --> Planning --> Development --> Validation --> Review --> Learning
```

## Measurement
The loop is only closed when evidence is checked against outcomes. Follow
`docs/standards/delivery-metrics-standard.md`: record story rework, finding
hit/miss, and open-question answer events in the feature workspace as they
happen, and let `learning-agent` aggregate them into
`.mana/global/metrics/delivery-metrics.md` at its trigger points. The miss
list is the tuning backlog for skills; the false-positive share tells you
which skills produce review load instead of removing it.

## Practical Use
Use the related profiles and templates to create repeatable artifacts. Fill each artifact with project-specific evidence and route blockers to the accountable owner.
