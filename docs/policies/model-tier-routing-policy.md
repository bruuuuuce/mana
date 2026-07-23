# Model Tier Routing Policy

## Purpose
Keep Mana model routing provider-neutral while giving runners a clear rule for
when an economy model is sufficient and when a stronger model or human
escalation is required.

Mana skills, agents, and profiles declare abstract capability needs. They must
not name provider-specific models such as GPT, Claude, or OpenCode model IDs.
Concrete model mapping belongs to the runner configuration.

## Provider-Neutral Metadata
Use existing front matter fields before adding new routing knobs:

```yaml
model_tier: economy | full
risk_level: low | medium | high
execution_mode: read | write
```

`model_tier` expresses the expected reasoning capability. `risk_level`
expresses impact if the result is wrong. `execution_mode` expresses whether the
workflow may modify external systems, source files, tickets, PRs, or releases.

## Tier Semantics
`economy` is appropriate for:

- read-only evidence collection;
- parsing and normalizing Jira, Git, GitHub, logs, or local artifacts;
- deterministic checklist application;
- low-risk summarization where source evidence is cited;
- artifact formatting after another step produced the judgment.

`full` is required for:

- architecture, security, database, concurrency, transaction, or production
  behavior judgment;
- cross-service compatibility or contract analysis;
- large, noisy, or ambiguous diffs;
- high-impact release, rollback, incident, or compliance decisions;
- cases where incomplete evidence requires deciding what cannot safely be
  inferred.

## Routing Rules
1. `model_tier: economy`, `risk_level: low`, and `execution_mode: read` may run
   on the configured economy model.
2. `risk_level: medium` may start on economy, but the runner must preserve
   evidence gaps and ambiguity instead of forcing a confident conclusion.
3. `model_tier: full` or `risk_level: high` makes the skill an escalation
   candidate for the configured full model.
4. `execution_mode: write` requires an explicit profile permission and must not
   be inferred from filesystem or tool access.
5. If subagents or full-model routing are unavailable, the root economy model
   may inventory evidence but must stop with `needs_model_escalation` before
   deep high-risk judgment.
6. If the evidence is ambiguous, contradictory, or missing required access, the
   runner must return `ambiguous`, `blocked`, or `needs_model_escalation` rather
   than inventing a verdict.

## Provider Mapping
The mapping from abstract tiers to concrete models is configured at runtime:

```yaml
codex:
  economy: MANA_CODEX_MODEL
  full: MANA_CODEX_FULL_MODEL
claude:
  economy: MANA_CLAUDE_MODEL
  full: MANA_CLAUDE_FULL_MODEL
opencode:
  economy: MANA_OPENCODE_MODEL
  full: MANA_OPENCODE_FULL_MODEL
```

The default model IDs may change over time. This policy should not be updated
just because a provider releases a new model.

## Jira And Tool Access
Jira is not a model tier. Treat it as a read/write capability with independent
access and risk controls:

- `jira_read` may provide requirement, workflow, and release evidence.
- Jira writes, comments, or transitions require explicit human approval.
- Missing Jira access is an evidence gap, not a reason to guess.
- For read-only audits, a model may continue with local Git/GitHub evidence only
  if the output clearly marks Jira evidence as unavailable.

## Warning Behavior
When a selected profile includes `model_tier: full` or `risk_level: high`
skills, the runner should warn that the root economy model is for routing and
evidence inventory only. The warning should be non-blocking when full-model
delegation is available and blocking only when the profile requires high-risk
judgment but no escalation path exists.
