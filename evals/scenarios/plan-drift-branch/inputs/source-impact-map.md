# Source Impact Map — PROJ-301 Notification retry

## Probably Modify

- `src/notification/NotificationSender.java` — add bounded retry on transient
  send failures.
- `src/notification/NotificationConfig.java` — retry attempts and backoff
  configuration.

## Inspect Before Deciding

- `src/notification/NotificationQueue.java` — confirm redelivery semantics do
  not duplicate retries.

## Avoid Unless Approved

- `src/payment/**` — protected area, payment owner approval required.
- Database changelogs — no schema change is in scope for this story.
