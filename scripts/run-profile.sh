#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
profile=""
project_root=""
render_only=false
runner=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root)
      project_root="${2:-}"
      [ -n "$project_root" ] || { echo "ERROR: --project-root requires a path" >&2; exit 2; }
      shift 2
      ;;
    --render-only)
      render_only=true
      shift
      ;;
    --codex)
      [ -z "$runner" ] || { echo "ERROR: choose only one runner flag" >&2; exit 2; }
      runner="codex"
      shift
      ;;
    --claude)
      [ -z "$runner" ] || { echo "ERROR: choose only one runner flag" >&2; exit 2; }
      runner="claude"
      shift
      ;;
    --*)
      echo "ERROR: unknown option: $1" >&2
      exit 2
      ;;
    *)
      if [ -z "$profile" ]; then
        profile="$1"
        shift
      else
        echo "ERROR: unexpected argument: $1" >&2
        exit 2
      fi
      ;;
  esac
done

if [ -z "$profile" ]; then
  active_file="${project_root:-.}/.mana/active-profile"
  if [ -f "$active_file" ]; then
    profile="$(tr -d '[:space:]' < "$active_file")"
    echo "Using active profile: $profile (from .mana/active-profile)"
  else
    echo "Usage: scripts/run-profile.sh <profile-name> [--codex|--claude|--render-only] [--project-root <path>]"
    exit 2
  fi
fi

file="$root/profiles/${profile}.yaml"
if [ ! -f "$file" ]; then echo "ERROR: profile not found: $profile"; exit 1; fi

if [ -z "$project_root" ]; then
  project_root="$(pwd)"
fi

if [ "$render_only" = true ] && [ -n "$runner" ]; then
  echo "ERROR: --render-only cannot be combined with --$runner" >&2
  exit 2
fi

"$root/scripts/mana-update-check.sh" --root "$root" --profile "$profile" || exit 1

echo "Profile: $profile"
echo "This profile renderer validates Mana freshness and prints the configured profile."
echo "Use --codex or --claude to execute the profile through a runner."
sed -n '1,220p' "$file"
echo
echo "Workspace note: profiles use the project-local .mana workspace. Run scripts/mana-workspace.sh init in the target project before agent execution when artifacts must be persisted."

hooks_config=""
if [ -n "$project_root" ] && [ -f "$project_root/.mana/global/hooks-config.yaml" ]; then
  hooks_config="$project_root/.mana/global/hooks-config.yaml"
fi

if [ -n "$hooks_config" ]; then
  trigger="$(grep '^trigger:' "$file" | awk '{print $2}' | tr -d '"' | head -n 1)"
  if [ -n "$trigger" ]; then
    disabled_skills="$(awk -v section="$trigger" '
      /^hooks:/ { in_hooks=1; next }
      in_hooks && $0 ~ "^  " section ":" { in_section=1; next }
      in_hooks && in_section && /^    disabled_skills:/ { in_skills=1; in_agents=0; next }
      in_hooks && in_section && /^    disabled_agents:/ { in_agents=1; in_skills=0; next }
      in_hooks && in_section && in_skills && /^      - / { sub(/^      - /, ""); print }
      in_hooks && in_section && /^  [a-z_]+:/ { in_section=0; in_skills=0; in_agents=0 }
    ' "$hooks_config")"
    disabled_agents="$(awk -v section="$trigger" '
      /^hooks:/ { in_hooks=1; next }
      in_hooks && $0 ~ "^  " section ":" { in_section=1; next }
      in_hooks && in_section && /^    disabled_skills:/ { in_skills=1; in_agents=0; next }
      in_hooks && in_section && /^    disabled_agents:/ { in_agents=1; in_skills=0; next }
      in_hooks && in_section && in_agents && /^      - / { sub(/^      - /, ""); print }
      in_hooks && in_section && /^  [a-z_]+:/ { in_section=0; in_skills=0; in_agents=0 }
    ' "$hooks_config")"

    if [ -n "$disabled_skills" ] || [ -n "$disabled_agents" ]; then
      echo
      echo "Project hooks-config.yaml overrides ($project_root/.mana/global/hooks-config.yaml):"
      if [ -n "$disabled_skills" ]; then
        echo "  Disabled skills for $trigger:"
        echo "$disabled_skills" | while IFS= read -r s; do echo "    DISABLED: $s"; done
      fi
      if [ -n "$disabled_agents" ]; then
        echo "  Disabled agents for $trigger:"
        echo "$disabled_agents" | while IFS= read -r a; do echo "    DISABLED: $a"; done
      fi
    else
      echo
      echo "Project hooks-config.yaml: no overrides for $trigger (all framework defaults active)."
    fi
  fi
fi

if [ "$render_only" = true ] || [ "${MANA_PROFILE_RUNNING:-}" = "1" ] || [ -z "$runner" ]; then
  if [ "$render_only" = true ]; then
    echo
    echo "Execution note: --render-only requested; no runner was started."
  elif [ "${MANA_PROFILE_RUNNING:-}" = "1" ]; then
    echo
    echo "Execution note: already inside a Mana profile runner; no nested runner was started."
  else
    echo
    echo "Execution note: no runner flag was provided, so no runner was started."
    echo "Run with --codex or --claude to execute the profile through that runner."
  fi
  exit 0
fi

prompt="$(cat <<PROMPT
Run the Mana profile '$profile' in this repository.

Repository root: $project_root
Mana framework root: $root
Selected runner: $runner

Instructions:
- Do not run './mana profile $profile' or 'scripts/run-profile.sh $profile' again; this command already rendered the profile and would recurse.
- Read '.mana/links/profiles/$profile.yaml' if present, otherwise '$file'.
- Read the listed agent AGENT.md and playbook.md. Load only the primary skill required to start the profile, then load specialist skills only when the filtered inputs show that their risk domain is relevant. Do not read every listed skill up front.
- Resolve the active .mana workspace and write the profile artifacts there using the agent routing rules.
- Load .mana/global/service-mission.md, architecture.md, and engineering-guards.md when present before analysis.
- For jessica-fletcher, resolve the main branch first, compare the full local branch changes against it, include uncommitted working-tree changes, and stop with a clear question if the main branch is ambiguous.
- For any profile using branch or code diff evidence, resolve and report the comparison base. Prefer explicit input, then origin/HEAD, then a single credible primary branch. If ambiguous, ask the user; do not default to main.
- For any profile using branch or code diff evidence, start with a filtered diff inventory, exclude Mana/bootstrap noise, classify changed files by risk domain, and read only files needed to validate plausible blocker or warning hypotheses. If the filtered diff is larger than roughly 80 files or 2,000 changed lines, ask the user to choose a review scope instead of scanning the whole repository.
- Exclude Mana framework/bootstrap noise from production findings and evidence: .mana/**, AGENTS.md, CLAUDE.md, mana, and Mana-only .gitignore or env ignore changes. Mention them only as operational setup notes when relevant.
- Do not commit, push, deploy, trigger CI, write to external systems, or make destructive changes.
- Final response must summarize status, blockers, warnings, artifact paths, and any required human approval.
PROMPT
)"

case "$runner" in
  codex)
    if ! command -v codex >/dev/null 2>&1; then
      echo "ERROR: --codex requested, but codex was not found in PATH" >&2
      exit 1
    fi

    echo
    echo "Starting Codex runner for profile: $profile"
    MANA_PROFILE_RUNNING=1 codex --ask-for-approval on-request exec --cd "$project_root" --sandbox workspace-write "$prompt"
    ;;
  claude)
    if ! command -v claude >/dev/null 2>&1; then
      echo "ERROR: --claude requested, but claude was not found in PATH" >&2
      exit 1
    fi

    echo
    echo "Starting Claude runner for profile: $profile"
    cd "$project_root" || exit 1
    MANA_PROFILE_RUNNING=1 claude -p --permission-mode default "$prompt"
    ;;
  *)
    echo "ERROR: unsupported runner: $runner" >&2
    exit 2
    ;;
esac
