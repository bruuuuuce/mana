# Analysis Trajectory Guard — final TG07 architecture

```mermaid
flowchart TD
    A[Approved story and acceptance criteria] --> B[Host-owned Mission Contract]
    B --> C{MANA_ANALYSIS_TRAJECTORY_MODE}
    C -->|off, default| D[Existing Story Start v2 flow]
    C -->|shadow| E[Passive TG02 telemetry and TG03 Ledger]
    C -->|enforce, per-run opt-in| F[Passive TG02 telemetry and TG03 Ledger]
    E --> G[TG04 deterministic drift recommendation]
    G --> H[No control-flow change]
    F --> I[TG04 deterministic policy at a real host boundary]
    I -->|on track| J[Continue with zero checkpoint calls]
    I -->|deterministic stop or scope gate| K[Apply stop, synthesis, or owner review]
    I -->|checkpoint justified| L[TG05 compact checkpoint envelope]
    L --> M[Terra high: one primary call]
    M -->|structural failure only| N[At most one repair call]
    M -->|valid| O[Host validates closed response]
    N -->|valid| O
    N -->|invalid| P[Fail closed: owner review]
    O --> Q[One re-anchor, explicit scope proposal, stop, or review]
    H --> R[Compact trajectory evidence package]
    J --> R
    K --> R
    Q --> R
    R --> S[Discovery v2 → Scope Triage → Planner v2 → Scope Governor]
    D --> S
    S --> T[Atomic Story Start Scope v2 publication]

    U[Provider-internal reads, tools, delegation and reasoning] -. opaque .-> E
    U -. opaque .-> F
```

The dotted boundary is intentional: Mana does not reconstruct internal tool
activity from prose. Enforcement occurs only at provider invocation,
completion, explicit next-action, and final-synthesis boundaries exposed to
the host. The trajectory package supplies evidence provenance and unresolved
gaps; Story Start Scope v2 alone classifies implementation scope.
