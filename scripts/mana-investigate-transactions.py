#!/usr/bin/env python3
"""Run a conservative, read-only Java/Spring transaction investigation."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


t01 = load_script("mana_investigation_t01", ROOT / "scripts/mana-transaction.py")
resource_cli = load_script("mana_investigation_resources", ROOT / "scripts/mana-resource-timeline.py")
wait_cli = load_script("mana_investigation_wait", ROOT / "scripts/mana-wait-dependencies.py")
from skill_factory.transactions.plantuml import render  # noqa: E402
from skill_factory.transactions.plantuml import render_integrated  # noqa: E402
from skill_factory.transactions.resources import validate_timeline  # noqa: E402


def default_context():
    return {
        "schema": "mana.transaction-context/v1",
        "initialState": "UNKNOWN",
        "entryThroughProxy": False,
        "managerCapabilities": {},
    }


def source_revision(project):
    try:
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(project), "rev-parse", "HEAD"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
        )
        value = result.stdout.strip()
        return value if len(value) == 40 and all(c in "0123456789abcdef" for c in value) else "UNKNOWN"
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"


def md(value):
    return str(value).replace("`", "'").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def report_markdown(project, entry, revision, model, timeline, svg_status, context_origin, context_arg=None, wait_summary=None, wait_scenario=None, wait_timelines=(), proxy_alternatives=()):
    frames = model["frames"]
    depth = {frame["id"]: frame.get("depth", 0) for frame in frames}
    lines = [
        "# Java/Spring transaction investigation", "",
        "> Conditional static source analysis. Runtime interception, transaction identity, datasource enlistment, locks, and outcomes are not observed.", "",
        "## Entry point and source revision", "",
        f"- Entry: `{md(entry)}`", f"- Project: `{md(project)}`", f"- Source revision: `{revision}` (UNKNOWN means the project is not a readable Git checkout)",
        f"- Model status: `{model['status']}`; investigation context origin: `{context_origin}`; model context evidence: `{model['contextEvidence']['origin']}`", "",
        "## Transaction call tree", "",
    ]
    if not frames:
        lines.append("No supported method frames were reconstructed.")
    for frame in frames:
        cfg = frame.get("configuration") or {}
        ctx = frame["duringState"]
        physical_id = ctx.get("physicalId")
        creator = next((p for p in model["physicalTransactions"] if p["id"] == physical_id), None)
        physical_role = "new physical transaction" if creator and creator["beginFrame"] == frame["id"] else "inherited physical transaction" if physical_id else ctx["kind"]
        lines.append("  " * depth[frame["id"]] + f"- `{frame['calleeMethod']}` — {cfg.get('propagation', 'UNANNOTATED')}; {physical_role} `{physical_id or 'identity UNKNOWN'}`; interception {frame.get('interception', {}).get('status', 'UNKNOWN')}; {frame['certainty']}")
    lines += ["", "## Physical transaction identities", "", "Symbolic identities describe conditional model regions; they are not runtime transaction IDs.", ""]
    for physical in model["physicalTransactions"]:
        lines.append(f"- `{physical['id']}` manager `{physical.get('manager') or 'UNKNOWN'}`, begins at frame `{physical['beginFrame']}`, ends at `{physical.get('endFrame') or 'UNKNOWN'}`.")
    if not model["physicalTransactions"]:
        lines.append("No physical transaction identity is established by the conservative input context.")
    lines += ["", "## Propagation and interception boundaries", "", f"- Interception mode: `{model.get('interceptionMode', 'UNKNOWN')}`; proxy mode: `{model.get('proxyMode', 'UNKNOWN')}`.", "- Proxy entry, manager capabilities, datasource enlistment, savepoint support, runtime state, and AspectJ application are not inferred from source presence.", "- `--context` omitted: the v1 model requires a boolean `entryThroughProxy`; the generated conservative input sets it to false and `initialState` to UNKNOWN. This is an explicit scenario boundary, not a finding that runtime proxy interception is absent. Supply `--context` to model an evidenced alternative.", ""]
    if proxy_alternatives:
        lines += ["Default-context proxy entry alternatives (conditional; neither observed):", ""]
        for alternative in proxy_alternatives:
            lines.append(f"- `entryThroughProxy={str(alternative['entryThroughProxy']).lower()}`: {alternative['summary']}; frames={alternative['frameCount']}; UNKNOWN regions={len(alternative['uncertainties'])}.")
        lines.append("Confirm whether the selected method is entered through the configured Spring proxy before preferring either alternative.")
    for s in model["suspensions"]:
        lines.append(f"- `{s['physicalId']}` is conditionally suspended while `{s['replacementPhysicalId']}` executes, then may resume.")
    for s in model["savepoints"]:
        lines.append(f"- `{s['id']}` is a conditional savepoint on `{s['physicalId']}`; driver/runtime support remains an assumption.")
    lines += ["", "Transaction-state distinctions used in this report:", "", "- `NO_TRANSACTION` means no physical transaction is established in the selected conditional scenario.", "- An inherited physical transaction reuses the caller's symbolic physical identity.", "- A new physical transaction starts a separate symbolic identity; if it replaces an outer context, that outer identity is suspended and remains live until conditional resume.", "- A nested savepoint belongs to the same physical identity as its outer transaction.", "- Interception `UNKNOWN`, unresolved calls, and unsupported regions remain unknown; source annotations alone do not establish advice execution.", ""]
    lines += ["", "## Resource operations and chronological constraints", "", "JDBC source observations below are lexical matches from the supported analyzer. Placement follows T01's supported call frontier; database order and execution are not observed.", "", "| Source | Operation | Resource evidence | Transaction context | Enlistment / lock |", "|---|---|---|---|---|"]
    for obs in timeline["observations"]:
        site = obs["callSite"]
        context = obs["transactionContext"]
        sql = obs.get("sqlLiteral") or "dynamic or unsupported SQL"
        lines.append(f"| `{md(site['file'])}:{site['line']}` | {md(obs['operationType'])} `{md(obs['applicationOperation']['method'])}` | {md(sql)}; `{md(obs['resource'].get('name') or 'UNKNOWN')}` | {md(context['kind'])} `{md(context.get('physicalId') or 'UNKNOWN')}` | UNKNOWN / UNKNOWN |")
    if not timeline["observations"]:
        lines.append("No supported JDBC observations were recognized.")
    risk_summary = (f"Validated S02 scenario result: `{wait_summary['assessment']}`; coverage `{wait_summary['coverage']}`. Runtime remains NOT RUN; static evidence does not confirm a deadlock." if wait_summary else "No wait/deadlock scenario is derived from lexical SQL similarity. S02/VIS require structured scenario premises and do not turn static source into a confirmed deadlock.")
    lines += ["", "## Conditional concurrency risks", "", risk_summary, "", "Investigation checklist:", "", "- Identify runtime datasource and transaction-manager bindings for each observed operation.", "- Verify actual call reachability, proxy/AspectJ interception, propagation, and manager capabilities.", "- Establish database engine/version, isolation, lock modes, row/key overlap, and wait behavior.", "- Supply independently justified participant schedules and resource ownership premises before running S02/VIS.", "", "## Unknown or unsupported regions", ""]
    for uncertainty in model["uncertainties"]:
        lines.append(f"- {uncertainty.get('reason', uncertainty)}")
    for limit in timeline.get("limits", []):
        lines.append(f"- Resource timeline: {limit}")
    if not model["uncertainties"] and not timeline.get("limits"):
        lines.append("No additional uncertainty records; the global runtime and datasource limits above still apply.")
    lines += ["", "## Suggested developer verification steps", "", "1. Inspect the reported source sites and validate the reconstructed paths against real entry wiring.", "2. Confirm Spring proxy/AspectJ configuration and transaction-manager capabilities.", "3. Confirm the datasource bound to each JdbcTemplate and whether it participates in the modeled manager.", "4. Use runtime tracing or focused integration tests to establish actual transaction IDs, savepoints, SQL execution, and lock behavior.", "5. Prepare explicit structured premises before requesting conditional wait/deadlock diagrams.", ""]
    command = ["python3", str(ROOT / "scripts/mana-investigate-transactions.py"), "--project-root", str(project), "--entry", entry]
    if context_arg:
        command += ["--context", str(Path(context_arg).absolute())]
    if wait_scenario:
        command += ["--wait-scenario", str(Path(wait_scenario).absolute())]
        for value in wait_timelines:
            name, _, path = value.partition("=")
            command += ["--wait-timeline", name + "=" + str(Path(path).absolute())]
    command += ["--output-dir", "/private/tmp/mana-investigation-replay"]
    lines += ["## Evidence and reproduction commands", "", "- `transaction-model.json`: validated T01 machine-readable evidence.", "- `resource-timeline.json`: validated T02-S01 machine-readable evidence.", "- `sequence.puml`: generated using the existing T01 renderer; renderer status: " + svg_status + ".", "- `evidence.json`: source hashes and context digest.", "", "```sh", " ".join(shlex.quote(part) for part in command), "```", "", "Explicit scenario assumptions can be supplied with `--context PATH`; without it, initial transaction state and manager capabilities remain unknown. No output is written to the analyzed project.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--output-dir", type=Path, help="fresh external directory; defaults to a private system temporary directory")
    parser.add_argument("--wait-scenario", type=Path, help="optional explicit S02 scenario sidecar")
    parser.add_argument("--wait-timeline", action="append", default=[], metavar="ID=PATH", help="validated resource timeline input; repeat for each S02 participant input")
    args = parser.parse_args()
    output = None
    try:
        project = t01.factory.canonical_project(args.project_root)
        output = t01.factory.candidate_location(args.output_dir, project) if args.output_dir else None
        if output is not None and output.exists():
            raise ValueError("output already exists; refusing overwrite")
        revision = source_revision(project)
        wait_artifacts = {}
        wait_summary = None
        proxy_alternatives = []
        with tempfile.TemporaryDirectory(prefix="mana-investigate-") as scratch:
            scratch = Path(scratch)
            if args.context:
                context_path = args.context
                context_raw = t01.factory.read_file(context_path)
                context = t01.context_input(context_path, context_raw)
                context_origin = "EXPLICIT_SCENARIO_NOT_RUNTIME_PROOF"
            else:
                context = default_context()
                context_raw = (json.dumps(context, sort_keys=True) + "\n").encode()
                context_path = scratch / "context.json"
                context_path.write_bytes(context_raw)
                context_origin = "CONSERVATIVE_DEFAULT_NOT_RUNTIME_PROOF"
            model, facts = t01.analyze(project, context_path, args.entry, include_facts=True)
            timeline = resource_cli.build_timeline(model, facts)
            validate_timeline(timeline)
            diagram = render(model, timeline)
            if not args.context:
                alternate_context = dict(context)
                alternate_context["entryThroughProxy"] = True
                alternate_context_raw = (json.dumps(alternate_context, sort_keys=True) + "\n").encode()
                alternate_context_path = scratch / "context-proxy-true.json"
                alternate_context_path.write_bytes(alternate_context_raw)
                alternate_model, alternate_facts = t01.analyze(project, alternate_context_path, args.entry, include_facts=True)
                if alternate_model["evidence"] != model["evidence"]:
                    raise ValueError("source changed between conditional proxy alternatives")
                alternate_timeline = resource_cli.build_timeline(alternate_model, alternate_facts)
                validate_timeline(alternate_timeline)
                proxy_alternatives.append({
                    "entryThroughProxy": False,
                    "summary": "baseline model in transaction-model.json",
                    "frameCount": len(model["frames"]),
                    "uncertainties": [u["reason"] for u in model["uncertainties"]],
                    "physicalTransactions": len(model["physicalTransactions"]),
                    "resourceObservations": len(timeline["observations"]),
                })
                proxy_alternatives.append({
                    "entryThroughProxy": True,
                    "summary": "alternate model; runtime proxy crossing UNKNOWN",
                    "frameCount": len(alternate_model["frames"]),
                    "uncertainties": [u["reason"] for u in alternate_model["uncertainties"]],
                    "physicalTransactions": len(alternate_model["physicalTransactions"]),
                    "resourceObservations": len(alternate_timeline["observations"]),
                    "sourceEvidence": alternate_model["evidence"],
                    "contextSha256": hashlib.sha256(alternate_context_raw).hexdigest(),
                })
            if args.wait_scenario:
                raw_inputs = {}
                for value in args.wait_timeline:
                    name, sep, raw_path = value.partition("=")
                    if not sep or not name or name in raw_inputs:
                        raise ValueError("expected unique ID=PATH --wait-timeline arguments")
                    raw_inputs[name] = wait_cli.read_bounded(Path(raw_path), wait_cli.BUDGETS["timelineBytes"])
                    if sum(map(len, raw_inputs.values())) > wait_cli.BUDGETS["combinedBytes"]:
                        raise ValueError("combined S02 timeline byte budget exceeded")
                sidecar_path = args.wait_scenario
                sidecar_raw = wait_cli.read_bounded(sidecar_path, wait_cli.BUDGETS["sidecarBytes"])
                sidecar = wait_cli.parse_json(sidecar_raw, wait_cli.BUDGETS["sidecarBytes"])
                wait_report = wait_cli.build_report(raw_inputs, sidecar)
                wait_cli.validate_report(wait_report, raw_inputs)
                diagnostics, _ = wait_cli._derive_report(raw_inputs, sidecar)
                wait_artifacts.update({"wait-" + name: content for name, content in wait_cli.artifacts(wait_report, diagnostics).items()})
                wait_artifacts.update({"vis-" + name: content.encode("utf-8") for name, content in render_integrated(wait_report, raw_inputs).items()})
                wait_summary = {
                    "scenarioId": wait_report["scenario"]["id"],
                    "assessment": wait_report["assessment"]["result"],
                    "coverage": wait_report["coverage"]["status"],
                    "scenarioSha256": hashlib.sha256(sidecar_raw).hexdigest(),
                    "timelineInputs": [{"id": key, "sha256": hashlib.sha256(raw).hexdigest()} for key, raw in sorted(raw_inputs.items())],
                }
            elif args.wait_timeline:
                raise ValueError("--wait-timeline requires --wait-scenario")
        svg_result = "SVG not generated: PlantUML renderer unavailable or failed"
        artifacts = {
            "transaction-model.json": (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode(),
            "resource-timeline.json": (json.dumps(timeline, indent=2, ensure_ascii=False) + "\n").encode(),
            "sequence.puml": diagram.encode(),
            "context.json": context_raw,
            "evidence.json": (json.dumps({"sourceRevision": revision, "contextOrigin": context_origin, "sourceEvidence": model["evidence"], "contextSha256": hashlib.sha256(context_raw).hexdigest(), "proxyEntryAlternatives": proxy_alternatives, "waitScenario": wait_summary}, indent=2) + "\n").encode(),
        }
        if sum(map(len, artifacts.values())) > 12 * 1024 * 1024:
            raise ValueError("combined investigation exceeds 12 MiB output budget")
        if sum(map(len, wait_artifacts.values())) + sum(map(len, artifacts.values())) > 16 * 1024 * 1024:
            raise ValueError("combined investigation and S02/VIS outputs exceed 16 MiB budget")
        if output is None:
            output = Path(tempfile.mkdtemp(prefix="mana-transaction-investigation-"))
            output.chmod(0o700)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.mkdir(mode=0o700)
        try:
            for name, raw in artifacts.items():
                (output / name).write_bytes(raw)
            for name, raw in wait_artifacts.items():
                (output / name).write_bytes(raw)
            plantuml = shutil.which("plantuml")
            diagrams = sorted(output.glob("*.puml"))
            if plantuml and diagrams:
                try:
                    result = subprocess.run([plantuml, "-tsvg", *map(str, diagrams)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
                except subprocess.SubprocessError:
                    result = None
                svgs = [source.with_suffix(".svg") for source in diagrams]
                if result is not None and result.returncode == 0:
                    for svg in svgs:
                        if svg.is_file() and svg.stat().st_size > 4 * 1024 * 1024:
                            svg.unlink()
                    if (output / "sequence.svg").is_file():
                        svg_result = "SVG rendered successfully by local PlantUML"
                else:
                    for svg in svgs:
                        svg.unlink(missing_ok=True)
            report = report_markdown(project, args.entry, revision, model, timeline, svg_result, context_origin, args.context, wait_summary, args.wait_scenario, args.wait_timeline, proxy_alternatives)
            (output / "report.md").write_text(report, encoding="utf-8")
        except Exception:
            for child in output.iterdir():
                if child.is_file() and not child.is_symlink():
                    child.unlink()
            output.rmdir()
            raise
        result = {"status": "CONDITIONAL_STATIC_SCENARIO", "outputDir": str(output), "frames": len(model["frames"]), "resourceObservations": len(timeline["observations"]), "svg": svg_result}
        if wait_summary:
            result["waitScenario"] = wait_summary
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
