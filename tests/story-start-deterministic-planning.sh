#!/usr/bin/env bash
set -eu

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_text() {
  file="$1"
  text="$2"
  rg -Fq "$text" "$root/$file" || fail "$file is missing required guardrail: $text"
}

require_text profiles/story-start.yaml 'authoritative_input_behavior: do_not_rederive_or_reload'
require_text profiles/story-start.yaml 'numeric_estimate_behavior_when_blocked: not_estimable'
require_text agents/story-implementation-planner/AGENT.md 'record the exact conflict as a blocker'
require_text agents/story-implementation-planner/AGENT.md 'never a numeric range'
require_text skills/story-effort-estimation/SKILL.md 'story_points: null'
require_text skills/story-effort-estimation/SKILL.md 'implementation-only person-time range'
require_text skills/technical-task-breakdown/SKILL.md 'requirement or acceptance criterion'
require_text skills/green-border-plan/SKILL.md 'explicit-risk citation'
require_text templates/implementation-contract.template.yaml 'authoritative_inputs: []'

echo "Story-start deterministic planning guardrail tests passed"
