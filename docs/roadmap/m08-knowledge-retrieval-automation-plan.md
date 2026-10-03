# M08 Knowledge, Retrieval, and Review Automation Plan

## Status

Proposed implementation plan. This document defines phase boundaries, contract
work, evidence gates, and delivery order. It does not authorize a runtime
default change, a new background service, model calls, external writes, or a
Mana Familiar implementation by itself.

M08 follows the accepted Mana Inspect v1 read-model boundary. Mana remains the
semantic producer and owner of validation, persistence, retrieval, governance,
and automation. Mana Familiar remains a client of versioned contracts and owns
presentation, navigation, and local UI preferences.

## Problem Statement

The current product has four related gaps:

1. Multiple Inspect operations can independently rebuild the same catalog.
   Each rebuild walks `.mana`, hashes and stats every file, and classifies its
   contents. A large workspace therefore pays repeated producer cost while a
   project is opening or refreshing.
2. Mana has bounded targeted retrieval and compact hand-maintained knowledge
   indexes, but no shared, ranked, passage-level index covering framework,
   user, and project knowledge with explicit provenance.
3. Project learning candidates and cross-project User Learning have governed
   lifecycles, but a client cannot yet present one evidence-first review queue
   through stable read and action contracts.
4. The `requested-pr-review` profile can analyse an explicit pull request or
   discover requested reviews during an invoked run, but Mana has no
   host-owned, persistent, opt-in review inbox and polling lifecycle.

These gaps should be solved as one roadmap because they share identity,
provenance, freshness, budgeting, and client-contract concerns. They must not
be implemented as one indivisible release.

## Outcomes

M08 should deliver the following outcomes in order:

- one producer scan per semantic snapshot instead of one scan per surface;
- a measured Familiar startup path that remains responsive with large artifact
  inventories and makes no eager request for data outside the visible route;
- a derived, rebuildable, local knowledge index with explicit freshness;
- bounded lexical retrieval that selects passages rather than loading whole
  knowledge bases;
- versioned Knowledge and Learning contracts consumable by Familiar and other
  clients;
- explicit, optimistic-concurrency actions for editable knowledge and learning
  dispositions;
- an opt-in PR review inbox whose analysis runs without Familiar being open;
- evidence deciding whether semantic retrieval adds enough value to justify
  embeddings and their operational cost.

## Non-Goals

M08 does not initially provide:

- a vector database, embedding service, or model-backed retrieval dependency;
- automatic promotion of learning candidates into governed knowledge;
- automatic publication of PR comments, approvals, merges, or CI actions;
- client-side parsing or direct writes to `.mana` or User Context sources;
- a combined authority model that erases framework, user, project, repository,
  candidate, and generated-source distinctions;
- indexing of credentials, unrestricted logs, binary data, or arbitrary files
  outside declared source roots;
- a hidden cache write performed by existing read-only `mana inspect` commands;
- a daemon as a prerequisite for ordinary CLI or Familiar use.

## Source and Authority Model

Every indexed or returned passage must preserve one source scope:

| Scope | Initial source | Authority and write rule |
|---|---|---|
| `framework` | Reviewed Mana framework knowledge and concept sources explicitly admitted by the index contract | Distributed with Mana and read-only to a linked project. Changes occur through the Mana repository release process. |
| `user` | Healthy generated `.mana/user-context/` mirror | Advisory and potentially stale. The mirror is never edited; an explicit action targets the configured external source, then refreshes the mirror. |
| `project` | Declared Service Context, knowledge cards, decisions, policies, and Learning Journeys in the selected project | Project-owned. Writes require a dedicated validated action, revision precondition, and project policy checks. |
| `candidate` | Project Learning candidates and external User Context candidates exposed through dedicated adapters | Proposal only. Search results must identify candidate status and must not present a candidate as active guidance. |

Repository evidence remains outside the Knowledge index unless a later
contract explicitly admits it. For project claims, the established precedence
remains repository evidence, then project/service context, then user context.
Framework operational rules and current human instructions retain their own
authority and must not depend on search ranking to be applied.

## Target Architecture

```text
Canonical and governed sources
  framework | user mirror | project context | candidates
                         |
                         v
              Mana source adapters
       containment, policy, schema, revision
                         |
            +------------+-------------+
            |                          |
            v                          v
  semantic snapshot builder    derived knowledge index
  one catalog inventory        documents + passages + FTS
            |                          |
            +------------+-------------+
                         |
              versioned read contracts
       project / work / knowledge / learning / review
                         |
            +------------+-------------+
            |            |             |
         Familiar      Mana CLI    review automation
```

Canonical files remain authoritative. The index is a disposable projection;
it cannot grant authority, approvals, freshness, or write permission.

## Delivery Order

| Order | Work package | Can ship independently | Required predecessor |
|---|---|---:|---|
| M08-A | Baseline and single-scan semantic snapshot | Yes | Current Inspect v1 |
| C04 | Familiar large-project startup and refresh performance | Cross-repository; baseline can start immediately | Current Familiar; aggregate optimization completes after M08-A |
| M08-B | Derived incremental catalog | Yes | M08-A measurements and identity decisions |
| M08-C | Lexical knowledge index and retrieval contracts | Yes | M08-B |
| M08-D | Knowledge and Learning read/action contracts | Yes, read before write | M08-C for search; existing learning commands for dispositions |
| C05 | Familiar Knowledge and Learning client | Cross-repository | Corresponding M08-D contracts |
| M08-E | Opt-in PR review inbox and scheduler | Yes | Stable identity/state conventions; retrieval is optional until proven |
| C06 | Familiar PR Inbox client | Cross-repository | M08-E read/action contracts |
| M08-F | Semantic retrieval experiment | Optional | M08-C lexical baseline and evaluation corpus |

M08-E may begin after its state and identity review without waiting for
Knowledge editing. It must not make M08-C search a mandatory dependency until
evaluation demonstrates that retrieved knowledge improves review quality.

## M08-A: Baseline and Single-Scan Semantic Snapshot

### Objective

Remove repeated catalog reconstruction from one logical project read while
preserving current Inspect v1 results and read-only guarantees.

### Work

1. Add reproducible fixtures representing small, medium, and large `.mana`
   workspaces. Include many Markdown files, JSON/JSONL runtime artifacts,
   workspaces, Journey records, unknown files, and excluded/symlink cases.
2. Add a benchmark harness that reports cold and repeated timings, number of
   files and bytes admitted, digest work, process count, peak response bytes,
   and catalog-build count. Store no source content in benchmark summaries.
3. Measure the current `project`, `artifacts`, `work-items`,
   `project-context`, and `activity` sequence separately and as the sequence
   used by Familiar. Record the linked-project prerequisites before accepting
   any Phoenix measurement.
4. Extract catalog construction into one reusable in-process or single-process
   inventory object. All semantic projections in one invocation must consume
   the same immutable inventory.
5. Define a versioned semantic-snapshot operation, or an equivalent versioned
   aggregate, that returns the initial client surfaces from one inventory.
   The contract must keep individual v1 operations supported.
6. Update the consumer handoff only after deterministic producer fixtures and
   schema validation pass.

### Gate A

- One aggregate request performs exactly one catalog build.
- Aggregate projections are semantically equivalent to the corresponding
  individual v1 operations for accepted fixtures.
- Existing v1 operations retain byte-stable output where their inputs and
  contracts are unchanged.
- No model, network call, project write, cache write, or background process is
  introduced.
- The benchmark records a baseline and improvement for the large fixture;
  timing thresholds are set from that evidence rather than invented upfront.
- Failure of an optional projection is represented explicitly and does not
  discard independently valid surfaces.

## C04: Mana Familiar Large-Project Startup and Refresh Performance

### Objective

Make the native window and initial Overview useful as early as possible, while
keeping expensive producer work, JSON decoding, catalog rendering, and
filesystem refresh outside the critical path. Prove the behavior on projects
with large artifact inventories rather than extrapolating from small fixtures.

This is a cross-repository gate. Mana owns producer timing and response shape;
Familiar owns process orchestration, decoding, read-model updates, Flutter
rendering, list virtualization, route-driven loading, and native startup UX.

### Existing Baseline and Gap

Familiar already has `test/performance_regression_test.dart`. It constructs a
2,400-artifact in-memory catalog, measures parsing and legacy inbox derivation,
checks lazy review-list construction, and renders large synthetic Work and
Activity models under a five-second test bound. Preserve this regression.

It is not the C04 acceptance gate: it does not launch Mana, read a large
workspace, measure process or transport time, exercise JSON decoding from a
real response, measure first meaningful Overview, observe native window
startup, or prove macOS/Windows profile/release behavior. C04 extends it with
the layers and fixture matrix below rather than treating its five-second bound
as a product startup target.

### Measured Milestones

The performance harness must record separate monotonic timestamps for:

1. process start to native window presented;
2. Flutter binding ready to first rendered application frame;
3. project selection to visible loading shell;
4. inspect process start, first byte, last byte, and exit;
5. JSON decode and typed read-model construction;
6. first meaningful Overview with project identity and work-item summaries;
7. visible route fully populated;
8. optional background surfaces settled;
9. filesystem event to refreshed visible route.

No single aggregate duration may hide which layer regressed. Test-only traces
contain durations, counts, schema names, and result sizes only; they must not
contain source content, absolute paths, credentials, prompts, or responses.

### Fixture Matrix

Create deterministic, generated cross-repository fixtures with at least these
logical inventories:

| Class | Artifacts | Work items | Runtime events | Knowledge documents | Purpose |
|---|---:|---:|---:|---:|---|
| small | 100 | 10 | 100 | 20 | Ordinary developer project and fast local regression. |
| medium | 1,000 | 100 | 5,000 | Expected large project and primary PR performance gate. |
| large | 10,000 | 500 | 50,000 | Stress the producer response, Dart decode, lists, filters, and refresh behavior. |
| hostile-large | 10,000 plus bounded malformed, unknown, symlink, and oversize entries | 500 | 50,000 | Prove that safety diagnostics and skipped inputs do not create unbounded work or UI stalls. |

Fixture generation must be deterministic from a seed, use synthetic content,
report its exact logical counts and bytes, and run without network or provider
calls. It must not copy customer or local project artifacts into the repository.

### Startup Work

1. Render the application chrome and a stable project loading shell before any
   Inspect response completes. Native project-window bookkeeping and recent
   project persistence must not wait for semantic loading.
2. Make the initial request route-driven. Overview requests only the minimum
   project identity, attention, and work summaries required above the fold.
   Knowledge, Activity, raw catalog, document detail, Human Feedback threads,
   Journey materialization, and review detail load only when visible or during
   an explicitly budgeted idle prefetch.
3. Consume the M08-A aggregate operation when advertised. Keep the existing v1
   sequence as a compatibility fallback and make the selected path observable
   in test traces.
4. Do not start optional producer operations immediately after the first frame
   if they compete with the current route for CPU, disk, or process slots.
   Schedule them after first meaningful content and cancel or reprioritize them
   when navigation changes.
5. Keep the raw artifact catalog absent from Overview memory and widget state.
   Load it only for Advanced/Artifacts, with paging or windowing before a full
   10,000-row response becomes part of one Flutter build.
6. Move large JSON decoding and typed projection off the UI isolate when a
   measured payload threshold shows frame loss. Preserve deterministic errors
   and cancellation when the project or route changes during decoding.
7. Avoid constructing hidden Knowledge/Journey subtrees during application
   startup. Their stores and futures should be created on route entry.
8. Preserve the last successfully rendered model during refresh. Update only
   the changed visible projection instead of replacing the entire Observatory
   tree when the contract permits it.
9. Add generation IDs and cancellation so a response from an older project,
   route, or refresh cannot update the current window.
10. Keep warm-start persistence out of the first implementation. A persisted
    last-good semantic snapshot may be considered only after a privacy and
    freshness ADR defines content limits, encryption/platform storage, schema
    invalidation, project identity, deletion, and an unmistakable stale state.

### Watcher and Refresh Work

1. Retain recursive `.mana` watching, but convert bursts into one revision
   check and one coalesced refresh. An event received during a refresh permits
   at most one follow-up pass for the resulting revision.
2. Ignore derived cache/index paths so index publication cannot trigger a
   refresh loop.
3. If Mana exposes a semantic revision or projection digest, skip producer and
   Flutter work when the visible projection is unchanged.
4. Refresh only surfaces affected by the changed producer revision where the
   contract supplies a reliable invalidation set. Without that contract, use
   the aggregate snapshot rather than issuing all independent operations.
5. Apply backpressure during sustained writes and show that data is updating;
   do not queue unbounded refresh futures or blank the last good UI.

### Test Layers

The Familiar repository should add four distinct performance layers:

- **orchestration tests:** fake process runner proves exact operation count,
  ordering, cancellation, lazy route loading, and refresh coalescing;
- **Dart performance tests:** decode and typed-model construction for generated
  aggregate responses, with response bytes and isolate behavior recorded;
- **Flutter performance tests:** frame/build timing, lazy widget construction,
  list windowing, filtering, navigation, and project switching for medium and
  large models;
- **native desktop tests:** real macOS and Windows application startup, first
  meaningful Overview, route changes, close/reopen, and refresh under a
  producer fixture. Widget tests do not claim this gate.

The medium fixture runs on every PR using deterministic operation and frame
budgets. The large and hostile-large suites run scheduled/manual and publish a
machine-readable performance report. A smaller smoke may run on every PR where
native runner time is constrained.

### Performance Budgets

Before optimizing, record at least five cold and five warm runs on each named
reference environment, including hardware, OS, build mode, Flutter version,
Mana revision, Familiar revision, fixture digest, and background-load policy.
Debug builds diagnose behavior but do not establish release latency budgets.

The initial release targets are:

- exactly one initial semantic producer request after capability negotiation
  when M08-A is available;
- zero raw-catalog, Activity, Journey, Human Feedback, or Knowledge-detail
  requests before first meaningful Overview;
- no frame over 50 ms between loading-shell presentation and first meaningful
  Overview in a profile/release build, excluding time blocked on producer I/O;
- no synchronous JSON decode on the UI isolate that exceeds 16 ms in the
  medium or large fixture;
- unchanged filesystem bursts produce at most one semantic check and no model
  replacement;
- warm medium-fixture first meaningful Overview targets 1 second and cold
  targets 2 seconds on the declared reference environment;
- cold large-fixture first meaningful Overview targets 3 seconds, with raw
  catalog and optional surfaces excluded from that milestone;
- opening and scrolling a 10,000-artifact Advanced catalog maintains bounded
  widget construction and no sustained UI jank.

If the first baseline shows a target is infeasible on the agreed reference
environment, changing it requires a recorded budget decision with the layer
responsible, measured evidence, and a follow-up target. Passing relative to a
slower baseline alone is insufficient for release.

### Gate C04

- The fixture matrix and reports are reproducible from committed generators.
- Producer, transport, decode, model, Flutter, and native timings are reported
  separately.
- Initial Overview performs only its declared minimum operations.
- Medium PR budgets pass in profile or release mode without network/model use.
- Large scheduled tests prove bounded memory, response size, widget count,
  refresh queue, and frame behavior.
- Navigating away, switching project, and closing the window cancel or safely
  ignore stale work.
- No optimization weakens schema validation, path containment, provenance,
  freshness, accessibility semantics, or the last-good-data behavior.
- The current native macOS and Windows gates remain distinct; success on one
  platform is not reported as success on the other.

## M08-B: Derived Incremental Catalog

### Objective

Avoid rehashing and reparsing unchanged inputs across invocations while keeping
the Inspect result derived, verifiable, and rebuildable.

### Storage Decision Gate

Before implementation, approve an ADR selecting the cache location. The
preferred starting point is a user-local cache outside the inspected project,
keyed by a non-secret project identity. This avoids changing the current
read-only project contract and prevents cache writes from triggering the
project `.mana` watcher. The ADR must cover macOS, Windows, XDG platforms,
cleanup, multi-window concurrency, project relocation, and privacy.

### Work

1. Define a versioned catalog database schema. SQLite is the default candidate
   because it provides transactions, locking, portability, and later FTS5 use.
2. Store only bounded metadata required to validate and reconstruct catalog
   entries: source identity, project-relative path, source scope, file type,
   size, content digest, revision identity, classification, and index schema.
3. Use safe traversal and regular-file checks before admission. Symlinks,
   escaping paths, special files, oversize inputs, and restricted sources stay
   rejected or safely diagnosed.
4. Make content digests authoritative for reuse. Filesystem metadata may select
   candidates for revalidation but cannot alone establish unchanged content or
   semantic identity.
5. Publish database updates transactionally under one host-owned lock. A
   crashed or incompatible build must leave the last verified database usable
   or mark it unavailable; it must not silently bless partial state.
6. Provide explicit maintenance commands such as `status`, `build`, `verify`,
   and `rebuild`. Existing read-only Inspect commands must not silently create
   or repair the database.
7. Report `current`, `stale`, `missing`, `invalid`, or `unsupported` freshness
   with bounded reasons. Fallback to a live scan must be explicit in the result
   and measurable.

### Gate B

- An unchanged second read performs no full-content reparse and no redundant
  digest work beyond the approved validation strategy.
- Add, modify, delete, rename, permission change, symlink replacement, and
  same-byte file-instance replacement cases have explicit tests.
- Concurrent builders cannot publish mixed or partial catalog state.
- Deleting the cache and rebuilding produces the same logical catalog.
- The database contains no credentials, unrestricted payloads, absolute source
  paths, prompts, responses, or model output.
- Older clients and projects without a cache remain supported.

## M08-C: Lexical Knowledge Index and Retrieval

### Objective

Retrieve a small, relevant, provenance-preserving set of passages without
loading complete knowledge bases.

### Work

1. Extend the derived database with document and passage projections plus an
   FTS5 index when the platform SQLite build supports it. Keep a validated
   fallback or report the capability unavailable; do not silently change
   ranking semantics between platforms.
2. Split supported text by declared structure, preferring Markdown headings
   and bounded paragraphs. Preserve stable document identity separately from
   passage revision identity.
3. Index title, heading path, bounded body text, scope, artifact identity,
   revision, lifecycle state, and provenance. Do not index excluded or
   restricted content merely because it is textual.
4. Define a versioned read-only search contract with query, source scopes,
   project identity, lifecycle filters, limit, maximum returned bytes, and
   index-freshness preconditions.
5. Rank lexical matches deterministically using documented FTS/BM25 settings,
   then apply explicit authority and lifecycle filters. Ranking never changes
   a source's authority.
6. Return bounded snippets, stable source references, passage revision,
   ranking reasons, freshness, and explicit gaps. Never return a generated
   answer from the retrieval command.
7. Allow progressive loading: metadata results first, selected passages next,
   and full document detail only through a separate bounded request.
8. Integrate controlled explorer retrieval only after parity tests show the new
   contract preserves source separation, cycle limits, and provenance.

### Gate C

- Search never loads or returns the entire corpus by default.
- Results remain isolated by requested scope and project.
- Stale, candidate, superseded, rejected, and active material are visibly
  distinct and filterable.
- Required governance rules are loaded through deterministic mechanisms and
  cannot disappear because BM25 ranked them poorly.
- A fixed corpus of at least 30 representative questions records expected
  relevant passages, irrelevant traps, bilingual wording, stale documents,
  conflicting guidance, and no-answer cases.
- Evaluation reports recall-at-k, precision-at-k, returned bytes, latency,
  freshness behavior, and source-scope errors separately from answer quality.

## M08-D: Knowledge and Learning Contracts

### Objective

Expose the three Knowledge scopes and governed Learning review lifecycle to
clients without transferring semantic ownership to those clients.

### Read Contracts

Define versioned operations for:

- scope capabilities and health;
- knowledge categories and documents;
- document metadata and bounded content;
- effective-context trace when an authoritative producer run records it;
- knowledge search using M08-C;
- project Learning candidates and their evidence/counter-evidence;
- User Context candidates, review status, and promotion eligibility;
- diagnostics for missing, stale, conflicted, or unavailable sources.

An effective-context trace reports what was actually supplied to a run. It
must not claim that indexed or available material was read when no run receipt
proves that fact.

### Action Contracts

Writes use commands separate from `mana inspect`. Every action requires a
specific target, expected revision, validated payload, and structured receipt.

- Framework knowledge is not editable through a linked project.
- Project knowledge edits use optimistic concurrency, project containment,
  schema/policy validation, atomic publication, and an audit-safe receipt.
- User knowledge edits target only a configured external User Context source
  after explicit source disclosure and permission. Success is followed by the
  existing materialization refresh; mirror files remain read-only.
- Project Learning actions retain the existing candidate lifecycle and never
  promote knowledge automatically.
- User Learning actions adapt the existing accept, edit-and-accept, reject,
  defer, and separate promotion commands without weakening their human gates.

### Gate D

- A client cannot turn an unavailable or stale read into a write authority.
- Revision mismatch returns a conflict and preserves both source and proposed
  content without overwriting either.
- Candidate review and promotion remain distinct receipts.
- Rejected or deferred candidates do not appear as active knowledge.
- All no-op, validation-failure, conflict, and partial-refresh outcomes are
  explicit and reproducible.
- Contract fixtures and a consumer compatibility gate exist before Familiar
  enables each surface.

## C05: Mana Familiar Knowledge and Learning Client

This cross-repository phase begins only after the corresponding Mana contracts
pass Gate D. Familiar should provide:

- separate Framework, User, and Project scopes;
- search with source, revision, freshness, and lifecycle filters;
- document reader and metadata views;
- an effective-context view based only on producer receipts;
- candidate review showing proposal, evidence, counter-evidence, limitations,
  target scope, and resulting receipt;
- editing only for capabilities advertised by Mana, with a diff and exact
  revision precondition before submission.

Familiar must not open SQLite directly, scan source roots, edit a generated
mirror, infer candidate eligibility, or reconstruct a failed action.

## M08-E: Opt-In PR Review Inbox and Scheduler

### Objective

Discover requested reviews, create idempotent review work, and make results
available even when Familiar is closed.

### Work

1. Define explicit user-level configuration: enabled repositories or
   organizations, reviewer identity, polling interval, maximum PRs per cycle,
   analysis policy, quiet hours, and cost/provider budgets.
2. Keep GitHub discovery read-only. Record an external-state cursor and bounded
   PR metadata; do not store credentials, full diffs, or unrestricted comments
   in scheduler state.
3. Use an idempotency key including repository identity, PR number, head SHA,
   requested reviewer identity, review profile revision, and relevant context
   revision. A changed head creates new work; an unchanged head does not.
4. Run the existing `requested-pr-review` profile through the governed runner.
   Preserve its scope checks, evidence requirements, and workspace isolation.
5. Store structured review status and local draft findings. Mark results stale
   when the PR head, profile, or admitted context changes.
6. Keep three policies distinct: notify only, analyse automatically, and
   publish an explicitly selected draft. Automatic analysis does not imply
   comment publication.
7. Implement the scheduler as a host-owned optional service or OS integration
   only after an ADR covers lifecycle, crash recovery, upgrades, locking,
   offline behavior, macOS and Windows support, and uninstall/disable behavior.
   Familiar is a controller and viewer, not the scheduler host.
8. Expose versioned inbox, run-detail, retry/cancel, and draft-publication
   contracts. External publication requires an explicit human action naming
   one current PR revision and the exact draft.

### Gate E

- Polling an unchanged inbox creates no duplicate run.
- Two scheduler instances or Familiar windows cannot analyse the same identity
  concurrently.
- Restart and network loss preserve a recoverable state without treating an
  unknown publication result as success.
- A new PR head makes older analysis visibly stale.
- Notify-only mode makes no provider call.
- Automatic analysis publishes no GitHub comment, review, approval, merge, or
  CI action.
- Publication tests use a fake boundary by default; a live pilot requires a
  dedicated repository and separate human authorization.

## C06: Mana Familiar PR Inbox Client

After Gate E, Familiar may display requested-review items, analysis progress,
freshness, checks, evidence gaps, findings, and comment drafts. It may request
retry, cancel, or explicit publication through Mana actions. It must not poll
GitHub independently, run providers directly, or infer that a GitHub thread is
resolved from local analysis alone.

## M08-F: Semantic Retrieval Experiment

### Decision Rule

FTS5 lexical retrieval is the production baseline. Semantic or hybrid
retrieval is considered only after Gate C exposes measured misses attributable
to vocabulary, language, or conceptual mismatch rather than bad source data,
chunking, filters, or ground truth.

### Experiment

1. Freeze the Gate C corpus and judgments before evaluating embeddings.
2. Compare lexical retrieval with one bounded local or explicitly configured
   embedding candidate. Keep indexing and query costs, model identity, privacy,
   and platform support visible.
3. Evaluate retrieval independently from generated answers. Use the same
   top-k, byte budget, filters, and freshness rules.
4. If hybrid ranking is evaluated, document score normalization and keep
   provenance and authority filters outside the embedding score.
5. Admit semantic retrieval only if it materially improves the predefined
   hard-query recall without unacceptable precision, latency, privacy,
   packaging, or maintenance regressions.

Failure to clear this gate closes M08-F with lexical retrieval retained. It
does not block M08-A through M08-E.

## Verification Strategy

Each work package must include:

- deterministic unit tests for identities, ordering, filtering, bounds, and
  state transitions;
- hostile filesystem fixtures for symlinks, traversal, replacement, malformed
  content, oversize files, permissions, and concurrent publication;
- contract fixtures checked against the published JSON schema;
- zero-model and zero-network acceptance paths for indexing, retrieval, reads,
  and human dispositions;
- consumer compatibility tests before Familiar depends on a new operation;
- benchmark evidence that distinguishes file discovery, hashing, parsing,
  projection, retrieval, process startup, and client rendering;
- Familiar performance reports for operation count, transport, decode,
  read-model construction, Flutter frames, memory, list windowing, refresh
  coalescing, and native first meaningful Overview;
- native desktop acceptance only for behavior that genuinely depends on window
  lifecycle, notifications, or OS scheduler integration.

Broad green test suites do not replace the negative cases and performance
evidence named by each gate.

## Rollout and Compatibility

1. Ship M08-A aggregate reads behind capability negotiation while keeping v1
   individual operations.
2. Ship M08-B index maintenance as opt-in and observable. Read results name
   whether they used a current index or a live scan.
3. Enable M08-C search only where the declared tokenizer/ranking capability is
   supported and the index is current.
4. Add M08-D read contracts before enabling any write action. Add Familiar
   surfaces one capability at a time.
5. Keep M08-E scheduler disabled until explicitly configured. Disabling it
   stops future polling without deleting review evidence.
6. Do not make embeddings, a daemon, or Familiar availability required for
   existing Mana workflows.

Rollback for every phase means disabling the new capability and returning to
the previous producer path without rewriting canonical source artifacts.

## Open Decisions

The following decisions require an ADR or explicit phase approval:

1. aggregate semantic-read operation name and schema composition;
2. external cache location, project key, retention, and encryption/privacy
   expectations;
3. SQLite/FTS5 availability and tokenizer parity on supported desktop targets;
4. exact source allowlist and chunking contract for each Knowledge scope;
5. project knowledge files eligible for governed editing;
6. User Context source-write authorization and recovery UX;
7. scheduler host, cross-platform lifecycle, and notification integration;
8. review result storage and retention across repositories;
9. quantitative semantic-retrieval admission threshold.

No implementation phase should silently decide one of these through incidental
code structure.

## Definition of Done

M08 is complete only when:

- the initial Familiar semantic read no longer repeats full catalog work;
- medium and large Familiar fixtures meet the approved first meaningful
  Overview, UI-isolate, frame, memory, and refresh budgets;
- the derived catalog and Knowledge index are versioned, rebuildable,
  freshness-aware, bounded, and safe under concurrent and hostile inputs;
- lexical retrieval passes its fixed relevance, scope, byte, latency, and
  freshness evaluation;
- Knowledge and Learning contracts preserve source authority and human gates;
- the optional review scheduler is idempotent, recoverable, disabled by
  default, and incapable of implicit publication;
- Familiar consumes only published capabilities and contracts;
- the semantic retrieval experiment is either admitted with evidence or
  explicitly closed while retaining the lexical baseline;
- compatibility, operational recovery, privacy, and release documentation are
  current.
