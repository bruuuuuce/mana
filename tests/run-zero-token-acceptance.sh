#!/usr/bin/env bash
# Complete deterministic acceptance suite. It invokes no model or external API.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tests=(
  behavioural-evals.sh
  bounded-repair-loop.sh
  bounded-repair.sh
  bug-hunter-agent.sh
  cast.sh
  codex-subagent-regression.sh
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
  provider-dispatch.sh
  repair-containment.sh
  runtime-events.sh
  service-knowledge-bootstrap.sh
  story-start-deterministic-planning.sh
  story-start-scope-v2-fixture.sh
  story-start-scope-v2-schemas.sh
  story-start-scope-v2-discovery.sh
  story-start-scope-v2-triage.sh
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

echo 'Complete zero-token acceptance suite passed'
