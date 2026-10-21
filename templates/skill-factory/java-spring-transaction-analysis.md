---
name: java-spring-transaction-analysis
version: 0.2.0
description: Untrusted candidate for bounded Java/Spring T01 static transaction scenarios and PlantUML scopes; explicit invocation and context required.
compatibility:
  - codex
  - claude
  - junie
  - opencode
preferred_runner: mana
allowed_tools:
  - read_files
  - code_search
inputs:
  - technology_evidence
  - explicit_transaction_analysis_request
  - java_sources
  - explicit_transaction_context
outputs:
  - transaction_model
  - transaction_sequence_plantuml
risk_level: high
model_tier: full
execution_mode: read
delegation_group: architecture
parallel_safe: true
owner_role: Architect / Team Leader
stack:
  - java
  - spring
tags:
  - candidate
  - transaction-analysis
---

# Java/Spring Transaction Analysis Candidate — T01

## Purpose
Describe the implemented bounded Transaction Boundary Engine. This generated
candidate remains untrusted, unregistered and non-executable. Generating or
validating it does not run analysis or approve/activate the skill.

## When To Use It
Review for an explicit Java/Spring transaction-analysis request after the existing
Maven/source technology gate succeeds. Before a separately authorized manual run,
read `docs/standards/transaction-model-v1.md` and supply an explicit scenario context.
Do not treat Spring dependency presence as proof of AOP interception, transaction
manager capabilities, driver savepoints or runtime transaction identity.

## Outputs
On separate manual invocation, `scripts/mana-transaction.py` emits a validated
`mana.transaction-model/v1` model and `sequence.puml` in a fresh external directory.
The factory itself still emits only this skill candidate and its evidence manifest.

## Implemented Capabilities
- Parse Java ASTs using a fixed Mana JDK helper, without target compilation,
  attribution, class loading, annotation processing, build scripts or model calls.
- Resolve bounded zero-argument synchronous source call scenarios through concrete
  `@Autowired` fields, with explicit imports, stereotypes and class proxy config.
- Distinguish method execution, logical transaction scopes and symbolic physical
  transactions for REQUIRED, REQUIRES_NEW and conditional NESTED/savepoints.
- Preserve self-invocation bypass, unannotated inherited/no-transaction context,
  class/method annotation precedence and unresolved call/configuration evidence.
- Render labelled PlantUML regions, shared identities, savepoints and explicit
  suspension/resumption events. Validate model identity and lifetime invariants.

## Decision Rules
- Every physical ID is SYMBOLIC_SCENARIO; actual runtime identity and transaction
  outcome stay UNKNOWN. Entry state/proxy and manager capabilities are declared
  scenario assumptions, not runtime proof inferred from source.
- Unmodeled propagation, manager ambiguity, unknown prior context, AOP uncertainty,
  async, complex control flow, inheritance, dynamic/reflective/programmatic calls
  stop confident traversal and retain explicit UNKNOWN/UNSUPPORTED diagnostics.
- Candidate validation and model invariant validation are separate decisions;
  neither constitutes human approval or runtime qualification.

## Limits And Prerequisites
JDK `java`/`javac` are required for analysis. The local JDK determines accepted
Java syntax. Evidence reads reuse factory limits; AST extraction is capped at
64 Java files / 2 MiB, 60 seconds per tool call and a 4 MiB fact/result budget.
Only conventional Maven/direct Spring evidence is supported by technology gating.
Only annotation-driven class proxies, declared concrete DataSourceTransactionManager
beans, direct public zero-argument straight-line methods and conservative wiring
are positively modeled. Other proxy/dispatch/configuration forms stay UNKNOWN.
No full Spring context, dependency resolution, exception/rollback computation,
resources/locks or deadlock analysis is implemented. T02/T03 remain out of scope.

## Diagram Notation
PlantUML groups follow method nesting. Labels carry L/P/S/SP identities and
semantic kinds in addition to colors. Physical lifetime BEGIN/END and suspension
notes make overlapping retained lifetimes explicit; groups do not pretend that
overlapping physical/resource regions are ordinary lexical nested transactions.

## Verification Criteria
Use `tests/transaction-boundaries.py`, the eight independent fixture oracles,
negative controls and `tests/mana-skill-factory.py`. Check actual PlantUML syntax
and SVG rendering using a local jar; a skipped renderer check remains NOT RUN.
Retain source hashes, call-site locations, conditional assumptions and UNKNOWNs.

## Human Approval
Architect / Team Leader review is mandatory before registration or activation.
The factory has no promotion operation. The separate analysis CLI requires an
explicit human request; it does not consume candidate approval as authorization.
This file is a review artifact, not an executable Verification Skill spec.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Keep compact caveman
working notes and context budget discipline, preserving evidence and limits.
