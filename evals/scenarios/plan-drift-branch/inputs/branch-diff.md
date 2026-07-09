# Branch Diff Evidence — feature/PROJ-301-notification-retry

Changed files against `develop`:

| File | Change |
|---|---|
| `src/notification/NotificationSender.java` | Added retry loop with backoff for transient failures; new `isTransient(Exception)` branch |
| `src/notification/NotificationConfig.java` | Added `maxRetryAttempts` and `retryBackoffMillis` properties |
| `src/payment/FeeCalculator.java` | Changed `INTERNATIONAL_FEE_RATE` from `0.025` to `0.02` |
| `src/notification/NotificationSenderTest.java` | Added test `retriesTransientFailureThenSucceeds` |

Notes:

- No test covers retry exhaustion, the permanent-failure fast path, or backoff
  bounds.
- No planning artifact, story text, or commit message references the
  `FeeCalculator` change.
