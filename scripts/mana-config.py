#!/usr/bin/env python3
"""Read the effective Mana project configuration."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from lib.project_config import ConfigError, resolve


def profile_options(result, scope, args):
    prefix = f"profiles.{args.profile}."
    settings = result["settings"]
    mode = settings.get(prefix + "runtime")
    if mode and not args.explicit_runtime:
        if mode["value"] != "legacy" and not scope["allow_runtime"]:
            raise ConfigError(f"{mode['source']}: {prefix}runtime requires allow_runtime = true")
        print(f"runtime {mode['value']}")
    skill_prefix = prefix + "skills."
    preferred = sorted(key[len(skill_prefix):] for key, value in settings.items()
                       if key.startswith(skill_prefix) and value["value"])
    if not preferred:
        return
    base = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("mana_config_runtime", base / "lib" / "context-runtime.py")
    compiler = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = compiler
    spec.loader.exec_module(compiler)
    profile = base.parent / "profiles" / f"{args.profile}.yaml"
    if not compiler.IDENTIFIER.fullmatch(args.profile):
        raise ConfigError("invalid profile identifier")
    text = compiler._host_text(profile, "profile")
    mode, baseline, conditional = compiler._parse_skill_activation(text, args.profile)
    if mode == "legacy-fallback":
        baseline = compiler._top_level_list(text, "skills", "profile")
    explicit = set(args.request_skill) | {conditional.get(signal) for signal in args.static_signal}
    for skill in preferred:
        if skill in explicit or skill in baseline:
            continue
        if skill not in conditional.values():
            value = settings[skill_prefix + skill]
            raise ConfigError(f"{value['source']}: {skill_prefix}{skill}: expected a conditional profile skill")
        print(f"skill {skill}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("command", choices=["explain", "profile-options"])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--profile")
    parser.add_argument("--explicit-runtime", action="store_true")
    parser.add_argument("--request-skill", action="append", default=[])
    parser.add_argument("--static-signal", action="append", default=[])
    args = parser.parse_args()
    try:
        result, scope = resolve(args.project_root)
        if args.command == "profile-options":
            if not args.profile:
                parser.error("profile-options requires --profile")
            profile_options(result, scope, args)
            return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"Project configuration: {result['reason']}")
        if result["workspaceRoot"]:
            print(f"Workspace root: {result['workspaceRoot']}")
        print("Defaults: legacy runtime, manual export")
        for key, entry in sorted(result["settings"].items()):
            print(f"{key} = {json.dumps(entry['value'])} ({entry['source']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
