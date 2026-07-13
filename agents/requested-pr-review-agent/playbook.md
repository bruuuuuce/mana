# Requested PR Review Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman working notes while analyzing; maintain a context budget; keep final artifacts structured and free of private chain-of-thought.

1. Confirm `gh` is available and authenticated. Use it only for read-only PR
   discovery and evidence collection.
2. Resolve the active repository and reviewer. If `pr_number` is provided,
   analyze that PR directly; otherwise prefer `--review-requested @me` and ask
   the user if repository or reviewer identity is ambiguous.
3. Resolve the active Mana workspace and inspect `pr-review/**/run-metadata.yaml`
   plus existing `pr-review/pr-*-review-notes.md` artifacts. If this run targets
   an explicit PR and the active workspace already contains artifacts for a
   different PR, stop before reading the new diff with `needs_human_decision`.
   Warn that the session/workspace already analyzed another PR, recommend a
   clean runner session (`clear`/new chat) or a fresh Mana workspace, and ask
   whether to continue anyway. Continue only after explicit confirmation.
4. Create or reuse a target-specific output directory, then create a run
   directory before writing artifacts: `pr-review/pr-<number>/runs/<YYYYMMDDTHHMMSSZ>/`
   for an explicit PR, `pr-review/ticket-<issue-key>/runs/<YYYYMMDDTHHMMSSZ>/`
   when only a ticket is known, or `pr-review/inbox/runs/<YYYYMMDDTHHMMSSZ>/`
   for review inbox runs. Write `run-metadata.yaml` in the run directory before
   other outputs.
5. List open requested-review PRs, or load the selected PR, and collect metadata
   before reading diffs.
6. Rank PRs by risk and select the highest-signal PRs first. Respect any
   `max_prs`, label, author, branch, or repository filter from the user.
7. For each selected PR, collect changed files, filtered diff, checks, and
   review-relevant metadata.
8. Exclude Mana/bootstrap noise before finding production or review issues.
9. Load and run only the review skills whose conditions in `AGENT.md` match the
   filtered PR diff and available evidence.
10. Update or reference `agent-memory/story-trace.md` when a story workspace is
   available, then write the review inbox report and per-PR notes under the
   run-specific `pr-review/` subdirectory.
11. Present suggested comments as drafts by default. If
   `publish_high_risk_comments=true` and a single PR is selected, publish at
   most one `gh pr comment` containing only blocker or high-criticality findings
   from this run. Do not call any other `gh` command that writes to GitHub
   without explicit human approval.
