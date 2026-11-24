#!/usr/bin/env python3
"""Publish an explicitly selected Mana artifact bundle to a configured vault."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
from lib.project_config import ConfigError, contains, resolve

MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
DIAGRAM = re.compile(r"(?:entry-0[2-8]\.)?sequence\.puml")
REPORT_HEADINGS = {
    "# Java/Spring transaction investigation",
    "# Comparative Java/Spring transaction investigation",
}
MACHINE_PATH = re.compile(
    r"(?<![\w./:])(?:file:/|[A-Za-z]:[/\\]|\\\\[^\\\s]+\\|//[^/\s]+/)"
    r"|(?<![\w./:<])/(?=[^/\s`'\"<>])",
    re.IGNORECASE,
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_artifact(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ConfigError(f"{name}: expected a regular artifact file")
        data = source.read(MAX_ARTIFACT_BYTES + 1)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ConfigError(f"{name}: artifact exceeds the export size limit")
        return data


def portable_report(raw, project, project_id, diagrams):
    lines = raw.decode("utf-8").splitlines()
    if not lines or lines[0] not in REPORT_HEADINGS:
        raise ConfigError("report.md: expected a transaction investigation report")
    label = str(project).replace("`", "'").replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    project_lines = {line for line in lines if line.startswith("- Project: `")}
    if project_lines != {f"- Project: `{label}`"}:
        raise ConfigError("report.md: investigation belongs to a different project")
    portable = []
    evidence_section = False
    for line in lines:
        if line in {"## Evidence and reproduction commands", "### Evidence and reproduction commands"}:
            evidence_section = True
            continue
        if line.startswith("## ") and not line.startswith("### "):
            evidence_section = False
        if not evidence_section and not line.startswith("- Project: `"):
            portable.append(line)
    portable.extend(["", f"Project: `{project_id}`", "", "## Exported diagrams", ""])
    portable.extend(f"- [{name}](./{name})" for name in diagrams)
    return ("\n".join(portable) + "\n").encode()


def bundle(source, project, project_id):
    fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        manifest = json.loads(read_artifact(fd, "entries.json"))
        if not isinstance(manifest, dict) or manifest.get("schema") != "mana.transaction-investigation-entries/v1":
            raise ConfigError("entries.json: expected transaction investigation manifest")
        if "projectRoot" in manifest and manifest["projectRoot"] != str(project):
            raise ConfigError("entries.json: investigation belongs to a different project")
        entries = manifest.get("entries")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 8:
            raise ConfigError("entries.json: expected one to eight entries")
        diagrams = {}
        for entry in entries:
            name = entry.get("sequenceDiagram") if isinstance(entry, dict) else None
            if not isinstance(name, str) or not DIAGRAM.fullmatch(name) or name in diagrams:
                raise ConfigError("entries.json: unexpected or repeated sequence diagram")
            raw = read_artifact(fd, name)
            if digest(raw) != entry.get("sequenceDiagramSha256"):
                raise ConfigError(f"{name}: diagram digest differs from the investigation manifest")
            diagrams[name] = raw
        raw_report = read_artifact(fd, "report.md")
        if ("projectRoot" in manifest or "reportSha256" in manifest) and digest(raw_report) != manifest.get("reportSha256"):
            raise ConfigError("report.md: digest differs from the investigation manifest")
        report = portable_report(raw_report, project, project_id, diagrams)
        payloads = {"report.md": report, **diagrams}
        machine_roots = {str(Path(project)), str(source.absolute()), str(Path.home())} - {"/"}
        for name, raw in payloads.items():
            text = raw.decode("utf-8")
            if MACHINE_PATH.search(text) or any(root + "/" in text for root in machine_roots):
                raise ConfigError(f"{name}: contains a machine-specific path")
        return payloads
    finally:
        os.close(fd)


def existing_matches(destination, payloads):
    try:
        fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ConfigError("export destination exists and is not a directory") from exc
    try:
        same = all(read_artifact(fd, name) == raw for name, raw in payloads.items())
    except (ConfigError, OSError) as exc:
        raise ConfigError("export destination conflicts with the selected artifacts") from exc
    finally:
        os.close(fd)
    if not same:
        raise ConfigError("export destination has modified artifacts; existing files were preserved")
    return True


def staging_class():
    spec = importlib.util.spec_from_file_location(
        "mana_export_fs", Path(__file__).with_name("lib") / "context-runtime.py"
    )
    fs = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = fs
    spec.loader.exec_module(fs)
    return fs.PrivateStagingDirectory, fs.ContractError


def publish(vault, parent, name, payloads):
    staging, contract_error = staging_class()
    stage = staging.create(vault, parent, name)
    try:
        for artifact, raw in payloads.items():
            stage.write_bytes(artifact, raw)
        try:
            stage.publish_noreplace(name)
        except contract_error as exc:
            if isinstance(exc.__cause__, FileExistsError) and existing_matches(vault / parent / name, payloads):
                return "unchanged"
            raise
        stage.commit_publication()
        return "exported"
    finally:
        try:
            stage.cleanup()
        finally:
            stage.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("kind", choices=["transaction"])
    parser.add_argument("--from", dest="source", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="write the previewed bundle")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result, scope = resolve(args.project_root)
        settings = result["settings"]
        vault_alias = settings.get("export.vault", {}).get("value")
        project_id = settings.get("project.id", {}).get("value")
        if not vault_alias or not project_id:
            raise ConfigError("export requires export.vault and a leaf project.id")
        vault = scope["vaults"][vault_alias]
        if not vault.is_dir():
            raise ConfigError(f"vault alias {vault_alias} does not point to an existing directory")
        payloads = bundle(args.source, result["projectRoot"], project_id)
        relative = Path(result["projectRoot"]).relative_to(result["workspaceRoot"])
        namespace = digest(f"{scope['name']}\0{relative.as_posix()}".encode())[:16]
        parent = f"Mana/{project_id}-{namespace}/Transactions"
        identity = digest(json.dumps({name: digest(raw) for name, raw in payloads.items()}, sort_keys=True).encode())
        name = f"analysis-{identity}"
        destination = vault / parent / name
        if contains(Path(result["projectRoot"]), destination):
            raise ConfigError("export destination must be outside the project directory")
        status = "preview"
        if args.apply:
            status = publish(vault, parent, name, payloads)
        output = {
            "status": status,
            "source": str(args.source.absolute()),
            "destination": str(destination),
            "files": list(payloads),
        }
        if args.json:
            print(json.dumps(output))
        else:
            print(f"{status}: {output['source']} -> {destination}")
            for artifact in payloads:
                print(f"  {artifact}")
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
