# M07 release readiness: Mana productization track

## Scope reviewed

Starting revision: `ebf24649d1e55676572a1b311b1db40a9be10c23` on
`feature/mana-inspect-v1`. The local audit baseline file was unavailable, so
the checked-out repository and committed M00–M06 outputs are authoritative.

| Area | Status | Evidence |
|---|---|---|
| Inspect v1 contracts | Ready | Versioned schemas, fixtures, copied bundle, producer tests, and the C00 compatibility gate passed against the available Mana Familiar checkout. |
| Existing workspace compatibility | Ready | Inspect remains additive; unknown/malformed workspace entries are catalogued safely and current evidence-index/runtime/verify/repair commands are unchanged. |
| Bootstrap and wrapper | Ready | Public `mana inspect` and `mana pilot-feedback` dispatch is covered by bootstrap-target tests. |
| Bug hunt | Ready | Explicit bounded scope, evidence threshold, Jessica/PR routing, read-only behavior, and zero-token evals are covered. |
| Pilot feedback | Ready | Explicit local human dispositions, deterministic aggregate exports, redaction, duplicate/immutable-reference and zero-record tests are covered. |
| Provider runtimes | Compatible | No provider runtime contract changed; inspect/pilot commands are local shell operations and make no model call. |
| Documentation/security | Ready | README, help routing, workflow, compatibility, privacy, path, symlink, payload, and no-OS-sandbox limits are documented. |

## Release blockers

The inspect/pilot/bug-hunt targeted contracts are green. Final release approval
is blocked on a complete hosted CI run because the local runner did not return
a completion result for the pre-existing bounded-repair timeout/interruption
tests (`tests/bounded-repair.sh` and `tests/bounded-repair-loop.sh`). Their code
was not modified in this track. Human release work also remains required:
choose a version, review this branch, and make any tag/push/release decision.
No inspect result, pilot aggregate, or test result grants that approval.

## Warnings and intentionally unexecuted checks

- GitHub Actions was not triggered locally; the complete zero-token suite is
  wired into its validation workflow but needs a hosted pull request/push run.
  Locally, it passed `behavioural-evals` before the bounded-repair runner did
  not return an outcome; separate targeted inspect/pilot/bug-hunt tests pass.
- C01 is a later cross-repository Mana → Familiar harness, not part of M07.
  C00's deterministic compatibility gate passed against the available Familiar
  checkout; C01 still requires its dedicated end-to-end harness.
- C02 needs real, explicitly recorded pilot feedback; no saved-time, ROI, or
  adoption claim is supportable from empty/local fixtures.
- `mana-doctor` completed with environment warnings: Sonar scanner readiness,
  Docker daemon, GitHub CLI authentication, and Jira access are unavailable;
  User Context is intentionally unconfigured. These do not alter inspect v1.
- No version, tag, commit, push, PR, release, network action, or model-backed
  test was performed by M07.

## Compatibility and security notes

Inspect is an additive v1 producer API. It preserves existing workspace
commands, emits project-relative paths, does not follow symlinks, bounds detail
payloads, and treats Markdown/text as untrusted content. The pilot mechanism is
opt-in and local-only; aggregates exclude raw references and notes. Neither
mechanism provides an OS sandbox or a human approval decision.

## Next phase

After hosted CI passes, the branch is ready for human review and then C01 where
the target Mana Familiar checkout is explicitly selected. C02 follows only
after approved pilot evidence is available.
