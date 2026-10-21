---
name: specialist-skill-factory
version: 0.1.0
description: Generate and validate an untrusted specialist skill candidate from project technology evidence; initial domain is Java/Spring via Maven.
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
  - repository
  - specialist_request
  - external_candidate_directory
outputs:
  - specialist_skill_candidate
  - technology_evidence
risk_level: medium
model_tier: full
execution_mode: write
delegation_group: architecture
parallel_safe: false
owner_role: Architect / Team Leader
stack:
  - java
  - spring
tags:
  - skill-factory
  - candidate-generation
---

# Specialist Skill Factory

## Purpose
Turn verifiable technology declarations into a reviewable candidate using the
deterministic helper `scripts/mana-skill-factory.py`. Generation writes only to
an explicit candidate directory outside the analyzed project.

## When To Use It
An explicit transaction-analysis request for a Java/Spring Maven project needs a
specialist contract. Bounded T01 analysis is a separate explicit invocation;
generation and candidate validation never run it.

## Outputs
A candidate bundle containing `SKILL.md` and `candidate.json`, with source hashes,
supported technologies, current and future capabilities, usable evidence,
applicability, required tools, limits, verification criteria and pending approval.

## Execution Logic
1. Read `docs/workflow/specialist-skill-factory.md` for the bounded supported path.
2. Run `python3 scripts/mana-skill-factory.py generate --project-root <project>
   --request transaction-analysis --candidate-dir <canonical-external-directory>`.
3. The helper inventories Java/Maven evidence, selects the curated specialist
   contract and tools, validates native Mana metadata and source provenance.
4. Present the exact bundle for human review. Do not register or activate it.
5. Revalidate with `validate --project-root <project> --candidate-dir <directory>`
   before review; changed evidence requires regeneration in a fresh directory.

## Decision Rules
- Unsupported or unproven technology blocks generation; no guessing from README text.
- Validation means compatible candidate structure, never trusted analysis.
- No model, build, plugin or repository script is needed for generation.
- Generated candidates stay outside `skills/`, profile lists and runner configuration.
- Human approval is required before future registration or activation. This
  version intentionally provides no approval or promotion operation.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Keep compact caveman
working notes and context budget discipline, retaining evidence and limits.
