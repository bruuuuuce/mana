# Service Knowledge Policy

## Purpose
Keep durable service knowledge useful, evidence-backed, and cheap to retrieve.
It complements the Service Context Layer; it does not replace source code,
tests, Jira, ADRs, incident records, or human ownership.

## Layout
```text
.mana/global/knowledge/
  index.md
  cards/
  candidates/
```

`index.md` is a retrieval map, not a repository summary. Stable cards belong in
`cards/`. Proposed or insufficiently supported cards belong in `candidates/`.

## Card Requirements
Every card must use the template and declare:

- `id`, `scope`, `kind`, `confidence`, and `promotion_state`;
- at least one evidence reference;
- `last_verified` date or explicit `unknown`;
- owner or owner role;
- invalidation signals, such as changed files, config, contract, or release.

`kind` values: `observed`, `inferred`, `decision`, `unknown`.
`promotion_state` values: `candidate`, `stable`, `superseded`, `retired`.

## Promotion Rules
1. Agents may create or update candidate cards from evidence.
2. A stable card requires explicit owner approval recorded in the card.
3. Architecture, security, database, production, and cross-service cards need
   approval by the accountable specialist owner.
4. Inferred claims remain candidates until confirmed. Unknowns are valid cards
   when they prevent unsafe assumptions.
5. Superseded or retired cards stay short and point to their replacement.

## Retrieval And Token Budget
- Read `index.md` first, then only domain-relevant cards.
- Keep the index below 200 lines and cards below 80 lines.
- Store references and short statements, never raw logs, full diffs, copied Jira
  payloads, credentials, customer data, or private chain-of-thought.
- Revalidate a card when its invalidation signals are touched or its evidence is
  older than the team-defined review period.

## Relationship With Existing Context
- Put non-negotiable rules in `engineering-guards.md`.
- Put approved broad architecture in `architecture.md` and integrations in
  `integration-map.md`.
- Put recurring failure patterns in `known-pitfalls/`.
- Put granular, evidence-backed service behavior and open constraints in
  `knowledge/`.
