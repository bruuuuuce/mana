#!/usr/bin/env python3
"""MANA-META-SKILL-00: deterministic, offline, candidate-only skill factory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# Prevent local adapter bytecode caches from writing into an analyzed Mana checkout.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
# Also support programmatic loading from a host outside scripts/.
sys.path.insert(0, str(ROOT / "scripts"))
from skill_factory import ADAPTERS  # noqa: E402 - suppress caches before local imports
from skill_factory.contracts import DOMAIN_FIELDS, FactoryError, SkillAdapter  # noqa: E402

FORBIDDEN = {
    "skills",
    "agents",
    "profiles",
    ".git",
    ".codex",
    ".claude",
    ".junie",
    ".opencode",
}
SKIP = FORBIDDEN | {"target", "build", "out", "node_modules", "vendor", "dist"}
MAX_FILES = 5000
MAX_BYTES = 1024 * 1024
MAX_TOTAL = 32 * MAX_BYTES
MAX_JSON_DEPTH = 32
MAX_JSON_TOKENS = 20000


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_project(project: Path) -> Path:
    try:
        project = project.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise FactoryError("project root cannot be resolved") from exc
    if not project.is_dir():
        raise FactoryError("project root must be a directory")
    return project


def read_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FactoryError(f"not a regular file: {path}")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or b"\0" in raw:
        raise FactoryError(f"oversized or binary input: {path}")
    raw.decode("utf-8")
    return raw


def project_files(project: Path, adapter: SkillAdapter) -> dict[str, bytes]:
    """Bounded read-only inventory, filtered by the selected trusted adapter."""
    files = {}
    count = total = 0
    for directory, dirs, names in os.walk(project, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and d not in SKIP
            and not (Path(directory) / d).is_symlink()
        )
        for name in sorted(names):
            if name.startswith("."):
                continue
            count += 1
            if count > MAX_FILES:
                raise FactoryError(
                    "file inventory budget exceeded; no partial detection"
                )
            path = Path(directory) / name
            if (
                name not in adapter.evidence_names
                and path.suffix not in adapter.evidence_suffixes
            ):
                continue
            if path.is_symlink():
                continue
            raw = read_file(path)
            total += len(raw)
            if total > MAX_TOTAL:
                raise FactoryError("read budget exceeded; no partial detection")
            files[path.relative_to(project).as_posix()] = raw
    return files


def candidate_location(path: Path, project: Path) -> Path:
    absolute = path.absolute()
    # Check lexical and resolved paths, including symlink aliases to discovery roots.
    resolved = absolute.resolve()
    if (set(absolute.parts) | set(resolved.parts)) & FORBIDDEN:
        raise FactoryError(
            "candidate location intersects a discovery/configuration surface"
        )
    if resolved == project or project in resolved.parents:
        raise FactoryError("candidate output must be outside the analyzed project")
    if any(p.is_symlink() for p in [absolute, *absolute.parents]):
        # /tmp is a standard macOS alias; callers should pass its canonical path.
        raise FactoryError(
            "candidate location must not contain symlinks; use a canonical path"
        )
    return resolved


def adapter_for(request: str | None) -> SkillAdapter:
    matches = [a for a in ADAPTERS if request is None or a.request == request]
    if len(matches) != 1:
        raise FactoryError(f"unsupported or ambiguous specialist request: {request!r}")
    adapter = matches[0]
    if (
        not isinstance(adapter.skill_id, str)
        or len(adapter.skill_id) > 63
        or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", adapter.skill_id) is None
    ):
        raise FactoryError("adapter skill_id must be a safe lowercase skill identifier")
    return adapter


def bounded_json(raw: bytes):
    """Iterative lexical budgets before the standard, depth-bounded JSON parser."""
    if len(raw) > MAX_BYTES:
        raise FactoryError(f"JSON byte limit exceeded: {MAX_BYTES}")
    text = raw.decode("utf-8")
    depth = tokens = 0
    quoted = escaped = atom = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char.isspace():
            atom = False
            continue
        if char == '"':
            quoted = True
            atom = False
            tokens += 1
        elif char in "{}[]:,":
            atom = False
            tokens += 1
            if char in "{[":
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    raise FactoryError(f"JSON depth limit exceeded: {MAX_JSON_DEPTH}")
            elif char in "}]":
                depth -= 1
        elif not atom:
            tokens += 1
            atom = True
        if tokens > MAX_JSON_TOKENS:
            raise FactoryError(f"JSON token limit exceeded: {MAX_JSON_TOKENS}")

    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise FactoryError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def invalid_constant(value):
        raise FactoryError(f"invalid JSON constant: {value}")

    try:
        return json.loads(
            text, object_pairs_hook=unique_keys, parse_constant=invalid_constant
        )
    except FactoryError:
        raise
    except (ValueError, RecursionError) as exc:
        raise FactoryError("malformed or excessively complex JSON") from exc


def manifest(project: Path, adapter: SkillAdapter) -> dict:
    domain = adapter.specialize(project_files(project, adapter))
    if set(domain) != DOMAIN_FIELDS:
        raise FactoryError("adapter contract has missing or unexpected domain fields")
    # Only the host owns lifecycle/trust fields, never the selected domain recipe.
    return {
        "schema": "mana.skill-candidate/v1",
        "skillId": adapter.skill_id,
        "status": "candidate",
        "trustOrigin": "generated",
        "trusted": False,
        "executable": False,
        "registered": False,
        "approval": {
            "required": True,
            "status": "pending",
            "ownerRole": "Architect / Team Leader",
        },
        "request": adapter.request,
        **domain,
        "skillSha256": digest(read_file(adapter.template)),
    }


def temporary_parent(project: Path) -> Path:
    # tempfile.gettempdir() probes candidates by WRITING. Resolve/check first instead.
    project = canonical_project(project)
    selected = next(
        (os.environ[k] for k in ("TMPDIR", "TEMP", "TMP") if os.environ.get(k)), None
    )
    if selected is None:
        if os.name != "posix":
            raise FactoryError(
                "configure an existing external temporary parent with TMPDIR"
            )
        selected = "/tmp"
    lexical = Path(selected).absolute()
    try:
        parent = lexical.resolve()
    except (OSError, RuntimeError) as exc:
        raise FactoryError(f"temporary parent cannot be resolved: {lexical}") from exc
    if parent == project or project in parent.parents:
        raise FactoryError(f"temporary parent is inside analyzed project: {parent}")
    if (set(lexical.parts) | set(parent.parts)) & FORBIDDEN:
        raise FactoryError(
            f"temporary parent intersects discovery/configuration surface: {parent}"
        )
    if not parent.is_dir():
        raise FactoryError(f"temporary parent must already exist: {parent}")
    return parent


def check_mana_contract(skill: bytes, project: Path, adapter: SkillAdapter) -> None:
    parent = temporary_parent(project)
    with tempfile.TemporaryDirectory(
        prefix="mana-skill-contract-", dir=parent
    ) as temporary:
        stage = Path(temporary)
        directory = stage / "skills" / adapter.skill_id
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_bytes(skill)
        # Subprocesses get the same isolated canonical temp and working directory.
        # No host-global environment mutation, shell startup instructions or target cwd.
        env = {k: v for k, v in os.environ.items() if k not in {"BASH_ENV", "ENV"}}
        env.update({"TMPDIR": str(stage), "TEMP": str(stage), "TMP": str(stage)})
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/validate-skills.sh"), str(stage)],
            capture_output=True,
            text=True,
            check=False,
            cwd=stage,
            env=env,
        )
        if result.returncode:
            raise FactoryError(
                f"Mana contract rejected candidate: {result.stderr.strip()}"
            )


def validate(project: Path, directory: Path) -> dict:
    project = canonical_project(project)
    directory = candidate_location(directory, project)
    if not directory.is_dir() or {p.name for p in directory.iterdir()} != {
        "SKILL.md",
        "candidate.json",
    }:
        raise FactoryError(
            "candidate bundle must contain only SKILL.md and candidate.json"
        )
    skill = read_file(directory / "SKILL.md")
    candidate = bounded_json(read_file(directory / "candidate.json"))
    if not isinstance(candidate, dict) or not isinstance(candidate.get("request"), str):
        raise FactoryError("candidate must be an object with a specialist request")
    adapter = adapter_for(candidate["request"])
    expected = manifest(project, adapter)
    if json.dumps(candidate, sort_keys=True) != json.dumps(
        expected, sort_keys=True
    ) or skill != read_file(adapter.template):
        raise FactoryError(
            "candidate contract or source evidence changed; regenerate for review"
        )
    check_mana_contract(skill, project, adapter)
    return {
        "status": "valid",
        "skillId": adapter.skill_id,
        "approval": "pending",
        "executable": False,
    }


def generate(project: Path, directory: Path, request: str | None = None) -> dict:
    project = canonical_project(project)
    directory = candidate_location(directory, project)
    if directory.exists():
        raise FactoryError("candidate output already exists; refusing overwrite")
    adapter = adapter_for(request)
    value = manifest(project, adapter)
    payload = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    bounded_json(payload)
    skill = read_file(adapter.template)
    check_mana_contract(skill, project, adapter)
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700)
    try:
        (directory / "SKILL.md").write_bytes(skill)
        (directory / "candidate.json").write_bytes(payload)
        return validate(project, directory)
    except Exception:
        for name in ("SKILL.md", "candidate.json"):
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "validate"):
        child = commands.add_parser(command)
        child.add_argument("--project-root", required=True, type=Path)
        child.add_argument("--candidate-dir", required=True, type=Path)
        if command == "generate":
            child.add_argument("--request", required=True)
    args = parser.parse_args()
    try:
        project = canonical_project(args.project_root)
        if args.command == "generate":
            result = generate(project, args.candidate_dir, args.request)
        else:
            result = validate(project, args.candidate_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (FactoryError, OSError, UnicodeError, ValueError, RecursionError) as exc:
        print(
            json.dumps({"status": "blocked", "reason": str(exc), "executable": False}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
