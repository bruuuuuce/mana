#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
profile=""
project_root=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root)
      project_root="${2:-}"
      [ -n "$project_root" ] || { echo "ERROR: --project-root requires a path" >&2; exit 2; }
      shift 2
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
    echo "Usage: scripts/run-profile.sh <profile-name> [--project-root <path>]"
    exit 2
  fi
fi

file="$root/profiles/${profile}.yaml"
if [ ! -f "$file" ]; then echo "ERROR: profile not found: $profile"; exit 1; fi

"$root/scripts/mana-update-check.sh" --root "$root" --profile "$profile" || exit 1

echo "Profile: $profile"
echo "This profile renderer validates Mana freshness and prints the configured profile."
echo "It does not execute the listed agents or skills autonomously."
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
