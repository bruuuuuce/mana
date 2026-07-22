---
name: jira-release-state-evidence
version: 1.0.0
description: Collects read-only Jira, Git, and GitHub evidence to audit whether a Jira issue state is consistent with branch, PR, merge, tag, and release evidence.
compatibility:
  - codex
  - claude
preferred_runner: codex
allowed_tools:
  - jira_read
  - git_read
  - github_read
  - code_search
  - read_files
inputs:
  - jira_issue_key
  - target_branch
  - release_branch
  - fix_version
  - remote_refs
  - jira_state_consistency_policy
outputs:
  - jira_state_evidence_report
  - release_evidence_timeline
  - consistency_input_summary
risk_level: low
owner_role: Developer / Team Leader / Release Owner
stack:
  - workflow
tags:
  - jira
  - release
  - git
  - github
  - audit
model_tier: economy
execution_mode: read
delegation_group: documentation
parallel_safe: true
---

# Jira Release State Evidence

## Purpose
Collect factual, read-only evidence needed to audit whether one Jira issue state
matches repository and release evidence. The skill produces a structured
timeline and evidence gaps; it does not update Jira, branches, PRs, releases, or
external systems.

## When To Use It
- When a user asks whether a Jira issue is in the right workflow state for its
  implementation, PR, merge, fixVersion, release branch, tag, or release.
- Before release readiness, branch validation, or delivery governance checks
  where Jira state must be compared with technical evidence.
- When low-cost economy-model evidence collection is enough and ambiguous cases
  should be escalated instead of over-interpreted.

## When Not To Use It
- Do not use it to transition Jira issues, approve PRs, merge branches, create
  tags, publish comments, or deploy.
- Do not infer release correctness from missing evidence.
- Do not resolve high-impact ambiguity without human review.
- Do not treat comments, branch names, or commit messages as stronger evidence
  than merge, tag, release, or deployment records.

## Inputs
- `jira_issue_key`: Jira key to audit, or issue keys discovered from the branch.
- `target_branch`: mainline or integration branch expected by the policy.
- `release_branch`: release or hotfix branch expected by the policy, when known.
- `fix_version`: Jira fixVersion to compare against release evidence, when known.
- `remote_refs`: available local or remote refs, including PR refs if fetched.
- `jira_state_consistency_policy`: policy file or embedded rules to apply later.

## Outputs
- `jira_state_evidence_report`: compact evidence report with access gaps.
- `release_evidence_timeline`: ordered timeline of Jira, Git, GitHub, branch,
  tag, and release signals.
- `consistency_input_summary`: normalized facts for the evaluating agent.

## Execution Logic
1. Resolve the Jira issue key from explicit input, branch name, PR title, commit
   messages, or local Mana artifacts. If multiple issue keys are plausible,
   report ambiguity instead of choosing silently.
2. Read the Jira issue with read-only access. Extract status, resolution,
   fixVersion, affectedVersion when relevant, labels, linked issues, issue
   links, development links, comments that mention PRs, branches, releases,
   deployments, rollback, or manual transitions, and timestamps.
3. Search Git history for the issue key in commit subjects, bodies, branch
   names, merge commits, tags, and release branches. Record commit SHAs, authors
   when available, commit dates, containing branches, and tag containment.
4. Search GitHub or GHE read-only metadata when available: PRs mentioning the
   issue key, linked branches, target branch, merge status, merge commit,
   review/check status when already present, releases, tags, and PR timestamps.
5. Build a single timeline ordered by timestamp. Mark each event as `fact`,
   `inference`, or `gap`. Facts need a concrete source reference.
6. Normalize evidence into policy-friendly fields: `jira_status`,
   `jira_resolution`, `fix_versions`, `prs`, `commits`, `merged_to_mainline`,
   `merged_to_release_branch`, `tag_contains_commit`, `release_mentions_issue`,
   `deployment_evidence`, `comments_override_or_explain_state`, and
   `access_gaps`.
7. Return `blocked` only when the issue cannot be read and no fallback evidence
   exists. Return evidence gaps for missing PR refs, unavailable remote, missing
   GitHub auth, or incomplete clone.

## Decision Rules
- `blocker`: Jira issue cannot be read and no local fallback can identify state,
  fixVersion, or implementation evidence.
- `warning`: clone lacks relevant refs, remote is unavailable, GitHub/GHE is not
  authenticated, multiple PRs or release branches are plausible, or fixVersion
  mapping is unclear.
- `info`: coherent evidence was collected with concrete references and no
  material access gap.

## Failure Modes
- Local clones may not include PR refs, deleted branches, release tags, or full
  history.
- GitHub development links and Jira development panels may be unavailable
  through the configured MCP or CLI.
- Cherry-picks, hotfixes, reverted commits, release trains, and parallel release
  branches can make branch containment non-1:1 with Jira fixVersion.
- Commit messages without issue keys can hide implementation evidence.
- Jira comments may describe intent rather than completed technical state.

## Required Human Review
Team Leader or Release Owner reviews `non_coherent`, `ambiguous`, and
`blocked` outcomes. High-impact release, production, hotfix, or customer-visible
ambiguity requires human escalation even when an economy model collected the
evidence.

## MCP Behavior
Use least-privilege read-only access. Jira, GitHub, Git, CI, release, and
deployment systems may be read when configured. Never write comments,
transition issues, edit fixVersion, approve/merge PRs, create tags, publish
releases, trigger CI, or deploy.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use `templates/standard-agent-skill-report.template.md` when no more
specific template exists.

Internal reasoning must use compact caveman mode: terse facts, evidence-first
notes, no long narrative, and no private chain-of-thought in final artifacts.
Maintain a context budget: summarize raw Jira payloads, PR threads, logs, and
diffs instead of copying them.

## Example Output
```yaml
skill: jira-release-state-evidence
status: ready_with_warnings
jira_issue_key: PROJ-1234
summary: "Issue is Done with fixVersion 2.7.1; PR 456 is merged to release/2.7 but no release tag evidence is available locally."
timeline:
  - timestamp: "2026-07-10T09:12:00Z"
    type: jira_status
    evidence: "PROJ-1234 transitioned to Done"
  - timestamp: "2026-07-11T14:20:00Z"
    type: pr_merge
    evidence: "PR 456 merged into release/2.7"
evidence_gaps:
  - "Local clone does not contain tags newer than 2026-07-11."
normalized:
  jira_status: Done
  fix_versions:
    - "2.7.1"
  merged_to_release_branch: true
  tag_contains_commit: unknown
human_review_required: true
```
