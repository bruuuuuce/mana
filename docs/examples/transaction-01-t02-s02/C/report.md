# Conditional wait dependency scenario

CONDITIONAL_CROSS_LAYER_COMPLETION_RISK

Coverage: COMPLETE_MODELED_SCOPE. Runtime: NOT RUN. Global risk absence: NOT ASSERTED.

Inputs are referenced by exact-byte SHA-256; embedded T01 uses the documented canonical JSON digest.

## Application graph

```mermaid
%% Application completion graph
%% CONDITIONAL only. Arrows are waiter -> blocker (or caller -> callee).
flowchart LR
  N1["a/F1"]
  N2["a/F2"]
  N1 -->|"completion CONDITIONAL"| N2
```

## Cut replacement

CONDITIONAL_CROSS_LAYER_COMPLETION_RISK

```mermaid
%% DB graph: one common cut replacement
%% CONDITIONAL only. Arrows are waiter -> blocker (or caller -> callee).
flowchart LR
  N1["a/P1"]
  N2["a/P2"]
  N2 -->|"X CONDITIONAL cut=replacement"| N1
```


## Obligations

- W1 / replacement: a2 -> a1 — QUALIFIED
  - W1 MODEL_EVIDENCE: Distinct identified P; live at cut; waiter current and unsuspended. Premises:
  - W2 EXPLICIT_ASSUMPTION: Common database, effective datasource and JDBC enlistment explicitly assumed. Premises: a2_binding, a1_binding
  - W3 EXPLICIT_ASSUMPTION: Object and opaque lock target overlap are separate explicit premises; granularity remains bounded/UNKNOWN. Premises: X_database, X_object, X_overlap
  - W4 EXPLICIT_ASSUMPTION: Waiter request, prior holder acquisition and retention have separate provenance. Premises: a2_request, a1_request, a1_acquire, a1_retain
  - W5 EXPLICIT_ASSUMPTION: Versioned abstract incompatible modes and blocking (not NOWAIT/skip/retry). Premises: blocking
  - W6 EXPLICIT_ASSUMPTION: Pending waiter at invocation; holder acquisition precedes cut and is retained, not inferred from L/SP/S. Premises: a1_retain
  - W7 EXPLICIT_ASSUMPTION: Common explicit prefix cut with concurrent independent instances or live suspended outer/replacement. Premises: outer
  - W8 MODEL_EVIDENCE: Jointly compatible prefixes; no continuation beyond pending returns or unresolved frontiers. Premises:

## Coverage and limits

- Conditional static scenario only; execution, locks and waits are not observed.
- Opaque targets and abstract compatibility are explicit scenario assumptions.
- No JDBC wiring, SQL target resolution, runtime adapter or schedule enumeration.
- NO_CYCLE_IN_MODELED_SCENARIO applies only to the modeled scope and cut(s).
- No conclusion of general risk absence, deadlock freedom, commit or rollback.
- Input digests establish byte identity, not external source authenticity.

## Typed cross-layer links

```mermaid
%% Typed cross-layer relations; these are not DB wait edges
flowchart LR
  N1["frame a/F1"]
  N2["P a/P1"]
  N1 -. EXECUTES_IN .-> N2
  N3["frame a/F2"]
  N4["P a/P2"]
  N3 -. EXECUTES_IN .-> N4
  N2 -. SUSPENDS_FOR .-> N4
  N2 -. RESUME_REQUIRES_COMPLETION .-> N4
```

