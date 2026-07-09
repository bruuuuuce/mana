# Technical Task Breakdown — PROJ-301 Notification retry

## Task 1: Add bounded retry to NotificationSender

- Scope: retry transient failures up to a configured maximum with exponential
  backoff; permanent failures fail fast.
- Files: `src/notification/NotificationSender.java`,
  `src/notification/NotificationConfig.java`.
- Tests: unit tests covering retry-then-success, retry exhaustion, permanent
  failure fast-path, and backoff timing bounds.
- Definition of done: all listed tests exist and pass; no changes outside the
  impact map.
