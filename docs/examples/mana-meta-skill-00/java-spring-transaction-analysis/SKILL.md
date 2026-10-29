---
name: java-spring-transaction-analysis
version: 0.1.0
description: Candidate future contract for Java/Spring transaction analysis; analyzers are not implemented and execution is blocked.
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
  - spring_configuration
outputs:
  - transaction_analysis_contract
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

# Java/Spring Transaction Analysis Candidate

## Purpose
Provide a reviewable future contract for TRANSACTION-01. This generated candidate
is untrusted, unregistered and non-executable. No analyzer is implemented.

## When To Use It
Review when an explicit transaction-analysis request matches Java sources and
direct Spring dependency declarations in the same conventional Maven module.
Source/dependency presence does not prove transaction usage, resolved versions,
Spring proxy configuration, transaction-manager capabilities or runtime behavior.

## Outputs
Current output: this candidate contract and its evidence manifest only.
Future output: evidence-backed transaction findings, boundaries, uncertainty
records and a sequence diagram with overlapping transaction regions.

## Decision Rules
- Candidate validation is structural compatibility, never analysis qualification.
- Keep every future capability `not_implemented` until TRANSACTION-01 supplies
  implementation and verification evidence.
- Missing runtime dispatch, proxy, manager or configuration evidence stays unknown.
- Stop execution: human approval is pending and analyzers are unavailable.

## Supported Technologies And Applicability
Java and Spring declared through Maven direct dependencies. Gradle, inherited-only
dependencies, activated profiles and nonstandard source roots are unsupported in
this factory version. XML declarations are evidence of intent, not a resolved classpath.

## Future Analysis Contract
All items below are requested capabilities, not demonstrated analysis results:
1. Identify transactional methods with annotation/configuration provenance,
   including unresolved class-level, inherited and meta-annotation cases.
2. Model Spring propagation: REQUIRED, REQUIRES_NEW, NESTED, SUPPORTS,
   MANDATORY, NOT_SUPPORTED and NEVER, with explicit manager/configuration assumptions.
3. Distinguish reused transactions, independent transactions and nested savepoint
   regions. Do not infer savepoint support from Spring presence.
4. Identify entry, exit, suspension, resumption and uncertain transaction boundaries.
5. Produce sequence diagrams with overlapping regions: logical method scopes and
   physical transaction identity must remain distinct. A nested region must not
   imply an independent physical transaction. Diagram syntax/renderer is to be
   selected and verified in TRANSACTION-01.
6. Report unresolved static cases, including proxy/self-invocation, dynamic dispatch,
   multiple managers, async/reactive execution and missing configuration. Do not
   convert possible call edges into proven runtime execution or commit/rollback facts.

## Usable Evidence And Tools
Use source locations/hashes, direct dependency declarations, explicit project
configuration and separately approved runtime evidence. `read_files` and
`code_search` are existing Mana tool identifiers. The transaction analyzer is
`not_implemented`; there is no command, adapter or Verification Skill spec here.
No build scripts, Maven plugins, repository wrappers, LLMs or external services
are invoked by generation or validation.

## Verification Criteria
Recompute evidence hashes; run the existing Mana skill validator in isolation;
reject changed/extra candidate fields, content, tools or artifacts; retain
generated trust, pending human approval and non-executable state. Future analysis
needs independent positive and negative cases for every claimed propagation and
diagram capability before its status can change.

## Human Approval
Architect / Team Leader must review evidence, applicability, tools, limitations
and exact candidate content before any registration or activation. This factory
has no approval, promotion or execution operation. Approval alone cannot supply
the missing analyzers. Use existing Mana governance and generated trust policy;
do not treat a learning-agent review as human authorization.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Maintain compact caveman
working notes and context budget discipline; preserve evidence references and
unknowns without publishing private chain-of-thought.
