# Service Knowledge Index

Use this file as a compact retrieval map. Keep it below 200 lines. Load only
the card groups relevant to the current analysis.

## Domains

| Domain | Stable Cards | Candidate Cards | Load When |
|---|---|---|---|
| service-behavior | `cards/` | `candidates/` | Tracing runtime behavior or ownership |
| integrations | `cards/` | `candidates/` | API, messaging, retry, timeout, or contract work |
| operations | `cards/` | `candidates/` | Configuration, deployment, incident, or performance work |
| tests | `cards/` | `candidates/` | Test selection, environment, fixture, or performance work |

## Retrieval Rules
- Read a card only when its domain and scope match the active question.
- Prefer stable cards. Candidate cards are hints, not facts.
- Revalidate cards when their invalidation signals are touched.
