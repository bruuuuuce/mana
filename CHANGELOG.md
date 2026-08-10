# Changelog

## Unreleased

## 0.4.0 - 2026-08-10
- Added an optional, read-only User Context Layer with bounded materialization,
  project-local mirrors, explicit precedence, and diagnostics.
- Added deterministic Verification Skills and `mana verify`, with strict
  machine-readable contracts on normal skills, fixed adapters, bounded
  structured evidence, explicit trust/effects, source-mutation detection, and
  zero model calls. Initial skills cover changed shell syntax, bounded Mana
  governance evals, and approval-gated Java build/test evidence.
- Added provider-isolated, evidence-driven bounded repair with containment,
  mutation grants, host-side patch validation, and deterministic repair loops.
- Added governed cross-project User Learning capture, aggregation, synthesis,
  review, and promotion with explicit human approval gates.
- Added producer-owned Mana Learning Journey, concept, scout, expansion,
  rationale, Git history, and diagram contracts and commands; extracted the
  Flutter Learning Explorer into its own consumer repository.
- Preserved generated report wrappers when project bootstrap refreshes an
  existing Mana installation.

## 0.3.0 - 2026-07-26
- Added governed API and database test validation: approval-gated Newman API
  collections and PostgreSQL read-only verification catalogs for isolated targets.
- Added governed GUI test validation: redacted context discovery, approval-gated
  Playwright testbooks, isolated-target execution with trace/screenshot/video/JUnit
  evidence, and human-approved learning proposals.
- Added opt-in, read-only team-level historical calibration for story effort
  estimates. Mana now returns a base estimate first and requires explicit user
  approval before reading delivery history; individual productivity metrics are
  excluded.
- Added a generated skill routing index, conditional profile skill activation,
  and a compact runtime/output contract to reduce repeated model context.
- Added database, contract, and dependency-security activation eval fixtures
  for the conditional PR-review skill routing policy.
- Added progressive-load service knowledge capture with evidence-backed cards,
  candidate promotion gates, and a compact global retrieval index.
- Added provider-neutral testbook discovery and controlled local execution for
  unit, integration, and performance test candidates.
- Added Codex multi-agent orchestration support with Mana-managed
  `mana_explorer`, `mana_full_specialist`, and `mana_worker` custom agents.
- Changed Codex economy-first behavior so high-risk/full-tier work is delegated
  in the same run when subagents are available; `needs_model_escalation` remains
  as disabled/unsupported/failed/insufficient-delegation fallback.
- Added runner-neutral skill routing metadata validation for `model_tier`,
  `execution_mode`, `delegation_group`, and `parallel_safe`.
- Updated project bootstrap to install Mana custom agents while preserving
  target `.codex/config.toml` and unrelated custom agents.
- Added OpenCode project-scoped agent configuration and `--opencode` runner
  support using `mana_orchestrator`, `mana_explorer`, `mana_full_specialist`,
  and `mana_worker` with configurable `provider/model` overrides.
- Added project-scoped Claude Code runtime agents and runner model overrides so
  Claude follows the same bounded delegation model without modifying user-level
  Claude configuration.

- Initial Mana framework repository with skills, agents, profiles, workspace tooling, Jira MCP wrapper, project bootstrap, pre-commit development summary and knowledge-transfer artifacts, Jessica Fletcher pre-mortem agent, Application Manager readiness, architecture review, Team Leader planning, standardized agent/skill outputs with compact internal reasoning guidance, story-specific trace files and developer choice logs for Jira workspaces, diagnostics, GitHub templates, and end-to-end Codex flow documentation.
