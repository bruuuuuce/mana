#!/usr/bin/env bash
# Complete deterministic acceptance suite. It invokes no model or external API.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
acceptance_tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-zero-token-acceptance.XXXXXX")"
trap 'rm -rf "$acceptance_tmp"' EXIT
# Canonical acceptance is read-only with respect to this checkout. Evaluation
# output and any Python cache are explicitly owned by this external harness.
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$acceptance_tmp/pycache"
before_snapshot="$acceptance_tmp/worktree-before.jsonl"
after_snapshot="$acceptance_tmp/worktree-after.jsonl"
python3 "$root/tests/worktree-snapshot-test-only.py" "$root" > "$before_snapshot"
tests=(
  analysis-trajectory-guard-tg00-fixtures.sh
  analysis-trajectory-guard-tg02-telemetry.sh
  analysis-trajectory-guard-tg03-state.sh
  analysis-trajectory-guard-tg04-drift.sh
  analysis-trajectory-guard-tg05-checkpoint.sh
  analysis-trajectory-guard-tg06-integration.sh
  analysis-trajectory-guard-tg07-evaluation.sh
  behavioural-evals.sh
  bounded-repair-loop.sh
  bounded-repair.sh
  bug-hunter-agent.sh
  cast.sh
  codex-subagent-regression.sh
  context-runtime-baseline.sh
  context-runtime-budgets.sh
  context-runtime-authority.py
  context-runtime-race.py
  context-runtime-rollout.sh
  context-runtime-schemas.sh
  context-runtime-profile-compiler.sh
  context-runtime-evidence-store.sh
  context-runtime-phase-runner.sh
  context-runtime-phase-resume.sh
  context-runtime-phase-provider.sh
  context-runtime-delegation.sh
  context-runtime-workers.sh
  context-runtime-provider-children.sh
  context-runtime-modes.sh
  context-runtime-comparison.sh
  context-runtime-live-shadow.sh
  context-runtime-09g-r1-hygiene.sh
  divination.sh
  epic-analysis-profile.sh
  explorer-retrieval.sh
  jira-pr-evidence-completeness.sh
  learning-signals.sh
  mana-concept-tagging.sh
  mana-concepts.sh
  mana-diagram.sh
  mana-expand.sh
  mana-history.sh
  mana-inspect-contract.sh
  mana-inspect.sh
  mana-journey.sh
  mana-pilot-feedback.sh
  mana-rationale.sh
  mana-scout-cycles.sh
  mana-scout.sh
  profile-skill-activation.sh
  provider-capabilities.sh
  provider-dispatch.sh
  provider-usage.sh
  repair-containment.sh
  runtime-events.sh
  service-knowledge-bootstrap.sh
  story-start-deterministic-planning.sh
  story-start-scope-v2-fixture.sh
  story-start-scope-v2-schemas.sh
  story-start-scope-v2-discovery.sh
  story-start-scope-v2-triage.sh
  story-start-scope-v2-planner.sh
  story-start-scope-v2-governor.sh
  story-start-scope-v2-integration.sh
  story-start-scope-v2-release-gate.sh
  story-start-stage-routing.sh
  testbook-tools.sh
  user-context.sh
  user-learning-aggregation.sh
  user-learning-e2e.sh
  user-learning-live-semantic-harness.sh
  user-learning-review.sh
  user-learning-synthesis.sh
  user-learning.sh
  verification-skills.sh
)

for test_file in "${tests[@]}"; do
  [ -x "$root/tests/$test_file" ] || { echo "ERROR: missing executable test: tests/$test_file" >&2; exit 2; }
  echo "==> tests/$test_file"
  "$root/tests/$test_file"
done

python3 "$root/tests/worktree-snapshot-test-only.py" "$root" > "$after_snapshot"
if ! cmp -s "$before_snapshot" "$after_snapshot"; then
  echo 'ERROR: canonical suite changed the worktree filesystem' >&2
  diff -u "$before_snapshot" "$after_snapshot" | head -200 >&2 || true
  exit 1
fi
echo 'Complete worktree filesystem snapshot unchanged'

echo 'Complete zero-token acceptance suite passed'
