# Good Usage

User says in chat:

```text
Stiamo per aprire la PR, quale profilo uso?
```

Expected behavior:

- Reads the current `.mana/active-profile` (e.g., `jessica-fletcher`).
- Reports the currently active profile.
- Identifies the intent as "PR readiness" from the decision table.
- Confirms with the user before switching from `jessica-fletcher` to `pr-ready`.
- Writes `pr-ready` to `.mana/active-profile`.
- Returns the command: `scripts/run-profile.sh pr-ready --project-root .`

---

User says:

```text
I just started working on this story, what should I run?
```

Expected behavior:

- No active profile exists.
- Maps "just started / story" to `story-start`.
- Writes `story-start` to `.mana/active-profile` without asking for confirmation.
- Returns: `scripts/run-profile.sh story-start --project-root .`
- Lists the artifacts the profile produces.
