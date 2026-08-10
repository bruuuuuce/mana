# User Learning (M1–M4)

## Purpose

User Learning records explicit developer choices across Mana-linked projects as
small, auditable `UserChoiceSignal` records. M1 captures governed source
evidence and M2 deterministically aggregates that evidence:

```text
governed Developer Choice Log → UserChoiceSignal → RecurringEvidenceCluster → UserContextCandidate → external host-owned state
```

Run it deliberately from a linked project:

```bash
./mana user-learning capture
./mana user-learning capture --json
./mana user-learning aggregate
./mana user-learning aggregate --json
./mana user-learning synthesize
./mana user-learning synthesize --dry-run --json
```

The command reads only canonical Developer Choice Logs below
`.mana/features/*/decisions/` and `.mana/sessions/*/decisions/`. It does not
scan repositories elsewhere on the machine. Capture is deliberately not a
runner hook: a developer opts into this bounded scan rather than every Mana
execution rereading historical choice logs.

## Boundaries and vocabulary

Project-local governed learning remains exactly as it is: runtime observations
become project-local `.mana/learning/candidates/`. It is not cross-project and
its candidate semantics do not change.

A choice is an explicit decision, not a preference. For example, a confirmed
choice of PostgreSQL is evidence that PostgreSQL was selected in that bounded
decision; it says nothing by itself about a stable user preference.

The lifecycle is deliberately proposal-first:

```text
explicit choices
    ↓
UserChoiceSignal                         (M1 implemented)
    ↓
deterministic cross-project aggregation  (M2 implemented)
    ↓
RecurringEvidenceCluster                 (M2 implemented)
    ↓
bounded lightweight semantic synthesis   (M3 implemented, T1 only)
    ↓
UserContextCandidate                     (M3 implemented, proposal only)
    ↓
explicit human review/promotion          (M4 implemented, T0 only)
    ↓
host-owned User Context                  (M4 writes only after promotion)
```

A candidate is a proposal, never truth, until a human explicitly accepts it.
M3 has no promotion path and never reads or writes either the external User
Context source or the materialized `.mana/user-context` mirror.

## Eligibility and schema

M1 accepts only a well-formed row in the standard `## Choices` table whose
status is `confirmed` and whose Question Or Choice, Developer Answer, and
Confirmed By fields are non-empty. `asked`, `answered`, `rejected`, `deferred`,
and `needs_owner_review` rows are skipped. This is deliberately conservative:
the current log contract cannot distinguish every rejected or deferred item as
an explicit decision rather than a rejected proposal or outstanding work.
Malformed rows are skipped and reported; they never become signals.

[`UserChoiceSignal` schema version `2`](../standards/user-choice-signal.schema.json) contains a SHA-256-derived stable signal
ID, a stable project ID, a bounded source-decision reference and ordinal,
the confirmed subject and developer answer, any reliable date/Story/Area data,
the confirming actor, and bounded provenance (source artifact digest, evidence
cell, and follow-up when present). The Developer Choice Log has no separate
rationale column, so M1 never infers or splits rationale from the developer
answer. There are no preference, confidence, scope, personality, or semantic
category fields.

### Identity invariant

`signalId` identifies the originating governed developer decision, not a
captured JSON payload. It is stable across changes to decision descriptions,
evidence, follow-up text, whitespace, source line numbers, source artifact
digest, capture metadata, scan order, state location, and JSON serialization.
Distinct governed decision records remain distinct evidence, including records
with identical text and records in different projects.

The current identity key is canonical JSON with exactly these fields:

```text
identityVersion: "1"
projectId: hash(remote.origin.url) when available, otherwise hash(canonical project root)
sourceLog: project-relative canonical Developer Choice Log path
choiceOrdinal: ordinal of the well-formed row in that log's Choices table
```

`signalId = "user-choice-" + sha256(identityKey)`. `choiceOrdinal` counts all
well-formed Choice rows, including non-eligible rows, so a later confirmation
keeps the same source-decision identity. The current Developer Choice Log has
no stable row-ID column; moving a decision to another log or changing its
ordinal is therefore a genuine provenance identity change and produces new
evidence. Source line and artifact digest are diagnostics only.

## External state and provenance

Signals are never written to a project repository. The state directory is:

1. `$MANA_USER_STATE_HOME/user-learning/signals` when explicitly set;
2. `$XDG_STATE_HOME/mana/user-learning/signals`;
3. `$HOME/.local/state/mana/user-learning/signals`.

All roots must be absolute and a state location inside the source project is
rejected. Signal filenames are generated SHA-256 identifiers, writes stage a
private sibling file and publish with a rename, and an existing validated ID is
reported as already known. The JSON result reports discovered, newly stored,
already known, and skipped rows with cheap skip reasons and source references.
M1 uses preserve-first persistence: when the same source decision is
recaptured with changed non-identity content, it remains one signal and is
reported as already known rather than creating a second historical record.

Signals retain the project root, source log path, source row, source decision
ordinal, source artifact digest, and the evidence/follow-up cells
where present. This traces a signal to the governed explicit decision without
copying the complete log or any transcripts.

The User Context source and materialized `.mana/user-context` mirror are
outside this lifecycle. They are never read or written by capture; normal Mana
execution therefore retains User Context's read-only materialization boundary.

## M2 deterministic aggregation

M2 reads only regular JSON files from the external `signals/` directory and
materializes derived [`RecurringEvidenceCluster` v1](../standards/recurring-evidence-cluster.schema.json)
files under the sibling external `clusters/` directory. It validates schema v2
signals, rejects filename/embedded-ID mismatches, unsupported schemas,
malformed JSON, invalid records, duplicate signal IDs, and symlink inputs.
Skipped evidence is reported and never affects recurrence.

The aggregation key is canonical JSON with exactly these fields:

```text
aggregationVersion: "1"
normalizedSubject: normalized UserChoiceSignal.sourceDecision.subject
normalizedConfirmedChoice: normalized UserChoiceSignal.sourceDecision.confirmedChoice
```

Normalization is deliberately conservative and mechanical: normalize CRLF/CR
to LF, trim leading/trailing whitespace, collapse remaining whitespace runs to
one ASCII space, and preserve every other character and case. Therefore
`PostgreSQL`, `postgres`, and `PostgreSQL database` are distinct keys unless
they are already literally equal after that whitespace normalization. No topic
classification, fuzzy matching, embedding, or semantic equivalence is used.

`clusterId = "cluster-" + sha256(aggregationKey)`. It identifies the key, not
the current supporting signals: adding or removing source evidence refreshes
the cluster payload and counts while keeping the same ID. This intentionally
differs from M1, where a signal is immutable historical evidence identified by
its governed source decision.

Each cluster exposes sorted source signal IDs, source project IDs,
`occurrenceCount`, and `distinctProjectCount`. These are measurements only;
they are not candidate eligibility, a preference, a recommendation, or a
confidence score. M2 retains single-occurrence measured clusters as well as
recurring ones.

When an exact normalized subject has other exact normalized confirmed choices,
M2 exposes them as `alternativeConfirmedEvidence`. This is a mechanical
comparison of the same structured subject, not a claim that arbitrary choices
or projects are semantically contradictory. Rejected, deferred, and unresolved
records remain absent because M1 does not capture them.

Clusters are complete derived state: every aggregate builds a complete staging
directory, atomically replaces `clusters/`, and removes stale cluster files.
Signals are never changed. Ordering is sorted before grouping, and cluster
payloads contain no generation timestamp, so unchanged input produces
byte-equivalent materialized output.

## Cost policy

M1 and M2 make zero model calls (`modelCalls: 0` is stored and reported). M2
is strictly T0: it performs no agent, embedding, classification, or network
work. The design remains deterministic-first: semantic inference is used only
after T0 has selected a bounded M3 package. M3 is T1 only; T2 reasoning
escalation is not implemented.

## M3 bounded semantic synthesis

M3 is implemented as one tightly bounded T1 proposal call per deterministic
evidence family. It does not change M1 signals or M2 clusters. Its output is a
versioned [`UserContextCandidate` v1](../standards/user-context-candidate.schema.json)
under external state, or a successful `NO_CANDIDATE` record. M4 human review
and promotion remain separate T0 human actions.

The cost tiers are explicit: M1/M2 are T0 deterministic processing, M3 is T1
lightweight semantic synthesis, and no T2 provider/model/fallback/escalation
path exists. The T1 provider is selected with
`MANA_USER_LEARNING_T1_PROVIDER` (`codex`, `claude`, or `opencode`) and the
concrete model with `MANA_USER_LEARNING_T1_MODEL`; absent the latter, Mana uses
the provider's existing economy-model configuration (`MANA_CODEX_MODEL`,
`MANA_CLAUDE_MODEL`, or `MANA_OPENCODE_MODEL`). This keeps model names out of
the architecture. Codex M3 calls may explicitly set a supported reasoning
effort with `MANA_USER_LEARNING_CODEX_REASONING_EFFORT` (`minimal`, `low`,
`medium`, `high`, or `xhigh`). The override is applied after
`--ignore-user-config`; when unset, the existing isolated default is preserved.
`stub` is accepted only with the explicit test-only
`MANA_USER_LEARNING_ALLOW_STUB=true` gate.

### Deterministic T0 preflight and batching

M3 scans validated external M2 clusters but never sends the whole store to a
model. It makes deterministic lexical token buckets from normalized subjects,
then deduplicates equal cluster sets. Token overlap is only a cheap candidate
window; it is not semantic equivalence. A unit contains one or more M2
clusters and is T1-eligible only when it has at least three explicit supporting
M1 signals across at least two projects. This includes a single exact recurring
cluster: T1 may need to distinguish reusable guidance from repeated external
constraints. A single isolated or weakly repeated choice still remains a
deterministic no-spend observation. Units are sorted, capped, and never grow
recursively.

Default limits are 8 clusters/unit, 3 supporting signals/cluster, 3,600 input
tokens (an estimate), 12,000 hard serialized-input bytes, 500 output tokens,
32 units/run, and one invocation/unit. `MANA_USER_LEARNING_MAX_INPUT_TOKENS`
is a deterministic serialized-prompt planning estimate (serialized bytes divided
by four, rounded up); it is not a tokenizer or an exact provider billing
guarantee. `MANA_USER_LEARNING_MAX_INPUT_BYTES` is the independent, actual
host-enforced serialized prompt bound. Both can be lowered; hard caps are 8
clusters, 4 signals, 4,000 estimated input tokens, 16,000 input bytes, 600
output tokens, and 64 units.

Evidence text fields are clipped before packaging. If a package exceeds either
budget, Mana deterministically reduces optional supporting signals within the
existing per-unit bounds, serializes again, and rechecks both limits. If the
minimum valid package still exceeds a bound, that unit is reported as
irreducibly oversized and makes zero provider calls; JSON is never truncated.
The host also bounds runner output bytes and validates response lengths.
`--dry-run` reports selected provider/model, limits, unit counts, cache status,
and whether a call would be made without invoking a provider.

The synthesizer receives a structured package only: cluster keys/counts,
bounded signal IDs/project IDs/choice fields/evidence cells, and relevant M2
alternative evidence. It receives no source tree, transcript, full choice log,
or User Context. Its contract permits `CANDIDATE` or `NO_CANDIDATE` only. The
Codex transport schema is derived per bounded call with the exact exposed
cluster and signal IDs as enums, preventing structured decoding from truncating
or fabricating provenance. The provider-neutral host validator remains the
authority and rejects non-JSON output, unknown keys, unknown cluster or signal IDs,
missing support, oversize fields, and fabricated provenance. Provider failure
is distinct from `NO_CANDIDATE`, creates no artifact, and is never retried by
M3.

### State, identity, and re-synthesis

M3 stores inspectable JSON beside the existing external state:

```text
user-learning/
  signals/
  clusters/
  candidates/
  synthesis/
```

Files are published through private sibling staging files and renames. M3 does
not mutate `signals/` or `clusters/`. Candidate identity is
`sha256({identityVersion, synthesisVersion, semanticTask, sorted sourceClusterIds})`;
therefore capture timestamps, provider/model metadata, token telemetry, and
serialization order cannot create a new candidate. A materially different
cluster family has a different identity.

The input fingerprint is the SHA-256 of canonical JSON for the bounded
evidence package and synthesis contract. A `CANDIDATE` and `NO_CANDIDATE` both
publish a synthesis record keyed by that fingerprint. Normal reruns skip an
unchanged processed package; `--force` intentionally bypasses that cache. A
changed bounded source package gets a new fingerprint and may be synthesized.
`NO_CANDIDATE` is normal successful semantic output and produces no guidance
candidate artifact. A valid `deferred-for-review` candidate is deterministic
no-spend state: M3 does not overwrite a later review workflow's decision.

JSON and human output expose clusters scanned, units considered/skipped/cached,
calls made/avoided, reductions/irreducible oversize skips, estimated input and
output usage, serialized-input bytes, T1 identity, and the configured budgets.
Transport failures are reported separately from invalid provider responses.
Candidate artifacts retain source M2
cluster IDs, selected M1 signal IDs/project IDs, bounded counter-evidence,
input fingerprint, T1 provider/model metadata, estimated output usage, and
the model's rationale/limitations for later human review.

## M4 explicit human review and promotion

M4 is the final, T0-only human gate. It makes `modelCalls: 0` and never runs
synthesis, provider dispatch, semantic rewriting, scope inference, or
autonomous repository exploration. The stages remain distinct:

```text
candidate = Mana's M3 proposal
review = an explicit human disposition of that proposal/evidence version
managed User Context entry = explicitly promoted active guidance
```

Use the small explicit CLI:

```bash
./mana user-learning candidates --json
./mana user-learning show <candidate-id> --json
./mana user-learning review <candidate-id> --accept
./mana user-learning review <candidate-id> --edit "Prefer X only when Y" --scope reliability
./mana user-learning review <candidate-id> --reject
./mana user-learning review <candidate-id> --defer
./mana user-learning promote <review-id> --dry-run
./mana user-learning promote <review-id>
```

`review` requires exactly one action; there is no default. `ACCEPT` retains
the candidate text and scope, while `EDIT_AND_ACCEPT` records the supplied
human text/scope without changing the candidate. `REJECT` and `DEFER` never
write User Context. Promotion is a separate affirmative command, so listing,
showing, synthesis, validation, refresh, dry-run, or an omitted action can
never promote guidance. A rejected version requires `--override-rejected`
before a later acceptance can be recorded.

M4 creates immutable [`UserContextCandidateReview` v1](../standards/user-context-candidate-review.schema.json)
records in external `user-learning/reviews/`. Review identity is a canonical
hash of candidate ID, candidate input fingerprint, action, reviewed guidance,
and reviewed scope; timestamps do not change it. A separate external status
record tracks the current disposition for that exact candidate/fingerprint.
Changed M3 input fingerprints are pending again: an old review cannot promote
a changed candidate, and existing active guidance is never silently replaced.

Accepted reviews become eligible, not automatically active. `promote` first
revalidates the candidate, all M2 clusters, and M1 signals, then atomically
publishes one owned Markdown file under:

```text
$MANA_USER_CONTEXT_ROOT/learned/user-learning-entry-<stable-review-hash>.md
```

The entry is compact: approved guidance, approved scope, and bounded IDs for
entry/review/candidate/fingerprint provenance. Full M1–M3 audit detail stays
in User Learning state. The managed marker is required before an existing
target can be treated as idempotently promoted; any manually authored or
malformed collision fails closed and is never overwritten. Repeating the same
promotion therefore leaves one active managed entry.

After source publication, M4 calls the existing `mana context refresh` helper.
It never writes `.mana/user-context` directly. If refresh fails, the valid
external source entry remains and the promotion result reports
`source_published_refresh_failed`; it does not claim full promotion. The
normal User Context precedence and read-only materialization rules remain
unchanged.

Rejecting a candidate is not negative learning and does not teach Mana the
opposite preference. It is only lifecycle evidence about that proposal.
Deletion, supersession, and arbitrary User Context editing remain future
human-owned lifecycle work; M4 deliberately does not automate them.

## Testing and acceptance

Normal regression/CI tests consume zero model tokens. They cover M1 identity
and capture, M2 deterministic aggregation, M3 eligibility/budget/cache and
provider-stub contracts, M4 review/promotion, and the full
`tests/user-learning-e2e.sh` lifecycle from canonical Developer Choice Logs
through User Context refresh. The end-to-end test proves that source signals
and derived clusters remain unchanged, provenance is resolvable, promotion is
compact and idempotent, and project-local governed learning is untouched.

Provider-stub integration tests validate dispatch, bounded prompts, schema and
provenance rejection, cache behavior, and human/M4 zero-call behavior. They do
not establish that a semantic model can distinguish a recurring preference
from a recurring external constraint.

Some invariants concern the behavior of the semantic synthesizer itself and
cannot be proven by a fake provider. `tests/user-learning-live-semantic.sh` is
a separate opt-in semantic acceptance suite. It uses temporary state and tiny
synthetic Developer Choice Logs, never reads or writes a developer's User
Learning/User Context/project state, uses T1 only, and has no agent recursion,
repository exploration, retries, or T2 escalation.

Run it only with explicitly configured lightweight provider/model credentials
through Mana's normal provider setup:

```bash
MANA_RUN_LIVE_MODEL_TESTS=1 \
MANA_USER_LEARNING_T1_PROVIDER=codex \
MANA_USER_LEARNING_T1_MODEL=<lightweight-model> \
MANA_USER_LEARNING_CODEX_REASONING_EFFORT=high \
tests/user-learning-live-semantic.sh
```

The suite refuses to run without that opt-in and configuration, never prints
credentials, and is not executed by normal CI. It makes exactly five T1 calls
(one per compact scenario), each with at most 1,000 estimated input tokens,
4,000 serialized input bytes, and 500 estimated output tokens. These are hard
test bounds and useful cost characteristics, not exact billing guarantees.
It checks external-constraint `NO_CANDIDATE`, reusable guidance, contextual
counter-evidence, multi-cluster reconciliation, and exact single-cluster
recurrence using structured host-side assertions rather than brittle prose or
a second model as judge.
