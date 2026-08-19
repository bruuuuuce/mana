# Analysis Trajectory Guard — Passive Telemetry (TG02)

TG02 provides a versioned, opt-in sidecar for facts Mana can observe while running Story Start Scope v2. It does not alter planning, scope governance, provider routing, or failure handling.

Enable it only for diagnostic/pilot runs:

```text
MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true
MANA_STORY_START_SCOPE_VERSION=v2
MANA_STORY_START_CONTEXT=<project-relative-package>
```

When enabled, the active Story Start workspace contains `evidence/analysis-trajectory-events-v1.jsonl` (append-only events) and `validation/analysis-trajectory-summary-v1.json` (the deterministic derived summary). The contracts are `mana.analysis-trajectory.event/v1` and `mana.analysis-trajectory.run-summary/v1` under `contracts/analysis-trajectory`.

The sidecar records host-owned sequence IDs, sanitized correlation IDs, provider/model/effort route, host boundary, bounded reference arrays, outcome, and empty budget counters. It never stores prompts, provider responses, chain-of-thought, source content, credentials, ticket text, or token values that the host cannot observe.

Observable boundaries are the v2 Discovery, Scope Triage, Planner, and (if used) single correction provider invocations; host compact-planning-context synthesis; and publication/failure. Provider-internal reads, searches, tool retries, delegation, and context expansion remain opaque and are not synthesized into events.

The zero-token summary derives provider iterations, visited/repeated scopes, longest no-evidence sequence, evidence per completed iteration, expansion/decision observations, routes, terminal status, and checkpoint count. Checkpoints are always zero in TG02. Missing provider usage is represented by `tokenUsage.available: false`, never invented.

Telemetry defaults to disabled. Disabled runs create no sidecar files and retain the same runtime path. Enabled telemetry is best effort and never blocks, redirects, retries, re-anchors, or makes a provider call; it adds only local JSON serialization overhead. TG02 deliberately introduces no Mission Contract, Trajectory Ledger, drift labels, checkpoint policy, scope-expansion approval, or enforcement.
