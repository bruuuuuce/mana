# Jira State Consistency Policy

This policy defines how Mana classifies Jira issue state against read-only Jira,
Git, GitHub/GHE, branch, tag, and release evidence. It supports audit and
delivery governance decisions; it does not authorize Jira transitions, PR
approval, merge, deployment, or release.

## Verdicts

| Verdict | Meaning |
|---|---|
| `coherent` | Jira state is supported by the required technical evidence for the configured workflow state. |
| `non_coherent` | Jira state contradicts required technical evidence or is materially ahead/behind the implementation or release evidence. |
| `ambiguous` | Evidence is mixed, incomplete, branch mapping is unclear, or the policy cannot decide safely. |
| `blocked` | Required source access is unavailable and no reliable fallback evidence exists. |

## Evidence Strength

Use stronger evidence before weaker evidence:

| Strength | Evidence |
|---|---|
| Strong | Merged PR with target branch, merge commit containment, release tag containing commit, release record, deployment record. |
| Medium | Commit reachable from target branch, Jira development link, CI/check evidence tied to merged PR, release branch containment. |
| Weak | Branch name, unmerged PR, commit message only, Jira comment, manual note, inferred fixVersion mapping. |

Weak evidence can explain ambiguity but must not make an issue coherent when a
stronger required signal is missing.

## Baseline State Rules

| Jira State Family | Coherent When | Non-Coherent When | Ambiguous When |
|---|---|---|---|
| `To Do` / `Open` / `Backlog` | No merged PR, release branch, tag, or deployment evidence exists. | Strong evidence shows implementation is merged or released. | Only weak implementation evidence exists. |
| `In Progress` / `Development` | Work branch, commits, or open PR evidence exists and no required merge/release evidence is claimed. | Strong evidence shows issue is released, or no implementation evidence exists and the state is old enough to require owner review. | Multiple active branches or PRs exist with unclear owner/status. |
| `In Review` / `Code Review` | Open PR exists for the issue and target branch is plausible. | PR is already merged/released, or no PR/review evidence exists. | PR refs are missing, PR target is unknown, or several PRs match. |
| `Ready for Release` / `Merged` | PR or commit is merged to the configured release branch or mainline required by the workflow, and no release/tag/deploy claim is required yet. | Issue is marked ready but merge evidence is absent, or it is already released while Jira remains pre-release. | FixVersion maps to multiple release branches or cherry-pick path is unclear. |
| `Done` / `Resolved` | Project policy defines Done as merged, and merge evidence exists for the expected target branch. | Project policy defines Done as released but only merge evidence exists, or implementation evidence is absent. | Done semantics are not configured for the project. |
| `Released` / `Closed` | Release tag, release record, or deployment evidence contains the implementation or explicitly includes the issue/fixVersion. | No release/tag/deploy evidence exists, or the issue is released in Jira before containing branch/tag evidence. | Release evidence exists but commit containment or fixVersion mapping is incomplete. |

## FixVersion And Release Mapping

- `fixVersion` is not proof of release by itself.
- A fixVersion is coherent with `Ready for Release` when the issue's merged PR
  or commit is reachable from the mapped release branch.
- A fixVersion is coherent with `Released` only when at least one strong release
  signal exists: tag containment, release record, or deployment record.
- If one fixVersion maps to multiple branches, trains, hotfixes, or customer
  channels, classify as `ambiguous` unless the configured target is explicit.

## PR And Branch Rules

- A merged PR is strong evidence only for its actual target branch.
- A PR merged to `develop` is not automatically evidence for a release branch.
- A cherry-pick requires explicit commit containment on the release or hotfix
  branch; matching message text alone is weak evidence.
- A reverted PR or revert commit makes the state `ambiguous` unless release
  evidence proves the reverted change was not shipped or was restored.
- Deleted branches are not negative evidence when merge commits or PR metadata
  remain available.

## Tags, Releases, And Deployments

- A tag is strong evidence only when the implementation commit is reachable from
  the tagged commit.
- A GitHub/GHE release is strong evidence when it points to a tag or commit that
  contains the implementation, or when release notes explicitly include the
  issue and the tag relationship is credible.
- Deployment evidence is strong only when it is tied to a commit, tag, release,
  environment, or release artifact.

## Escalation Rules

Classify as `ambiguous` and require human review when:

- multiple matching PRs, branches, fixVersions, or release branches exist;
- Jira state and comments conflict;
- there are cherry-picks, hotfixes, reverts, backports, or parallel releases;
- GitHub/GHE, Jira, remote refs, tags, or deployment evidence are inaccessible;
- the issue has high customer, production, regulatory, security, database, or
  cross-service impact;
- project-specific workflow semantics for `Done`, `Resolved`, or `Closed` are
  not configured.

Classify as `blocked` only when the audit cannot read the Jira issue and lacks a
reliable local fallback for the requested decision.

## Required Output

Every verdict must include:

- Jira issue key, state, resolution, and fixVersion.
- Target branch and release branch used for evaluation.
- Evidence timeline with concrete source references.
- Required evidence that was found.
- Required evidence that is missing.
- Final verdict and one-sentence rationale.
- Human owner for follow-up when verdict is not `coherent`.
