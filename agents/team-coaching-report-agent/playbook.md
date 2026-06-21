# Playbook: team-coaching-report-agent

## Preparation

Before starting:
1. Confirm that `branch_name` and `base_branch` are provided. Default
   `base_branch` to `main` if not specified.
2. Load `.mana/global/engineering-guards.md` and
   `.mana/global/testing-policy.md` if present. Note missing files as
   warnings — do not block.
3. Check that an active workspace exists (`.mana/` directory). If missing,
   produce output in chat and advise:
   `scripts/mana-workspace.sh init --root . --feature <branch-key>`

## Execution

### Phase 1 — Enumerate Contributors

```bash
# List unique contributors on the branch beyond base
git log <branch_name> --not <base_branch> --format="%ae|%an" | sort -u

# List commits per contributor
git log <branch_name> --not <base_branch> \
  --author=<email> --format="%H|%s|%ad" --date=short
```

Present the list to the Team Leader with commit counts. Wait for
confirmation or adjustment before proceeding to Phase 2.

If `contributor_filter` is set in inputs, apply it directly — no
confirmation gate needed.

Edge cases:
- Zero commits beyond base → status `blocked`, stop immediately.
- Contributor with 1 commit → flag `low_commit_count`, continue with
  reduced confidence.
- Bot accounts (e.g., CI bots) identified by email pattern → skip by
  default, note in output.

### Phase 2 — Per-Contributor Analysis

For each confirmed contributor, in sequence:

```bash
# Files touched by this contributor
git log <branch_name> --not <base_branch> \
  --author=<email> --name-only --format="" | sort -u > /tmp/contrib_files

# Contributor diff (only their files)
git diff <base_branch>...<branch_name> -- $(cat /tmp/contrib_files)
```

Invoke skills in this order on the contributor's diff:
1. `pre-review-defect` — pass: diff, `engineering-guards.md` if available.
2. `test-quality` — pass: diff, `testing-policy.md` if available.
3. `npe-nullability` — pass: diff.
4. `java-performance-smell` — pass: diff. **Skip if no non-test `.java`
   files in diff.** Check with:
   `grep -l "\.java$" /tmp/contrib_files | grep -v "Test\.java$"`
5. `known-pitfalls-extraction` — pass: diff + `known-pitfalls` doc if
   available. Skip if no pitfall database found.

Invoke `contributor-pattern-analysis` with all collected findings.

Save output to workspace:
`agent-memory/contributor-pattern-report-<sanitized-name>.md`
(sanitize name: lowercase, spaces → hyphens, remove special chars)

### Phase 3 — Team Aggregation

Build the heatmap table after all contributor reports are complete.
Categories: `test_coverage`, `nullability`, `defect_quality`,
`performance`, `pitfall`.

For each cell: `habit` / `tendency` / `isolated` / `—`.

Shared gap threshold: pattern appears in > 50% of contributors.

### Phase 4 — Report Production

Write `agent-memory/team-coaching-report.md`.

Section order (mandatory):
1. Header with branch, date, contributor count.
2. Executive Summary (3-5 bullets).
3. Team Heatmap table.
4. Shared Gaps section.
5. Per-contributor sections (alphabetical by name).
6. TL Action Plan (prioritised, numbered).
7. Privacy Note (verbatim from AGENT.md).

Language rules:
- "growth opportunity" not "error" or "bug".
- "tends to omit" not "always forgets".
- "could strengthen" not "weak at".
- Recommend actions, never verdicts.

## Completion Criteria

- All confirmed contributors have a `contributor-pattern-report` saved.
- `team-coaching-report.md` exists in the active workspace.
- Heatmap covers all contributors.
- Privacy note is present verbatim.
- Status returned to TL with explicit `human_approval_required: true`.

## Handoff To Team Leader

After producing the report:
1. Confirm output location: `agent-memory/team-coaching-report.md`.
2. Remind: "Review before scheduling any coaching session."
3. Suggest next step: "Schedule 1-to-1s or team session based on Action Plan."
4. Update `agent-memory/story-trace.md` with: branch analysed,
   contributor count, shared gaps identified, TL gate status.
