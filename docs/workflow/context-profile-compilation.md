# Context Runtime profile compilation

CTX-04 adds a deterministic, zero-token compiler for the profile activation
graph:

```bash
scripts/mana-compile-profile.sh requested-pr-review \
  --execution-id execution-example
```

With no run directory, the compiler prints canonical JSON and writes no project
or `.mana` state. A host-derived static signal or a bounded classifier request
can activate only a conditional mapping declared by the profile:

```bash
scripts/mana-compile-profile.sh requested-pr-review \
  --execution-id execution-example \
  --static-signal migration_or_schema_change \
  --request-skill dependency-security-evidence \
  --deep-load-skill liquibase-production-risk
```

`--static-signal` is an assertion by the host that deterministic evidence has
matched the named profile signal. `--request-skill` is the classifier surface;
undeclared conditional requests fail. `--deep-load-skill` exposes an
instruction path only after activation and rejects inactive skills.

To publish the validated manifest beneath an explicit run directory, provide
both the authorized project root and a safe project-relative directory:

```bash
scripts/mana-compile-profile.sh requested-pr-review \
  --execution-id execution-example \
  --project-root /path/to/project \
  --run-directory .mana/runtime/runs/execution-example
```

Publication uses the CTX-03 contained, atomic writer and produces
`context-manifest-v1.json` with restrictive permissions. Absolute paths,
traversal, symlink redirection, and unsafe destinations fail closed.

## Legacy fallback

`skills:` remains the full profile candidate catalog and `skill_activation:`
remains authoritative when present. A profile without an activation block
compiles in `legacy-fallback` mode: every candidate stays initially active and
a migration warning is recorded. The existing single-run renderer follows the
same rule. This compatibility path avoids silently removing work before that
profile receives an explicit activation graph.

Skill activation never grants write authority. Active write skills appear in
`writePermissionRequirements`; the host governance envelope and authority
context still determine whether any write is permitted.

## Canonical runtime consumption

`cast.sh` accepts the same repeatable activation inputs as the compiler. Its
dry-run JSON keeps `candidateSkills`, `inactiveSkills`, and
`availableConditionalSkills` as a catalog, while `skills`, `modelRouting`, and
`runnerClasses` are projections of `activatedSkills` only. During execution it
publishes the already compiled canonical bytes beneath the runtime directory
and passes that exact manifest and the original host inputs to `run-profile.sh`.

`run-profile.sh` authoritatively validates a supplied manifest before routing.
The validation boundary materializes the canonical accepted bytes directly;
execution-plan and prompt construction consume that single in-memory value and
never reopen the caller-owned candidate path after validation. Its provider
prompt embeds the canonical manifest as the authority for active
skills, activation reasons, model tier, risk, execution mode, delegation group,
parallel safety, escalation, artifacts, semantic agents, and available
conditionals. The model may read the profile or selected agent/playbook for
remaining workflow semantics, but must not rederive activation from them.
Inactive skill bodies and the complete skill catalog index are not prompt
inputs. A skill instruction body is eligible only when its active ID also
appears in `deepLoadedSkills`.

The validator has a separate structural surface and an authoritative surface.
The latter resolves all catalogs from the framework root and profile ID and
compares the candidate to a freshly derived expected manifest. Caller-supplied
copies of profile/catalog/expected data are not accepted.

The legacy warning text is deterministic, contains no path or input payload,
is recorded in `warnings`, and is emitted on stderr. Stdout remains canonical
JSON and exit status remains zero. A present malformed activation block exits
nonzero, emits a clear error, and never emits a legacy warning or manifest.

For `requested-pr-review`, CTX-04 preserves the current baseline
`changed-files-risk-classifier` plus `pre-review-defect` and the existing nine
conditional mappings. Moving `pre-review-defect` behind
`application_code_change` is explicitly deferred to PRC-02.
