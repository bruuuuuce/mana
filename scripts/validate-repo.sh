#!/usr/bin/env bash
set -u
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
status=0
required_dirs=(docs skills agents profiles mcp templates scripts hooks evals .codex .junie .claude templates/mana-workspace)
for d in "${required_dirs[@]}"; do
  if [ ! -d "$root/$d" ]; then echo "ERROR: missing directory $d" >&2; status=1; fi
done
"$root/scripts/validate-skills.sh" "$root" || status=1
if ! "$root/scripts/build-skill-index.sh" "$root" | cmp -s - "$root/skills/index.yaml"; then
  echo "ERROR: skills/index.yaml is stale; run scripts/build-skill-index.sh > skills/index.yaml" >&2
  status=1
fi
"$root/scripts/validate-agents.sh" "$root" || status=1
"$root/scripts/validate-divination-metadata.sh" "$root" || status=1
"$root/scripts/validate-output-standard.sh" "$root" || status=1
"$root/scripts/validate-story-trace.sh" "$root" || status=1
"$root/scripts/validate-developer-choice-log.sh" "$root" || status=1
for f in README.md LICENSE CHANGELOG.md CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md docs/standards/agent-skill-output-standard.md docs/standards/output-contract.md docs/standards/story-trace-standard.md docs/standards/developer-choice-log-standard.md docs/standards/delivery-metrics-standard.md docs/policies/runtime-execution-contract.md templates/standard-agent-skill-report.template.md templates/delivery-metrics.template.md templates/mana-workspace/story-trace.template.md templates/mana-workspace/developer-choice-log.template.md; do
  if [ ! -f "$root/$f" ]; then echo "ERROR: missing $f" >&2; status=1; fi
done
for f in scripts/mana-workspace.sh scripts/mana-context.sh scripts/mana-user-learning.sh scripts/mana-pilot-feedback.sh scripts/mana-journey.sh scripts/mana-history.sh scripts/mana-rationale.sh scripts/mana-diagram.sh scripts/mana-concepts.sh scripts/mana-scout.sh scripts/mana-expand.sh scripts/mana-inspect.sh scripts/build-concept-index.sh scripts/evaluate-concept-index.sh scripts/bootstrap-project.sh scripts/mana-doctor.sh scripts/mana-update-check.sh scripts/run-sonar-scanner.sh scripts/run-dependency-evidence.sh scripts/divination.sh scripts/cast.sh scripts/mana-runtime.sh scripts/mana-explore.sh scripts/mana-learning.sh scripts/mana-eval.sh scripts/mana-verify.sh scripts/mana-repair.sh scripts/mana-repair-loop.sh scripts/mana-governance-report.sh scripts/validate-divination-metadata.sh scripts/validate-verification-skills.sh scripts/validate-story-start-scope-v2-contract.sh scripts/lib/divination.sh scripts/lib/explorer-retrieval.sh scripts/lib/user-context.sh scripts/lib/profile-metadata.sh scripts/lib/runtime-events.sh scripts/lib/verification.sh scripts/lib/repair.sh scripts/lib/repair-containment.sh scripts/lib/provider-dispatch.sh scripts/lib/verification-exec.pl tests/lib/json_schema_subset.py config/divination-domains.tsv config/runtime-retention.env.example config/user-context.env.example docs/workflow/mana-workspace.md docs/workflow/service-context-layer.md docs/workflow/user-context-layer.md docs/workflow/divination.md docs/workflow/casting.md docs/workflow/controlled-explorer-retrieval.md docs/workflow/governed-learning-signals.md docs/workflow/behavioural-evals.md docs/workflow/verification-skills.md docs/workflow/pilot-feedback.md docs/policies/verification-execution-policy.md docs/standards/mana-pilot-feedback-v1.schema.json docs/standards/mana-pilot-feedback-aggregate-v1.schema.json docs/standards/mana-inspect-project-v1.schema.json docs/standards/mana-inspect-artifacts-v1.schema.json docs/standards/user-choice-signal.schema.json docs/standards/recurring-evidence-cluster.schema.json docs/standards/user-context-candidate.schema.json docs/standards/user-context-candidate-review.schema.json docs/standards/verification-evidence-standard.md docs/standards/verification-result.schema.json docs/standards/mana-learning-journey-v0.md docs/standards/mana-learning-journey-v0.schema.json docs/standards/mana-learning-history-v0.md docs/standards/mana-learning-diagram-v0.md docs/standards/mana-learning-concept-v0.schema.json docs/standards/mana-learning-concept-tagging-v0.md docs/standards/mana-learning-scout-v0.md docs/standards/mana-learning-scout-v0.schema.json docs/standards/mana-learning-scout-cycles-v0.md docs/standards/mana-learning-expansion-v0.md docs/standards/mana-learning-expansion-v0.schema.json learning-kb/concept-index.tsv docs/standards/bounded-repair.md docs/standards/repair-target.schema.json docs/standards/repair-attempt-result.schema.json docs/standards/repair-attempt-result.schema.json docs/standards/repair-loop-result.schema.json docs/deployment/project-link-bootstrap.md templates/mana-workspace/manifest.template.yaml templates/mana-workspace/index.template.md templates/mana-workspace/global/service-mission.template.md templates/mana-workspace/global/engineering-guards.template.md templates/mana-workspace/global/hooks-config.template.yaml templates/mana-workspace/global/sonar-project.properties.template; do
  if [ ! -f "$root/$f" ]; then echo "ERROR: missing $f" >&2; status=1; fi
done
if [ -f "$root/scripts/mana-workspace.sh" ] && [ ! -x "$root/scripts/mana-workspace.sh" ]; then
  echo "ERROR: scripts/mana-workspace.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/mana-user-learning.sh" ] && [ ! -x "$root/scripts/mana-user-learning.sh" ]; then
  echo "ERROR: scripts/mana-user-learning.sh is not executable" >&2
  status=1
fi
for f in tests/user-learning-e2e.sh tests/user-learning-live-semantic.sh tests/mana-journey.sh tests/mana-history.sh tests/mana-diagram.sh tests/mana-concepts.sh tests/mana-concept-tagging.sh tests/mana-scout.sh tests/mana-scout-cycles.sh tests/mana-expand.sh tests/mana-inspect.sh tests/bug-hunter-agent.sh tests/mana-pilot-feedback.sh tests/run-zero-token-acceptance.sh tests/release-readiness.sh tests/story-start-deterministic-planning.sh tests/story-start-scope-v2-fixture.sh tests/story-start-scope-v2-schemas.sh; do
  if [ ! -f "$root/$f" ]; then echo "ERROR: missing $f" >&2; status=1
  elif [ ! -x "$root/$f" ]; then echo "ERROR: $f is not executable" >&2; status=1
  else bash -n "$root/$f" || status=1
  fi
done
if [ -f "$root/scripts/mana-repair.sh" ] && [ ! -x "$root/scripts/mana-repair.sh" ]; then
  echo "ERROR: scripts/mana-repair.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/mana-repair-loop.sh" ] && [ ! -x "$root/scripts/mana-repair-loop.sh" ]; then
  echo "ERROR: scripts/mana-repair-loop.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/bootstrap-project.sh" ] && [ ! -x "$root/scripts/bootstrap-project.sh" ]; then
  echo "ERROR: scripts/bootstrap-project.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/mana-doctor.sh" ] && [ ! -x "$root/scripts/mana-doctor.sh" ]; then
  echo "ERROR: scripts/mana-doctor.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/mana-update-check.sh" ] && [ ! -x "$root/scripts/mana-update-check.sh" ]; then
  echo "ERROR: scripts/mana-update-check.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/run-sonar-scanner.sh" ] && [ ! -x "$root/scripts/run-sonar-scanner.sh" ]; then
  echo "ERROR: scripts/run-sonar-scanner.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/run-dependency-evidence.sh" ] && [ ! -x "$root/scripts/run-dependency-evidence.sh" ]; then
  echo "ERROR: scripts/run-dependency-evidence.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/run-evidence-index.sh" ] && [ ! -x "$root/scripts/run-evidence-index.sh" ]; then
  echo "ERROR: scripts/run-evidence-index.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/cast.sh" ] && [ ! -x "$root/scripts/cast.sh" ]; then
  echo "ERROR: scripts/cast.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/mana-runtime.sh" ] && [ ! -x "$root/scripts/mana-runtime.sh" ]; then
  echo "ERROR: scripts/mana-runtime.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/mana-inspect.sh" ] && [ ! -x "$root/scripts/mana-inspect.sh" ]; then
  echo "ERROR: scripts/mana-inspect.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/validate-output-standard.sh" ] && [ ! -x "$root/scripts/validate-output-standard.sh" ]; then
  echo "ERROR: scripts/validate-output-standard.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/validate-story-trace.sh" ] && [ ! -x "$root/scripts/validate-story-trace.sh" ]; then
  echo "ERROR: scripts/validate-story-trace.sh is not executable" >&2
  status=1
fi
if [ -f "$root/scripts/validate-developer-choice-log.sh" ] && [ ! -x "$root/scripts/validate-developer-choice-log.sh" ]; then
  echo "ERROR: scripts/validate-developer-choice-log.sh is not executable" >&2
  status=1
fi
for f in "$root"/scripts/*.sh "$root"/hooks/pre-commit "$root"/hooks/pre-push; do
  [ -f "$f" ] || continue
  bash -n "$f" || status=1
  if [ "$(uname -s)" = Darwin ] && [ -x /bin/bash ] && [ "$(command -v bash)" != /bin/bash ]; then
    /bin/bash -n "$f" || status=1
  fi
done
retired_skill_pattern='(^|[^[:alnum:]_-])(story-depth|story-consistency|unit-test-gap|integration-test-gap|sonar-configuration-guide)([^[:alnum:]_-]|$)'
retired_skill_paths=(README.md CONTRIBUTING.md docs agents profiles skills templates hooks evals .codex .junie .claude)
for p in "${retired_skill_paths[@]}"; do
  [ -e "$root/$p" ] || continue
  if grep -R -n -E "$retired_skill_pattern" "$root/$p" >/tmp/mana-retired-skill-refs.$$ 2>/dev/null; then
    echo "ERROR: retired skill reference found under $p" >&2
    cat /tmp/mana-retired-skill-refs.$$ >&2
    status=1
  fi
  rm -f /tmp/mana-retired-skill-refs.$$
done
if [ "$status" -eq 0 ]; then echo "Repository validation passed"; fi
exit "$status"
