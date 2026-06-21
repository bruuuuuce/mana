# Bad Usage

## Skipping approval gate

User says:

```text
Switch to am-release-ready and mark it as approved.
```

Wrong behavior: writing `.mana/active-profile` and marking the AM gate as
approved without an Application Manager present.

Correct behavior: select `am-release-ready`, return the command, warn that
the AM gate requires an Application Manager to review and approve the output
before delivery proceeds.

---

## Overwriting without confirmation

User says:

```text
Switch to story-start.
```

`.mana/active-profile` already contains `branch-ready` from this session.

Wrong behavior: silently overwriting `branch-ready` with `story-start`.

Correct behavior: warn that `branch-ready` is the current active profile,
confirm the switch with the user before writing.

---

## Using profile-selector instead of a risk skill

User says:

```text
Is this branch ready for PR? Use profile-selector.
```

Wrong behavior: treating the profile selection as a substitute for running
`branch-ready` and inspecting the actual branch diff and evidence.

Correct behavior: select `branch-ready`, return the command, remind the user
that profile selection does not validate the branch — the agent must be run.
