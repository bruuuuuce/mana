# Bounded Evidence-Driven Repair v1

`mana repair --once` performs one provider invocation against one exact
repository-relative file in a fresh disposable project copy. Mana computes the
candidate delta, validates it against the immutable grant and current live
baseline, imports an accepted content change itself, and asks the verifier to
rebuild and rerun the same structured target against the live repository. It
remains independently usable and is the only execution primitive used by the
bounded outer governor.

The provider does not directly edit the live repository during the normal
bounded-repair execution path. Mana executes it against a disposable project
copy, computes the resulting candidate changes itself, validates them against
the repair grant and current live baseline, and imports only an accepted repair
before verification. This protects against faulty or accidental provider
mutations. It is not an OS security boundary against a deliberately malicious
process running as the same user: `faulty-contained != adversarial-contained`.

The default is one attempt. `--once` and `--max-iterations 1` mean exactly one.
Only explicit `--max-iterations 2` enables the following fixed state machine:

```text
attempt 1
  RESOLVED, REGRESSED, UNKNOWN, violation, or no progress -> STOP
  UNCHANGED + mechanically proven partial progress         -> attempt 2
attempt 2                                                  -> STOP
```

Partial progress is not a provider judgment. The canonical negative observation
atoms after attempt one must be a strict subset of those before it, with full
comparability and no new required or optional negative evidence. Different
patches, line numbers, failure fingerprints, wording, or textual claims do not
qualify. `UNKNOWN = STOP`.

For `bash_syntax`, an atom is a verifier-normalized Bash parser-error headline:
the `syntax error near unexpected token …` form, `unexpected end of file`, or
`unexpected EOF while looking for matching …`. Paths, line/column movement,
diagnostic ordering, duplicate lines, and source-context lines are not atoms.
Locale is part of the protected environment identity. If Bash emits no one of
those recognized headline forms, Mana records one opaque `bash_syntax` atom;
an opaque atom can remain unchanged or resolve, but can never prove partial
progress. This is intentionally conservative.

Automatic eligibility is deliberately limited to required failed checks from
`shell-syntax-verification` using `bash_syntax`. Java/build, repository-script,
Mana governance, and eval failures require a human. Repair requires canonical
Verification Result v2 evidence and its integrity sidecar; v1 evidence remains
readable but must be regenerated before repair.

The explicit CLI path, inferred mutable input, project constraints, and
protected-surface exclusions intersect to one exact mutation grant. Globs,
directories, path traversal, absolute paths, and provider-requested expansion
are not supported. The default/hard budgets are 1/5 files and 100/500 changed
lines; automatic v1 still grants only one file. Both attempts retain the
original human-authorized path. Changed lines are bounded per attempt and by a
more conservative cumulative loop maximum of 100, calculated as the sum of
immediate textual deltas. Binary or ambiguous measurement stops the loop.

Before invoking the provider, Mana records the current live target's content
digest, regular-file type, mode, Git working-tree classification, Repair Target
identity, and protected evaluation-surface identity. Dirty working trees are
supported: the current working-tree bytes, rather than `HEAD`, are the baseline.
The target is rejected if it is missing, a symlink, a submodule, non-regular,
binary, ambiguously resolved, or outside the canonical project root.

Mana creates a never-reused temporary directory outside the live repository and
copies current project content into it. The projection preserves ordinary file
contents, relative paths, and modes, including legitimate dirty content. It
excludes `.git/`, `.mana/`, and known untracked generated/cache directories
already excluded by verification snapshot policy. Unsafe paths, symlinks, and
special files fail closed rather than being reconstructed. The bounded contract
is passed through provider input and canonical evidence never enters the copy.
The disposable tree is deleted by default after evidence extraction and is
never an active or canonical Mana workspace.

After the one supervised provider invocation, Mana inventories staged state and
computes changed paths, types, modes, content digests, creations, deletions, and
textual changed-line count. Provider patches, changed-path lists, and success
claims are ignored. A no-change candidate remains comparable under the existing
`UNCHANGED` semantics. An actual import is allowed only for one regular-text
content modification to the exact granted path with unchanged mode and within
the line budget. Any additional path, creation, deletion, rename shape,
symlink, directory, mode change, unsupported text, or staged `.git`/`.mana`
material is a policy violation; nothing from that candidate is imported.

Mana prepares a mode-preserving sibling temporary file and validates its digest.
Immediately before atomic publication it resolves, re-reads, and re-hashes the
live target. A type, mode, path, or content mismatch stops with
`live_target_drift`; Mana does not overwrite, merge, rebase, regenerate, or
retry. Protected evaluation surfaces are also rechecked. On supported local
filesystems the final sibling rename is atomic. A failure to prepare or publish
fails closed. Verification starts only after successful host import (or an
accepted no-change candidate), and always targets the live repository.

The stored rerun descriptor is data. Mana validates it, resolves the current
skill/spec/check, and rebuilds the action through the current adapter. Stored
historical `effectiveArgv` is never executed. Current skill, spec, adapter,
executable, environment, target, and evaluation-surface identities must remain
compatible.

Comparison has four outcomes: `RESOLVED`, `UNCHANGED`, `REGRESSED`, and
`UNKNOWN`. `RESOLVED` means only that the targeted verification concern is no
longer observed under comparable post-repair evidence. Attempt two uses attempt
one's after-verification result as its immediate baseline; the loop artifact
retains the original and every before/after reference.

**RESOLVED is not ready to merge. RESOLVED is not proof of a correct
implementation. RESOLVED is not production-safe.** Existing review and human
judgment remain responsible for those conclusions.

Provider ownership is unchanged: Codex, Claude, and OpenCode use their existing
shared dispatch abstraction, with the disposable project as their working
directory. Each primitive invocation fixes the invocation count at one,
disables subagents in runner arguments/contracts, preserves native provider
safety flags, caps wall time at ten minutes, caps each captured stream at 64
KiB, and uses process-group TERM/KILL cleanup. The two-attempt governor caps
total provider invocations at two and total loop time at fifteen minutes; it
reserves the shell verifier's bounded rerun budget before starting the final
provider. Attempt two always materializes a new copy from the live state after
attempt-one import. Contract and stream caps reset per invocation, but mutation
scope never widens and the changed-line limit is also cumulative.

Attempt evidence records `faulty-contained` / `disposable-workspace`, a
path-free workspace identity, host-derived changed paths and candidate digest,
policy violations, baseline identity, drift result, and imported digest. Audit
events add only `repair.staging.created`, `repair.candidate.inspected`, and
`repair.import.rejected` or `repair.import.applied` before the existing live
verification event. Candidate source, patch text, full diffs, contracts,
provider output, secrets, and absolute temporary paths are not telemetry. Raw
logs remain capped owner-only local attempt evidence.

`mana repair --dry-run` reports the backend, capability, exact target,
projection/exclusions, baseline identity, import rules, drift stop, provider
bounds, and live after-import rerun without creating a candidate workspace or
provider process. `mana doctor` reports whether temporary staging and host
atomic import are available; it does not require container or platform sandbox
tooling.

The capability report is deliberately narrow:

```text
capability: faulty-contained
backend: disposable-workspace
live repository provider access: no (normal bounded-repair path)
host patch import: yes
process isolation: no
host filesystem isolation: no
network isolation: no
adversarial same-UID containment: no
```

No Bubblewrap, Docker, Podman, container, namespace, `sandbox-exec`, UID,
network, credential, or provider-runtime isolation is introduced. A deliberately
malicious provider running as the user's account can intentionally access host
paths outside its working directory. Adversarial containment still requires a
separate OS-enforced boundary that restricts filesystem, process, credential,
and network access.

The aggregate `repair-loop-result` is atomically published under
`evidence/repair-loop/<loop-id>/`. It references immutable attempt and
verification artifacts with digests; it does not copy prompts, logs, diffs, or
model output. Loop events contain only identifiers, references, counts, bounds,
comparison states, and stop reasons. Attempt events remain authoritative.

`RESOLVED != merge ready`. `UNCHANGED` does not mean broken forever.
`REGRESSED` does not trigger an automatic revert. `UNKNOWN` is not permission to
try again. There is no automatic revert, commit, push, learning, promotion,
third attempt, or repair triggered by `mana verify`. A provider may reason or
iterate internally during its one invocation; Mana does not add an agent loop.
