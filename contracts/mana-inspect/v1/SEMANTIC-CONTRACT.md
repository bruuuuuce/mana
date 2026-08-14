# Mana inspect semantic read contract v1

This document defines optional v1 CLI operations. Producers advertise the
operations they implement, and consumers negotiate them from
`project.operations` before calling them.

```text
mana inspect work-items --json
mana inspect work-item <work-item-id> --json
mana inspect project-context --json
mana inspect activity --json
```

`work-item` requires exactly one non-empty `feature:<workspace-id>` or
`session:<workspace-id>` ID; the other three take no positional argument.
`--json` is required.

| Operation | Schema | Meaning |
| --- | --- | --- |
| `work-items` | `mana.inspect.work-items/v1` | Compact work-item navigation list. |
| `work-item <id>` | `mana.inspect.work-item/v1` | One work item, stable sections, typed attention. |
| `project-context` | `mana.inspect.project-context/v1` | Typed global Mana context. |
| `activity` | `mana.inspect.activity/v1` | Conservative chronological semantic events. |

## Identity, uncertainty, and time

IDs derive only from owned workspace identity: `.mana/features/<workspace-id>`
maps to `feature:<workspace-id>` and `.mana/sessions/<workspace-id>` to
`session:<workspace-id>`. Ticket, title, purpose, branch, and canonical branch
are separate fields. A title rename never changes an ID. Future types are
`unknown`, never coerced to `feature`.

Nullable display fields carry provenance. Lifecycle is bounded to
`not_started`, `in_progress`, `completed`, `blocked`, `failed`, `stale`, and
`unknown`, with provenance and coverage. Producers never claim completion
without explicit canonical evidence. Missing optional files are not blockers.

Activity time is either an explicit domain timestamp or explicitly named
`filesystem_mtime_epoch`; mtime only supports the honestly named
`artifact_updated` fallback, never a meaningful-domain-event claim.

Each work-list entry includes typed `attention_items` for project-level
attention and a conservative `review` state. Review is `unknown` unless an
exact structured canonical source supplies its bounded state. Every artifact
reference identifies its owning work item and semantic section (or uses `null`
for project-global context), so consumers can open it without rediscovering
ownership from paths.

## Source-to-field mapping

| Semantic field | Source | Mapping class |
| --- | --- | --- |
| ID/type | workspace path and exact manifest identity | explicit structured source |
| ticket, purpose, branch, canonical branch | exact manifest keys | explicit structured source |
| title | no current canonical key | unavailable/unknown |
| lifecycle/sections | documented directories and structured result status | canonical path/category |
| pending decision | exact documented table headers/status values | conservative fallback |
| failed/stale evidence | known structured evidence fields | explicit structured source |
| review/PR state | exact canonical structured status field | explicit structured source |
| global categories | `.mana/global/` canonical named files | canonical path/category |
| activity | structured timestamps; mtime only as artifact update | explicit structured source / conservative fallback |
| PR state, owner action, prose summaries | no canonical structured source | unavailable/unknown |

Mana alone maps sources to semantic fields. Consumers render supplied responses
and references; they must not scan `.mana/`, parse arbitrary prose, or use
lexical inference to reconstruct missing semantics.
