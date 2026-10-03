# ADR: M08 opt-in review scheduler host

## Status

Accepted for M08-E. The scheduler is optional and disabled until a user-level
configuration is explicitly enabled. Familiar is a controller and viewer; it
is not the process host.

## Host and lifecycle

Mana provides one user-level scheduler CLI and persistent state machine. The
ordinary CLI remains usable without it. `mana review-inbox service --json`
runs the optional foreground host on macOS, Windows, and XDG platforms; it
re-reads configuration before every cycle, observes the configured interval,
continues after bounded offline failures, and stops cleanly on INT or TERM.
It owns no credentials and runs independently of Familiar.

An administrator or user may register that same foreground command with
`launchd`, Task Scheduler, systemd, or another process manager. Registration
and removal remain explicit host actions and are not performed by project
bootstrap, Inspect, or Familiar. This keeps service installation policy out of
the framework while providing the cross-platform service process required by
the scheduler contract.

Each cycle acquires one user-state lock, reads bounded GitHub discovery, commits
idempotent work, and exits. The foreground host holds no lock while waiting, so
Familiar and ordinary CLI reads remain available. A missed or crashed cycle is
recovered by the next cycle, whether invoked by the foreground host or directly
by an OS scheduler.

Configuration admits an explicit bounded list of exact `owner/name`
repositories and/or exact organizations. Discovery stores one external-state
cursor per configured repository or organization in the same transaction as
the admitted inbox identities. Later live queries use the cursor inclusively;
idempotency absorbs the boundary item. A failed or malformed discovery does
not advance any cursor.

## State and credentials

State is a versioned SQLite database under the user state directory:

- `$MANA_USER_STATE_HOME/review-scheduler/` when explicitly set;
- `${XDG_STATE_HOME:-$HOME/.local/state}/mana/review-scheduler/` on XDG;
- the equivalent platform-local application state root on Windows.

The database stores configuration, bounded PR identity/metadata, cursors, run
state, draft finding references, and receipts. It never stores credentials,
full diffs, unrestricted comments, provider prompts/responses, or GitHub tokens.
Authentication remains owned by the selected `gh`/provider environment.

## Identity and concurrency

Work identity is SHA-256 over repository identity, PR number, head SHA,
requested reviewer identity, requested-pr-review profile revision, and admitted
context revision. An unchanged identity is never analysed twice. A new head,
profile, or context revision makes prior results stale and creates distinct
work.

One host lock protects discovery and state transitions. SQLite transactions
prevent two scheduler processes or Familiar windows from claiming the same
run. A running claim has a lease and attempt ID; recovery changes an expired
claim to `interrupted`, never directly to success.

## Policies and external effects

`notify-only`, `analyse`, and `publish-selected-draft` are separate policies.
Notify-only performs no provider call. Analyse invokes the governed
`requested-pr-review` profile for one explicit PR revision and stores only
structured status plus local draft findings. It never publishes.

Publication is a distinct action naming the current repository, PR number,
head SHA, and exact draft revision. An unknown transport result remains
`publication_unknown`; retry requires a human decision. Tests use a fake
boundary. A live pilot requires a dedicated repository and separate explicit
authorization.

## Offline, upgrades, and disable/uninstall

Network or authentication failure records a bounded retryable diagnostic and
does not advance the discovery cursor. Database schema upgrades require an
explicit maintenance command and a backup; incompatible state is reported and
left untouched. Disabling configuration prevents new discovery and claims but
causes the foreground host to exit while retaining inspectable state. Uninstall
stops/removes only the user-configured process-manager entry. A separate
explicit purge removes validated scheduler state; projects and credentials are
never deleted.
