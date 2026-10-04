#!/usr/bin/env python3
"""Read canonical human choices for one workspace; verify provider preservation.

No writes, model calls, implicit approval, or matching by fuzzy text. Descriptor
matching survives content-derived IDs changing when a decision is resolved.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
from pathlib import Path

MAX_BYTES = 262144


def read(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("unsafe or oversized human-decision input")
    return json.loads(path.read_text(encoding="utf-8"))


def descriptor(decision):
    return {key: decision[key] for key in ("question", "owner", "materiality")} | {
        "options": sorted(
            [{key: option[key] for key in ("id", "label", "summary")} for option in decision["options"]],
            key=lambda option: option["id"],
        )
    }


def snapshot(workspace: Path, story_id: str):
    if workspace.is_symlink() or any(parent.name == ".mana" and parent.is_symlink() for parent in workspace.parents):
        raise ValueError("unsafe workspace")
    workspace = workspace.resolve(strict=True)
    mana = next((parent for parent in workspace.parents if parent.name == ".mana"), None)
    result = {"schemaVersion": "mana.story-start.human-decisions/v1", "storyId": story_id, "decisions": []}
    if mana is None:
        return result  # Standalone offline callers retain legacy behavior.
    if mana.is_symlink():
        raise ValueError("unsafe Mana root")
    root = mana.parent
    source = workspace / "planning/story-start-implementation-plan-v2.json"
    source_path = source.relative_to(root).as_posix()
    directory = mana / "human-feedback/decisions"
    for parent in (mana / "human-feedback", directory):
        if parent.is_symlink():
            raise ValueError("unsafe canonical feedback directory")
    seen = set()
    superseded = set()
    for path in sorted(directory.glob("decision_*.json")):
        record = read(path)
        if record.get("source", {}).get("path") != source_path:
            continue
        if record.get("schemaVersion") != "mana.human-feedback.decision/v1" or not re.fullmatch(r"[1-9][0-9]*", str(record.get("revision", ""))):
            raise ValueError("malformed canonical decision")
        identity = record["decisionId"]
        expected = "decision_" + hashlib.sha256(identity.encode()).hexdigest() + ".json"
        if path.name != expected or identity in seen:
            raise ValueError("ambiguous canonical decision identity")
        seen.add(identity)
        for previous in record.get("supersedes", []):
            if not isinstance(previous, dict):
                raise ValueError("malformed decision supersession")
            superseded.add((previous["decisionId"], previous["revision"]))
        decision = record.get("decision")
        if decision is None:
            # Earlier v1 producers did not retain the descriptor. Admit only
            # the exact source revision they actually validated at Decide.
            prior = read(source)
            revision = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            if record["source"].get("revision") != revision or prior.get("storyId") != story_id:
                raise ValueError("legacy human decision requires source reconciliation")
            matches = [item for item in prior["decisionRegister"] if item["id"] == identity]
            if len(matches) != 1:
                raise ValueError("missing or ambiguous decision source")
            decision = matches[0]
        elif record.get("storyId") != story_id:
            raise ValueError("human decision belongs to another story")
        selected = record["selectedOptionId"]
        if selected not in {item["id"] for item in decision["options"]}:
            raise ValueError("human option is absent from its validated source")
        result["decisions"].append({
            "decisionId": identity, "revision": record["revision"],
            "source": record["source"], "descriptor": descriptor(decision),
            "selectedOptionId": selected,
        })
        if len(result["decisions"]) > 128:
            raise ValueError("human decision count exceeds planning budget")
    result["decisions"] = [item for item in result["decisions"] if (item["decisionId"], item["revision"]) not in superseded]
    if seen and not result["decisions"]:
        raise ValueError("cyclic human decision supersession")
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("human decisions exceed planning budget")
    return result


def verify(context, artifact):
    if context["storyId"] != artifact["storyId"]:
        raise ValueError("human decision story mismatch")
    decisions = artifact.get("decisions", artifact.get("decisionRegister", []))
    for choice in context["decisions"]:
        matches = [item for item in decisions if descriptor(item) == choice["descriptor"]]
        if len(matches) != 1 or matches[0]["status"] != "resolved" or matches[0]["selectedOptionId"] != choice["selectedOptionId"]:
            raise ValueError("HUMAN_DECISION_NOT_PRESERVED: reconcile changed alternatives or preserve the recorded selection")


def main():
    try:
        if len(sys.argv) == 5 and sys.argv[1] == "snapshot":
            result = snapshot(Path(sys.argv[2]), sys.argv[3])
            Path(sys.argv[4]).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        elif len(sys.argv) == 4 and sys.argv[1] == "verify":
            verify(read(Path(sys.argv[2])), read(Path(sys.argv[3])))
        elif len(sys.argv) == 6 and sys.argv[1] == "supersedes":
            directory, source = map(Path, sys.argv[2:4])
            identity, source_path = sys.argv[4:6]
            plan = read(source)
            decision = next(item for item in plan["decisionRegister"] if item["id"] == identity)
            ids = []
            for path in sorted(directory.glob("decision_*.json")):
                record = read(path)
                if record.get("decisionId") != identity and record.get("storyId") == plan.get("storyId", "") and record.get("source", {}).get("path") == source_path and record.get("decision") is not None and descriptor(record["decision"]) == descriptor(decision):
                    ids.append({"decisionId": record["decisionId"], "revision": record["revision"]})
            print(json.dumps(ids))
        else:
            raise ValueError("expected snapshot <workspace> <story-id> <output> or verify <context> <artifact>")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
