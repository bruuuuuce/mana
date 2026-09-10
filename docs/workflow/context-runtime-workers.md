# Context Runtime fresh host workers

CTX-07B runs a validated CTX-07A delegation plan with:

```bash
scripts/run-context-workers.sh execution-... \
  --project-root /path/to/project \
  --plan /path/to/bound-delegation-plan.json
```

The execution must already be active in Context Runtime v2. Use the same
`--static-signal`, `--request-skill`, and `--deep-load-skill` inputs that were
used to initialize/prepare the authoritative CTX-04 manifest. Optional
`--profile` and `--provider` assertions fail if the plan belongs elsewhere.

The default parallelism is the authoritative CTX-04 `directWorkers` limit.
`--max-parallel` may lower that value but cannot raise it. All task packets are
read-only, independently owned, parallel-safe, and depth zero under CTX-07A;
there is no writer worker in CTX-07B.

Routing is deterministic:

- architecture, contracts, database, operations, and security scopes use the
  policy-selected full model;
- an active task skill with full tier or high risk uses the policy-selected full
  model;
- other read-only tasks use the policy-selected economy model.

Concrete model IDs and reasoning efforts come only from the host installation's authoritative,
versioned `config/context-runtime/worker-routing-policy-v1.json`. Worker
model/effort CLI flags are not accepted, and matching `MANA_*_MODEL`,
`MANA_*_FULL_MODEL`, or reasoning-effort environment overrides are rejected.
`--framework-root` is not a production option and framework/policy environment
overrides are rejected. The task question and provider response never select a
model.

Every task receives a fresh provider process and one canonical worker context
packet. It contains the read-only governance envelope, validated task, narrow
CTX-04 projection plus source digest, task-active skill metadata and bodies,
authorized evidence IDs, output contract, and policy-selected model/effort.
Parent prompts/transcripts, phase checkpoints, sibling tasks, candidate or
inactive skills, evidence bodies, full run state, and extra permissions are
omitted.

The capability probe proves explicit model/effort selection mechanisms, not
the existence of each policy model ID. A provider rejection is a transport
failure. A verified host read-isolation backend is mandatory. It exposes only
the private worker capsule; unavailable or uncertain isolation fails before
invocation. Every attempt runs in a dedicated process group with host-owned
timeout and TERM/KILL grace.

Claims and state use the CTX-03 root-FD/no-follow boundary. Bound results are
immutable attempt artifacts and become reusable only through a validated
task-result HEAD. Invocation lifecycle and usage artifacts are immutable and
privacy-safe; reuse produces no provider call or duplicate usage record.

Provider stderr is always captured in a separate mode-`0600` temporary file
inside the invocation's private mode-`0700` scratch directory. It is deleted
and never excerpted into runner output or durable state. Transport failures use
only a bounded host-generated diagnostic containing provider, invocation ID,
and exit status.

Raw trace retention is separate from stderr. The default
`config/context-runtime/worker-debug-policy-v1.json` policy discards traces.
Only a checked-in `retain` value loaded from the canonical framework root can
preserve an invocation trace; CLI options, environment variables, tasks, and
model output cannot enable it. A retained trace is stored as mode `0600` under
the matching invocation attempt and is a potentially sensitive local debug
artifact, not a delivery artifact. Usage records report its actual presence;
events and aggregates contain no trace content.

State operations briefly lock the existing task directory inode, avoiding a
lock-file creation race while allowing different tasks to execute concurrently.
An immutable receipt records the validated result and safe usage before HEAD
publication. A subsequent invocation of the runner reconciles committed or
pending receipts, finishes missing metrics/events and closes the original claim
without invoking the provider again. A failure receipt cancels an explicit
publication failure before HEAD. Unknown or tampered recovery artifacts stop
the runner without deletion; they are never treated as reusable results.

The isolation backend is the fixed OS executable, not a caller `PATH` command.
Metric setup failures stop transport. The process group is drained even when
the provider leader exits before its children, and watchdog sleeps are reaped.

The runner prints one canonical `delegation-merge-v1` object. It does not write
the merge into the run or advance the state machine. If a worker provider or
output validator fails, the runner prints an incomplete lossless merge,
returns nonzero, and does not retry. Capability gaps fail before invocation as
`needs_model_escalation`. Provider-managed child workers are not implemented in
this command and remain CTX-07C scope.
