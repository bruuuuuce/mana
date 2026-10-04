#!/usr/bin/env python3
"""Zero-token Decide -> real public replanning -> governed publication test."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
spec = importlib.util.spec_from_file_location("normalizer", ROOT / "scripts/lib/story-start-scope-v2-normalize.py")
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
fixtures = ROOT / "tests/fixtures/story-start-scope-v2"


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path.write_text(json.dumps(value) + "\n")


def replace(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [replace(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: replace(item, mapping) for key, item in value.items()}
    return value


def run(arguments, **kwargs):
    return subprocess.run([str(item) for item in arguments], check=True, capture_output=True, text=True, **kwargs)


with tempfile.TemporaryDirectory(prefix="mana-human-replan-") as temporary:
    project = Path(temporary) / "project"
    workspace = project / ".mana/features/SYNTHETIC"
    (workspace / "planning").mkdir(parents=True)
    d_raw = load(fixtures / "discovery/provider-output.json")
    t_raw = load(fixtures / "triage/provider-output.json")
    p_raw = load(fixtures / "planner/provider-output.json")
    original_d = n.normalize_discovery(d_raw)
    original_t = n.normalize_triage(t_raw, original_d)
    original_p = n.normalize_plan(p_raw, n.build_planning_context(original_d, original_t), original_t)
    source = workspace / "planning/story-start-implementation-plan-v2.json"
    save(source, original_p)
    feedback = ROOT / "scripts/mana-human-feedback.sh"
    relative = source.relative_to(project).as_posix()
    targets = json.loads(run([feedback, "--project-root", project, "decision-targets", "--decision-source", relative, "--json"]).stdout)
    decision = targets["decisions"][0]
    selected = decision["options"][0]["optionId"]
    run([feedback, "--project-root", project, "decide", "--decision-source", relative, "--decision-source-revision", targets["sourceRevision"], "--decision-id", decision["decisionId"], "--decision-revision", "0", "--option-id", selected, "--author", "Synthetic acceptance", "--body", "Explicit selection for replanning", "--idempotency-key", "replan-choice", "--json"])

    # Prepare provider outputs from the same explicit synthetic source model.
    question = next(item["question"] for item in original_d["decisions"] if item["id"] == decision["decisionId"])
    raw_choice = next(item for item in d_raw["decisions"] if item["question"] == question)
    chosen_label = next(item["label"] for item in original_d["decisions"] if item["id"] == decision["decisionId"] for item in item["options"] if item["id"] == selected)
    raw_choice["status"] = "resolved"
    raw_choice["selectedOptionId"] = next(item["id"] for item in raw_choice["options"] if item["label"] == chosen_label)
    new_d = n.normalize_discovery(d_raw)
    mapping = {original_d["artifactId"]: new_d["artifactId"]}
    for collection, key in (("decisions", "question"), ("findings", "summary")):
        for old in original_d[collection]:
            new = next(item for item in new_d[collection] if item[key] == old[key])
            mapping[old["id"]] = new["id"]
    new_t_raw = replace(t_raw, mapping)
    new_t_raw["decisions"] = copy.deepcopy(new_d["decisions"])
    new_t = n.normalize_triage(new_t_raw, new_d)
    mapping[original_t["artifactId"]] = new_t["artifactId"]
    for collection, key in (("classifications", "findingRef"), ("optionGroups", "decisionRef")):
        for old in original_t[collection]:
            new = next(item for item in new_t[collection] if item[key] == mapping.get(old[key], old[key]))
            mapping[old["id"]] = new["id"]
    new_p_raw = replace(p_raw, mapping)
    new_p_raw["decisionRegister"] = new_d["decisions"]
    new_p_raw["scenarioEstimates"]["openMaterialDecisionRefs"] = [item["id"] for item in new_d["decisions"] if item["status"] == "open" and item["materiality"] == "material"]
    # This performs production normalization and will still be governed by the
    # public runner. Alternative scenarios remain explicit, never approvals.
    n.normalize_plan(new_p_raw, n.build_planning_context(new_d, new_t), new_t)

    out = Path(temporary)
    save(out / "discovery.json", d_raw)
    save(out / "triage.json", new_t_raw)
    save(out / "plan.json", new_p_raw)
    stub = out / "provider-stub"
    stub.write_text('''#!/usr/bin/env bash
last=""; for arg in "$@"; do last="$arg"; done
case "$last" in
 *COMPACT_DISCOVERY_PACKAGE*) cat "$HUMAN_TEST_DISCOVERY" ;;
 *COMPACT_DISCOVERY_V2*) cat "$HUMAN_TEST_TRIAGE" ;;
 *) cat "$HUMAN_TEST_PLAN" ;;
esac
''')
    stub.chmod(0o700)
    env = dict(os.environ, MANA_USER_LEARNING_ALLOW_STUB="true", MANA_USER_LEARNING_STUB_COMMAND=str(stub), HUMAN_TEST_DISCOVERY=str(out / "discovery.json"), HUMAN_TEST_TRIAGE=str(out / "triage.json"), HUMAN_TEST_PLAN=str(out / "plan.json"))
    command = ['bash', '-c', '. "$1/scripts/lib/provider-dispatch.sh"; . "$1/scripts/lib/story-start-scope-v2.sh"; mana_story_start_scope_v2_run_public stub deterministic "$2" "$3"', 'human-decision-test', ROOT, fixtures / "discovery/compact-package.json", workspace]
    for regeneration in range(2):
        run(command, env=env)
        published = load(source)
        match = next(item for item in published["decisionRegister"] if item["question"] == question)
        assert match["status"] == "resolved" and match["selectedOptionId"] == selected
        assert load(workspace / "validation/story-start-scope-governance-v2.json")["status"] == "passed"

    # Dropping the choice is rejected before publication; the last good plan
    # remains byte-identical. The test uses the real public pipeline.
    before = source.read_bytes()
    save(out / "discovery.json", load(fixtures / "discovery/provider-output.json"))
    rejected = subprocess.run([str(item) for item in command], env=env, capture_output=True, text=True)
    assert rejected.returncode != 0 and "HUMAN_DECISION_NOT_PRESERVED" in rejected.stderr
    assert source.read_bytes() == before
    helper = ROOT / "scripts/lib/story-start-human-decisions.py"
    context = workspace / "validation/story-start-human-decisions-v1.json"
    for mutation in ("option", "owner", "alternatives", "missing", "story"):
        hostile = load(source)
        choice = next(item for item in hostile["decisionRegister"] if item["question"] == question)
        if mutation == "option":
            choice["selectedOptionId"] = next(item["id"] for item in choice["options"] if item["id"] != selected)
        elif mutation == "owner":
            choice["owner"] = "Changed owner"
        elif mutation == "alternatives":
            choice["options"][0]["summary"] = "Changed alternative"
        elif mutation == "missing":
            hostile["decisionRegister"].remove(choice)
        else:
            hostile["storyId"] = "Different story"
        save(out / "hostile.json", hostile)
        assert subprocess.run(["python3", str(helper), "verify", str(context), str(out / "hostile.json")], capture_output=True).returncode != 0

    # A new explicit selection on the regenerated ID supersedes the earlier
    # logical record without discarding either canonical history.
    targets = json.loads(run([feedback, "--project-root", project, "decision-targets", "--decision-source", relative, "--json"]).stdout)
    current = next(item for item in targets["decisions"] if item["question"] == question)
    alternative = next(item["optionId"] for item in current["options"] if item["optionId"] != selected)
    run([feedback, "--project-root", project, "decide", "--decision-source", relative, "--decision-source-revision", targets["sourceRevision"], "--decision-id", current["decisionId"], "--decision-revision", "0", "--option-id", alternative, "--author", "Synthetic acceptance", "--body", "Explicit changed selection", "--idempotency-key", "replan-choice-new", "--json"])
    run(["python3", helper, "snapshot", workspace, original_d["storyId"], out / "changed-choice.json"])
    changed = load(out / "changed-choice.json")["decisions"]
    assert len(changed) == 1 and changed[0]["selectedOptionId"] == alternative
    assert len(list((project / ".mana/human-feedback/decisions").glob("*.json"))) == 2
    print("Human decisions public replanning: two governed regenerations and omitted-choice rejection passed")
