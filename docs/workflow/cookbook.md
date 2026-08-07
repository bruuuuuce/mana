# Workflow Cookbook

Task-oriented recipes for common Mana situations. Each entry names the
profile, skill, or command to use; follow the linked profile or doc for
details. For the end-to-end picture, see the Golden Path table in the
README and `docs/examples/end-to-end-codex-flow.md` /
`docs/examples/end-to-end-claude-flow.md`.

## Orientation And Onboarding

- **Get help choosing the next step:** run `scripts/run-profile.sh mana-help`
  or ask for the `mana-help-agent`.
- **Learn the framework interactively:** run `scripts/run-profile.sh tutorial`
  to start a conversational walkthrough of profiles, agents, and skills
  tailored to your role and current delivery phase.
- **Create workspace:** run `scripts/mana-workspace.sh init`; feature work goes
  under `.mana/features/<feature-id>/`, canonical branch work goes under
  `.mana/sessions/<timestamp>-<branch>-<purpose>/`.

## Requirements And Planning

- **Start a story:** run the `story-start` profile to produce story context,
  impact map, technical breakdown, effort estimate, risk register, and
  green-border plan.
- **Check story readiness for development:** run
  `profiles/story-ready-for-dev.yaml` before assigning work to a developer.
- **Prepare Team Leader planning:** run `profiles/team-planning.yaml` to
  produce execution sequence, owner/dependency map, story effort estimate,
  delivery risks, and review-load plan.
- **Calibrate a story estimate from delivery history:** ask explicitly for
  historical calibration after receiving the base estimate. Mana then uses
  read-only, team-level comparable-story evidence; it never runs this deeper
  analysis by default or derives individual productivity metrics.
- **Review epic/story slicing:** use `profiles/team-planning.yaml` or
  `profiles/story-ready-for-dev.yaml` with `epic-story-partitioning` to check
  whether sibling stories overlap, miss epic goals, hide dependencies, or need
  splitting before assignment.
- **Analyze an epic end to end:** use `profiles/epic-analysis.yaml` with an
  explicit Jira key. It creates structure and partitioning reports plus an
  evidence-backed implementation graph. Add `--allow-service-discovery` only
  when read-only inspection of services named by the stories is approved.
- **Generate a plan:** use the Story Implementation Planner Agent and route
  open questions to BA/PO, Team Leader, Architect, or DBA.
- **Use the story as evidence:** planning profiles use Jira story text and
  acceptance criteria to check feasibility, testability, scope, owners, and
  approvals. Review, validation, pre-mortem, and PR profiles compare branch/PR
  changes against the story and flag missing requested behavior, unrequested
  scope, contradicted acceptance criteria, and weak tests.

## Jira Evidence

- **Read Jira context from a branch:** configure `JIRA_URL` plus
  `JIRA_PERSONAL_TOKEN` for Jira Server/Data Center, or use
  `.mana/jira-mcp.env`. Profiles discover generic issue keys such as
  `PROJ-1234` from the branch, or accept `--jira-key <KEY>`.
- **Read one Jira story quickly:** in a linked project, run
  `./mana jira-mcp --get-issue PROJ-1234`. Use
  `./mana jira-mcp --check-access --issue PROJ-1234` only for credential or
  permission diagnostics.
- **Audit whether Jira state matches technical evidence:** run
  `scripts/run-profile.sh jira-state-audit --jira-key PROJ-1234 --codex`.
  The audit is read-only and compares Jira state, fixVersion, comments, PRs,
  merges, release branches, tags, and releases against
  `docs/policies/jira-state-consistency-policy.md`.
- **Discover and validate a project's tests:** run
  `scripts/run-profile.sh testbook-validation --project-root /path/to/project --codex`.
  Review the proposed testbook and approve individual entries before asking the
  agent to execute unit, integration, or performance tests.
- **Build repeatable GUI validation:** run
  `scripts/run-profile.sh gui-test-validation --project-root /path/to/project --codex`.
  Provide redacted documentation references and an isolated test target. Review
  the proposed Playwright testbook, approve each entry, then request explicit
  IDs. Mana preserves access-controlled traces, screenshots, video, JUnit, and
  a learning proposal; reports are redacted and it never targets production.
- **Validate an API collection:** run
  `scripts/run-profile.sh api-test-validation --project-root /path/to/project --codex`.
  Review and approve isolated-target Newman entries before selecting IDs.
- **Verify database state safely:** run
  `scripts/run-profile.sh database-read-verification --project-root /path/to/project --codex`.
  This requires approved PostgreSQL `SELECT/WITH` files and a test-only
  connection environment variable; it does not allow mutations or production.
- **Cache epic and sibling stories as Markdown:** in a linked project, run
  `./mana jira-mcp --fetch-epic-story-pack PROJ-1234`. Mana resolves the
  parent epic when Jira exposes one and writes
  `.mana/features/<EPIC-ID>/evidence/jira/epic-story-pack.md` for reuse by
  planning agents.
- **Work without Jira MCP:** create
  `.mana/features/<EPIC-ID>/context/epic-story-pack.md` from
  `templates/epic-story-pack.template.md` and use it as the requirement
  source.

## Development Support

- **Get development support before writing code:** use
  `profiles/dev-assist.yaml` to ask what-if questions about planned changes
  (`change-impact-preview`), identify concurrency risks, surface known
  pitfalls, characterize legacy code before refactoring, and plan unit and
  integration tests.
- **Estimate class change risk:** use `profiles/dev-assist.yaml` with
  `sonar-change-risk` before modifying a fragile class. The skill combines
  Sonar evidence, git churn, tests, story scope, and engineering guards to
  recommend a safe change strategy.
- **Implement a task in Junie:** open the approved technical task, restrict
  edits to the approved source-impact map, and run local tests after each
  change.
- **Run green border:** use the Green Border Test Agent to generate or run
  focused unit, integration, contract, regression, and legacy tests.
- **Capture non-obvious service knowledge:** run
  `scripts/run-profile.sh service-knowledge-capture --project-root /path/to/project --codex`.
  The agent writes evidence-backed candidate cards; stable promotion needs the
  accountable owner's approval.

## Quality Evidence

- **Collect deterministic implementation evidence:** run `./mana verify`.
  Inspect selection, trust, effects, and exact fixed actions first with
  `./mana verify --dry-run --explain`. Verification makes zero model calls and
  does not produce reviewer severity or merge/readiness judgment.
- **Run one verification capability explicitly:** use repeatable
  `./mana verify --skill <id>` flags. Explicit selection does not bypass
  applicability, catalog approval, environment, trust, effects, or bounds.

- **Configure local Sonar evidence:** keep only `SONAR_HOST_URL` and
  `SONAR_TOKEN` in the environment, then run `./mana sonar --init-config` and
  edit `.mana/global/sonar-project.properties`. Use `./mana sonar --check` to
  validate scanner/runtime/config readiness. See
  `docs/deployment/sonar-scanner-wrapper.md`.
- **Run local Sonar before review:** after building the project, run
  `./mana sonar --analyze`. Mana writes scanner logs and summary under
  `.mana/<workspace>/evidence/sonar/` so review and validation agents can use
  the evidence without rerunning the scanner.
- **Collect dependency evidence:** run `./mana dependency-evidence --collect`
  when dependency surfaces changed to record manifests, lockfiles, and
  existing scanner reports.
- **Build an evidence index:** run `./mana evidence-index` after collecting
  Jira, Sonar, dependency, test, validation, or PR evidence so agents can
  read a compact index before deep-loading artifacts.

## Validation, Review, And Handoff

- **Generate pre-commit development notes:** use `profiles/pre-commit.yaml`
  and `pre-commit-documentation-agent` to create
  `pr/pre-commit-development-summary.md` and `pr/knowledge-transfer-brief.md`.
- **Run a production pre-mortem:** use `profiles/jessica-fletcher.yaml` or
  `jessica-fletcher-agent` before commit/push to ask why the branch would fail
  in production.
- **Validate branch:** run the Branch Validation Agent to detect plan drift,
  unplanned files, missing tests, unresolved risks, and unsafe DB changes.
- **Triage requested reviews:** use `profiles/requested-pr-review.yaml` to
  read open GitHub PRs where you are a requested reviewer, rank them by risk,
  and produce draft review findings. The agent may use authenticated `gh` for
  read-only evidence and must not post comments or reviews without approval.
- **Review one PR quickly:** run
  `scripts/run-profile.sh requested-pr-review --pr <number> --codex`. Add
  `--publish-high-risk-comments` only when you want one PR comment with
  blocker or high-criticality findings from that run.
- **Run architecture review:** use `profiles/architecture-review.yaml` for
  ADR, NFR, service-boundary, architecture-drift, trust-boundary, contract,
  and database-risk evidence.
- **Prepare AM release readiness:** use `profiles/am-release-ready.yaml` for
  release impact, continuity, incident-risk, rollback, support, and
  communication evidence.
- **Check Jira state before release governance:** use
  `profiles/jira-state-audit.yaml` when the question is narrowly whether one
  issue's Jira state is coherent with Git, PR, branch, tag, or release evidence.
- **Generate PR package:** run the PR Readiness Agent to create the PR
  description, reviewer focus, test evidence, risk report, and development
  summary.
- **Create developer handoff:** use `skills/developer-handoff` through PR
  Readiness to generate a developer-facing reading guide with diagrams, code
  references, short snippets, tests to read first, and intentional
  non-changes.
- **Challenge implementation choices:** use `skills/developer-decision-review`
  to ask targeted questions about non-obvious decisions, plan drift, missing
  rationale, protected-area changes, and risky trade-offs.

## Team And Learning

- **Review team code quality for coaching:** run
  `scripts/run-profile.sh team-coaching-review` on a feature branch to
  identify recurring quality patterns per contributor. The
  `team-coaching-report-agent` produces a confidential report for the Team
  Leader with a per-contributor growth analysis and a prioritised coaching
  action plan.
- **Close the measurement loop:** record story rework, finding hit/miss, and
  open-question answer events per
  `docs/standards/delivery-metrics-standard.md`, and let `learning-agent`
  aggregate them into `.mana/global/metrics/delivery-metrics.md`.

## Framework Maintenance

- **Control the freshness check:** every profile/mode change through
  `scripts/run-profile.sh` runs `scripts/mana-update-check.sh` before
  printing/executing the profile. The check never updates files. It warns when
  the Mana checkout is dirty, has no upstream, cannot reach the remote, or is
  behind/ahead of upstream. Configure it with:

  ```bash
  MANA_UPDATE_CHECK=off scripts/run-profile.sh pre-commit
  MANA_UPDATE_CHECK=warn scripts/run-profile.sh jessica-fletcher
  MANA_UPDATE_CHECK=strict scripts/run-profile.sh branch-ready
  ```

- **Regression-check instruction changes:** run the behavioral eval scenarios
  in `evals/` that cover the touched profiles, agents, or skills. See
  `evals/README.md`.
