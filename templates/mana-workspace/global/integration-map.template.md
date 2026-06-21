# Integration Map

## Inbound Integrations
| Source | Protocol | Endpoint/Event | Contract Owner |
|---|---|---|---|
| `{{source}}` | `{{protocol}}` | `{{endpoint_or_event}}` | `{{owner}}` |

## Outbound Integrations
| Target | Protocol | Endpoint/Event | Timeout | Retry | Idempotency |
|---|---|---|---|---|---|
| `{{target}}` | `{{protocol}}` | `{{endpoint_or_event}}` | `{{timeout}}` | `{{retry_policy}}` | `{{idempotency_policy}}` |

## Error Mapping
- `{{external_error}}` -> `{{internal_error}}`

