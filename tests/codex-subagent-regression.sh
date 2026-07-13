#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-codex-subagents.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_file_contains() {
  file="$1"
  pattern="$2"
  grep -Fq -- "$pattern" "$file" || fail "expected $file to contain: $pattern"
}

assert_file_not_contains() {
  file="$1"
  pattern="$2"
  if grep -Fq -- "$pattern" "$file"; then
    fail "did not expect $file to contain: $pattern"
  fi
}

make_fake_codex() {
  bin_dir="$1"
  mkdir -p "$bin_dir"
  cat > "$bin_dir/codex" <<'STUB'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then
  echo "codex-cli fake"
  exit 0
fi
printf '%s\n' "$@" > "$MANA_TEST_CODEX_ARGS"
last=""
for arg in "$@"; do last="$arg"; done
printf '%s\n' "$last" > "$MANA_TEST_CODEX_PROMPT"
STUB
  chmod +x "$bin_dir/codex"
}

run_profile_with_stub() {
  project="$1"
  shift
  mkdir -p "$project"
  MANA_TEST_CODEX_ARGS="$tmp/codex.args" \
    MANA_TEST_CODEX_PROMPT="$tmp/codex.prompt" \
    PATH="$tmp/bin:$PATH" \
    "$root/scripts/run-profile.sh" story-start --project-root "$project" --codex "$@" > "$tmp/run.out" 2> "$tmp/run.err"
}

make_fake_codex "$tmp/bin"

project_with_spaces="$tmp/project with spaces"
run_profile_with_stub "$project_with_spaces"
assert_file_contains "$tmp/codex.args" "--model"
assert_file_contains "$tmp/codex.args" "gpt-5.4-mini"
assert_file_contains "$tmp/codex.args" "--cd"
assert_file_contains "$tmp/codex.args" "$project_with_spaces"
assert_file_contains "$tmp/codex.args" "agents.max_threads=3"
assert_file_contains "$tmp/codex.args" "agents.max_depth=1"
assert_file_contains "$tmp/codex.args" "agents.interrupt_message=false"
assert_file_contains "$tmp/codex.prompt" "delegate required high-risk"
assert_file_contains "$tmp/codex.prompt" "avoid one subagent per skill"
assert_file_contains "$tmp/codex.prompt" "Child agents must not delegate further"
assert_file_contains "$tmp/codex.prompt" "needs_model_escalation"
assert_file_contains "$project_with_spaces/.codex/agents/mana-full-specialist.toml" 'model = "gpt-5.6-sol"'
assert_file_contains "$project_with_spaces/.codex/agents/mana-explorer.toml" 'model = "gpt-5.6-terra"'
assert_file_contains "$project_with_spaces/.codex/agents/mana-worker.toml" 'model = "gpt-5.6-terra"'

override_project="$tmp/override project"
run_profile_with_stub "$override_project" \
  --codex-model root-mini \
  --codex-full-model full-sol \
  --codex-explorer-model explorer-terra \
  --codex-worker-model worker-terra
assert_file_contains "$tmp/codex.args" "root-mini"
assert_file_contains "$override_project/.codex/agents/mana-full-specialist.toml" 'model = "full-sol"'
assert_file_contains "$override_project/.codex/agents/mana-explorer.toml" 'model = "explorer-terra"'
assert_file_contains "$override_project/.codex/agents/mana-worker.toml" 'model = "worker-terra"'

disabled_project="$tmp/disabled project"
run_profile_with_stub "$disabled_project" --no-codex-subagents
assert_file_contains "$tmp/codex.prompt" "Codex subagents enabled: false"
assert_file_contains "$tmp/codex.prompt" "legacy economy-first/manual-escalation behavior"

jira_project="$tmp/jira project"
mkdir -p "$jira_project/.mana"
printf 'JIRA_URL=https://jira.example.invalid\nJIRA_PERSONAL_TOKEN=dummy\n' > "$jira_project/.mana/jira-mcp.env"
run_profile_with_stub "$jira_project"
assert_file_contains "$tmp/codex.args" "agents.max_threads=3"
assert_file_contains "$tmp/codex.args" "mcp_servers.jira.command="
assert_file_contains "$tmp/codex.args" "mcp_servers.jira.args=[\"--env-file\",\"$jira_project/.mana/jira-mcp.env\"]"

bootstrap_project="$tmp/bootstrap project"
mkdir -p "$bootstrap_project"
"$root/scripts/bootstrap-project.sh" --project-root "$bootstrap_project" --mana-root "$root" --no-jira-env > "$tmp/bootstrap1.out" 2> "$tmp/bootstrap1.err"
"$root/scripts/bootstrap-project.sh" --project-root "$bootstrap_project" --mana-root "$root" --no-jira-env > "$tmp/bootstrap2.out" 2> "$tmp/bootstrap2.err"
assert_file_contains "$bootstrap_project/.codex/agents/mana-explorer.toml" "Mana-managed Codex custom agent"
assert_file_contains "$bootstrap_project/.codex/agents/mana-full-specialist.toml" 'name = "mana_full_specialist"'
assert_file_contains "$bootstrap_project/.codex/config.toml" "max_threads = 3"
assert_file_contains "$bootstrap_project/AGENTS.md" "Do not create one Codex subagent per Mana skill"

config_project="$tmp/config project"
mkdir -p "$config_project/.codex/agents"
printf '# user config\nmodel = "custom"\n' > "$config_project/.codex/config.toml"
printf '# user agent\nname = "custom_agent"\n' > "$config_project/.codex/agents/custom.toml"
printf '# user-owned collision\nname = "mana_explorer"\n' > "$config_project/.codex/agents/mana-explorer.toml"
"$root/scripts/bootstrap-project.sh" --project-root "$config_project" --mana-root "$root" --no-jira-env > "$tmp/bootstrap-collision.out" 2> "$tmp/bootstrap-collision.err"
assert_file_contains "$config_project/.codex/config.toml" 'model = "custom"'
assert_file_contains "$config_project/.codex/agents/custom.toml" 'name = "custom_agent"'
assert_file_contains "$config_project/.codex/agents/mana-explorer.toml" "user-owned collision"
assert_file_contains "$tmp/bootstrap-collision.err" "not replacing existing non-managed file"

managed_force_project="$tmp/managed force project"
mkdir -p "$managed_force_project/.codex/agents"
printf '# Mana-managed Codex custom agent.\nname = "old"\n' > "$managed_force_project/.codex/agents/mana-worker.toml"
"$root/scripts/bootstrap-project.sh" --project-root "$managed_force_project" --mana-root "$root" --no-jira-env --force > "$tmp/bootstrap-force.out" 2> "$tmp/bootstrap-force.err"
assert_file_contains "$managed_force_project/.codex/agents/mana-worker.toml" 'name = "mana_worker"'

nolinks_project="$tmp/nolinks project"
mkdir -p "$nolinks_project"
"$root/scripts/bootstrap-project.sh" --project-root "$nolinks_project" --mana-root "$root" --no-links --no-jira-env > "$tmp/bootstrap-nolinks.out" 2> "$tmp/bootstrap-nolinks.err"
[ ! -L "$nolinks_project/.codex/agents/mana-explorer.toml" ] || fail "--no-links should copy Codex agents, not symlink them"
assert_file_contains "$nolinks_project/.codex/agents/mana-explorer.toml" 'name = "mana_explorer"'

metadata_root="$tmp/metadata-root"
mkdir -p "$metadata_root/skills/valid" "$metadata_root/skills/invalid-model" "$metadata_root/skills/invalid-mode" "$metadata_root/skills/invalid-group" "$metadata_root/skills/invalid-parallel" "$metadata_root/skills/legacy"
base_skill='---
name: sample
version: 1.0.0
description: sample
compatibility:
  - codex
preferred_runner: codex
allowed_tools:
  - read_files
inputs:
  - input
outputs:
  - output
risk_level: low
owner_role: Team
stack:
  - any
tags:
  - test
---
# Sample'
printf '%s\nmodel_tier: economy\nexecution_mode: read\ndelegation_group: requirements\nparallel_safe: true\n' "$base_skill" > "$metadata_root/skills/valid/SKILL.md"
printf '%s\n' "$base_skill" > "$metadata_root/skills/legacy/SKILL.md"
"$root/scripts/validate-skills.sh" "$metadata_root" > "$tmp/metadata-valid.out"
assert_file_contains "$tmp/metadata-valid.out" "Skills validation passed"
printf '%s\nmodel_tier: huge\n' "$base_skill" > "$metadata_root/skills/invalid-model/SKILL.md"
if "$root/scripts/validate-skills.sh" "$metadata_root" > "$tmp/metadata-invalid-model.out" 2>&1; then fail "invalid model_tier passed"; fi
assert_file_contains "$tmp/metadata-invalid-model.out" "invalid model_tier"
rm -rf "$metadata_root/skills/invalid-model"
printf '%s\nexecution_mode: mutate\n' "$base_skill" > "$metadata_root/skills/invalid-mode/SKILL.md"
if "$root/scripts/validate-skills.sh" "$metadata_root" > "$tmp/metadata-invalid-mode.out" 2>&1; then fail "invalid execution_mode passed"; fi
assert_file_contains "$tmp/metadata-invalid-mode.out" "invalid execution_mode"
rm -rf "$metadata_root/skills/invalid-mode"
printf '%s\ndelegation_group: chaos\n' "$base_skill" > "$metadata_root/skills/invalid-group/SKILL.md"
if "$root/scripts/validate-skills.sh" "$metadata_root" > "$tmp/metadata-invalid-group.out" 2>&1; then fail "invalid delegation_group passed"; fi
assert_file_contains "$tmp/metadata-invalid-group.out" "invalid delegation_group"
rm -rf "$metadata_root/skills/invalid-group"
printf '%s\nparallel_safe: maybe\n' "$base_skill" > "$metadata_root/skills/invalid-parallel/SKILL.md"
if "$root/scripts/validate-skills.sh" "$metadata_root" > "$tmp/metadata-invalid-parallel.out" 2>&1; then fail "invalid parallel_safe passed"; fi
assert_file_contains "$tmp/metadata-invalid-parallel.out" "invalid parallel_safe"

echo "Codex subagent regression tests passed"
