# Provider capability contract

Mana inspects provider behavior with:

```bash
scripts/mana-provider-capabilities.sh codex
scripts/mana-provider-capabilities.sh claude
scripts/mana-provider-capabilities.sh opencode
```

The default output is JSON conforming to
`contracts/context-runtime/provider-capabilities-v1.schema.json`. `--human`
prints a derived local table. Inspection runs `--version`, documented help
commands, and a bounded provider-specific configuration probe where one exists.
It makes no model call, writes no repository or `.mana` state, stores no cache,
and deletes temporary probe files.

## Status semantics

- `supported`: the current probe has direct, provider-specific evidence for
  the control or transport surface.
- `unsupported`: an authoritative inspected surface proves the capability is
  absent.
- `unknown`: the available surface cannot establish the behavior reliably.

`unknown` is deliberately different from `unsupported`. Mana never converts an
unknown into supported because a flag existed historically, because a version
number is newer, or because another provider exposes a similar feature. A valid
but previously unseen version is evaluated only from its observed help/config
surface.

Each adapter records positive and negative evidence separately before state is
chosen. One shared resolver applies this truth table:

| Positive | Authoritative negative | State |
|---:|---:|---|
| no | no | `unknown` |
| yes | no | `supported` |
| no | yes | `unsupported` |
| yes | yes | `unknown` |

Contradictory evidence is therefore an evidence gap rather than a reason to
prefer whichever branch happened to run first.

Required-prerequisite composites are evaluated only after this atomic
resolution. All required states must be `supported` for the composite to be
supported; any atomically resolved `unsupported` prerequisite makes it
unsupported; otherwise an `unknown` prerequisite keeps the composite unknown.
Raw positive or negative evidence from a prerequisite is never inspected again.
Optional direct evidence about the composite is resolved independently, and a
direct/derived contradiction resolves to unknown.

Each provider adapter first recognizes the identity and grammar of its own help
surface. Support requires a structurally recognized option/command declaration
with positive semantics, or a successful structured provider-specific probe.
Flag names embedded in arbitrary or negative prose are ignored. Missing options
in partial help and syntactically successful but unexpected help produce
`unknown`. `unsupported` is reserved for an explicit negative declaration in a
recognized provider surface or an equivalent structured negative result.
Claude option declarations additionally include their entire indented
description block. Refutations such as `ignored at runtime`, `unsupported`,
`has no effect`, or `unavailable` on the same line or a continuation line are
negative evidence and prevent the declaration from resolving to support.

The v1 report models structured events, separate final output, output schemas,
fresh and ephemeral invocation, root model and effort selection, managed
children, hard child disable, child context/model/effort routing, recursion,
child concurrency/depth, tool-output retention, compaction threshold/prompt/
scope, and user-config isolation. Each entry carries a bounded evidence ID;
raw provider output is never copied into the report.

## Current provider interpretation

Codex uses `exec --help` for JSONL, final-message, schema, ephemeral, model, and
user-config-isolation controls, plus `features list` for multi-agent presence.
Hard disable requires the feature-disable CLI and the known multi-agent feature
surface. The current probe does not prove that a child receives isolated
context, uses the requested model/effort, cannot recurse while children are
enabled, or honors the configured thread/depth/compaction/tool-output values;
those capabilities remain unknown.

Claude uses the main CLI help. On a recognized surface it exposes stream JSON,
JSON Schema, print-mode fresh invocation, no-session persistence, root
model/effort, agent definitions, auto-compaction threshold, safe mode, and tool
denial. Absence of a separate final-message declaration is not itself negative
evidence, so that capability remains unknown unless the surface explicitly
rejects it. Child context, effective child model/effort,
enabled-path recursion limits, concurrency/depth, custom compaction prompt,
compaction scope, retained tool-output limit, and complete user-configuration
isolation remain unknown. Safe mode proves only its declared customization
scope, including custom commands and agents; it is not promoted to complete
user-configuration isolation.

OpenCode uses root/run help and a bounded `debug config --pure` probe with
temporary XDG and project directories. The probe supplies distinct user and
project markers plus a colliding inline agent definition. It records only safe
booleans showing that the provider merges non-conflicting configuration and
that inline `permission.task: deny` wins for the selected collision; it does not
retain resolved configuration. Run JSON, root model, and variant are exposed on
recognized help declarations. Absence of structured output schema and a
separate final-message file is not negative evidence, so both remain unknown
unless explicitly rejected. Child context and effective child model or effort,
concurrency/depth, persistence, compaction, tool-output retention, hard disable,
full user-config isolation, and runtime recursive-delegation prevention remain
unknown. A resolved `permission.task: deny` is configuration evidence only; no
model call is made to infer runtime behavior. An `ok` config probe is accepted
only when root/child deny, child model, user/project merge, non-conflicting
preservation, and inline collision precedence all satisfy the experiment's
invariants.

## Hard subagent disable

- Codex: passes `--ephemeral --ignore-user-config --disable multi_agent
  --disable multi_agent_v2`, `agents.max_depth=0`, and the provider-required
  inert minimum `agents.max_threads=1`. Because the child features are off, the
  effective maximum is zero even though Codex rejects a configured thread
  value of zero. Stale agent files cannot restore a disabled feature.
- Claude: does not select the managed orchestrator, enables `--safe-mode`, and
  denies the `Agent` tool explicitly. Safe mode excludes project/user custom
  agents; the prompt reports an effective maximum/depth of zero. This does not
  claim complete isolation from all user configuration.
- OpenCode: selects a unique primary defined through
  `OPENCODE_CONFIG_CONTENT` and denies its built-in `task` permission. This is a
  deterministic invocation-local configuration deny, and a stale project
  `mana_orchestrator` is not selected. The config surface alone does not prove
  runtime recursive-delegation prevention. OpenCode nevertheless merges config
  sources, and `--pure` excludes external plugins rather than proving complete
  user/project config isolation. Therefore recursion prevention, hard disable,
  and user-config isolation remain unknown. The disabled path creates no
  persistent managed orchestrator.

Enabled Claude and OpenCode concurrency limits remain prompt policy rather than
a verified provider hard limit, and Codex thread/depth behavior is not promoted
to supported by the capability report. High-risk work must continue to return
`needs_model_escalation` when provider-managed escalation is unavailable. Fresh
host-launched phase workers remain the reliable fallback planned for later
phases.

## Failures and privacy

Missing binaries, version failures, command-level help/probe failures, malformed versions,
malformed fixtures, and missing adapters fail with a non-zero status. Malformed
feature/config probe output cannot create supported capabilities; where a
report remains possible, affected fields become unknown. There is no cache to
become stale or corrupt.

OpenCode fixtures also undergo semantic validation. `probeStatus: ok` requires
all checks in the bounded merge/collision experiment to be true; a failed or
malformed probe cannot carry partial positive booleans. Structurally valid but
semantically inconsistent fixtures are rejected with the malformed-fixture
status rather than being allowed to create supported capabilities.

Capability reports contain no prompt, response, source, reasoning, credential,
arbitrary environment, transcript, or tool payload. They contain only schema
and provider version metadata, safe probe evidence identifiers, and capability
states.
