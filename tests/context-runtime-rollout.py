#!/usr/bin/env python3
"""Zero-token adversarial tests for CTX-10 rollout infrastructure."""
from __future__ import annotations

import json
import os
import importlib.util
import shlex
import shutil
import subprocess
import sys
import tempfile
import hashlib
import stat
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = [sys.executable, str(ROOT / "scripts/context-runtime-rollout.py")]


def inventory(root: Path) -> dict[str, tuple]:
    """Full no-follow before/after fixture inventory for doctor regressions."""
    values: dict[str, tuple] = {}
    for path in [root, *sorted(root.rglob("*"))]:
        relative = "." if path == root else str(path.relative_to(root))
        meta = path.lstat()
        kind = "symlink" if stat.S_ISLNK(meta.st_mode) else "directory" if stat.S_ISDIR(meta.st_mode) else "file" if stat.S_ISREG(meta.st_mode) else "other"
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if kind == "file" else None
        target = os.readlink(path) if kind == "symlink" else None
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", relative], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        values[relative] = ("tracked" if tracked else "ignored" if ignored else "untracked", kind, stat.S_IMODE(meta.st_mode), digest, meta.st_ino, target)
    return values


def load_rollout_module():
    spec = importlib.util.spec_from_file_location("ctx10_rollout_test", ROOT / "scripts/context-runtime-rollout.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(*args: str, root: Path, ok: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*TOOL, *args, "--project-root", str(root)], text=True, capture_output=True, env=env)
    if (result.returncode == 0) != ok:
        raise AssertionError(f"unexpected exit {result.returncode}: {result.stderr}")
    return result


def refresh(root: Path, target: str, content: str, *, fault: str | None = None, ok: bool = True) -> subprocess.CompletedProcess[str]:
    args = ["refresh-block", "--target", target, "--block-id", "fixture", "--content", content]
    if fault:
        args += ["--fault", fault]
    return run(*args, root=root, ok=ok)


def assert_durable_path_containment(project: Path, temporary_root: Path) -> None:
    """R2.6: every durable CTX-10 surface is opaque or project-relative."""
    durable = project / ".mana"
    forbidden = (str(temporary_root).encode(), temporary_root.name.encode(), str(project).encode())
    for path in sorted(durable.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        payload = path.read_bytes()
        assert all(token not in payload for token in forbidden), path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="CTX10_TMPDIR_SECRET_CANARY-", dir="/private/tmp" if sys.platform == "darwin" else None) as temporary:
        project = Path(temporary) / "project"; project.mkdir()
        outside = Path(temporary) / "outside"; outside.write_text("sentinel\n")
        # First bootstrap is dormant and creates no links.  A second is byte-idempotent.
        run("bootstrap", root=project)
        before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
        run("bootstrap", root=project)
        after = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
        assert before == after and not (project / ".mana/links").exists()
        decision = json.loads(run("candidate", "--profile", "example", root=project).stdout)
        assert decision["mode"] == "legacy" and decision["warning"]["code"] == "global-default-legacy"
        policy = project / ".mana/context-runtime/runtime-selection-v1.json"
        value = json.loads(policy.read_text()); value["profiles"] = {"v2-profile": {"mode": "v2", "failClosed": True}, "legacy-profile": {"mode": "legacy", "reason": "profile-explicitly-exempted", "exempted": True}}
        policy.write_text(json.dumps(value) + "\n")
        assert json.loads(run("candidate", "--profile", "v2-profile", root=project).stdout)["mode"] == "v2"
        assert run("candidate", "--profile", "v2-profile", "--requested-mode", "legacy", root=project, ok=False).returncode == 2
        # Plain legacy is pinned, not silently treated as an exemption. Both
        # the executable loader and status/doctor-facing loader path agree.
        value["profiles"].update({"pinned": {"mode": "legacy"}, "pinned-false": {"mode": "legacy", "exempted": False}})
        policy.write_text(json.dumps(value) + "\n")
        pinned_decision = json.loads(run("candidate", "--profile", "pinned", root=project).stdout)
        assert pinned_decision["runtimeSelection"] == "legacy" and pinned_decision["migrationDisposition"] == "pinned" and pinned_decision["migrationWarning"] == "profile-pinned-legacy" and pinned_decision["warning"]["code"] == "profile-pinned-legacy"
        assert json.loads(run("candidate", "--profile", "pinned-false", root=project).stdout)["warning"]["code"] == "profile-pinned-legacy"
        exempt_decision = json.loads(run("candidate", "--profile", "legacy-profile", root=project).stdout)
        assert exempt_decision["runtimeSelection"] == "legacy" and exempt_decision["migrationDisposition"] == "exempted" and exempt_decision["migrationWarning"] == "profile-exempted"
        status = json.loads(run("status", root=project).stdout)
        pinned = next(item for item in status["profileDiagnostics"] if item["profileId"] == "pinned")
        assert pinned["effectiveRuntime"] == "legacy" and "profile-pinned-legacy" in {warning["code"] for warning in pinned["migrationWarnings"]}
        # Strict JSON: duplicate members are rejected before schema/semantic
        # evaluation; every type and cross-field error is an executed case.
        invalid_policies = [
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"mode":"legacy","reason":7}}}',
            '{"schemaVersion":"unknown","defaultMode":"legacy","profiles":{}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","extra":true,"profiles":{}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"bad id":{"mode":"legacy"}}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"failClosed":true}}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"mode":"nope"}}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"mode":"legacy","failClosed":true}}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"mode":"v2","exempted":true}}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"mode":"shadow","exempted":true}}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"mode":"compare","exempted":true}}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"mode":"legacy","exempted":"false"}}}',
            '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"x":{"mode":"legacy","unknown":true}}}',
        ]
        for invalid in invalid_policies:
            policy.write_text(invalid)
            assert run("candidate", "--profile", "x", root=project, ok=False).returncode == 2
        policy.write_text(json.dumps(value) + "\n")
        # A decision is a host-owned immutable snapshot, including policy
        # digest and selection source; source mutation cannot revise it.
        workspace_one = "W-" + "1" * 64
        artifact = json.loads(run("materialize-decision", "--profile", "v2-profile", "--execution-id", "execution-one", "--execution-version", "1", "--workspace-id", workspace_one, root=project).stdout)
        assert artifact["effectiveMode"] == "v2" and artifact["policyDigest"].startswith("sha256:") and artifact["executionId"] == "execution-one"
        first_resolve = json.loads(run("resolve", "--profile", "v2-profile", "--execution-id", "execution-one", "--execution-version", "1", "--workspace-id", workspace_one, root=project).stdout)
        second_resolve = json.loads(run("resolve", "--profile", "v2-profile", "--execution-id", "execution-one", "--execution-version", "1", "--workspace-id", workspace_one, root=project).stdout)
        assert first_resolve["mode"] == second_resolve["mode"] == "v2"
        value["profiles"]["v2-profile"] = {"mode": "legacy", "reason": "later-policy-edit"}
        policy.write_text(json.dumps(value) + "\n")
        same = json.loads(run("resolve", "--profile", "v2-profile", "--execution-id", "execution-one", "--execution-version", "1", "--workspace-id", workspace_one, root=project).stdout)
        assert same["mode"] == "v2"
        workspace_two = "W-" + "2" * 64
        later = json.loads(run("materialize-decision", "--profile", "v2-profile", "--execution-id", "execution-two", "--execution-version", "1", "--workspace-id", workspace_two, root=project).stdout)
        assert later["effectiveMode"] == "legacy" and later["executionId"] == "execution-two" and "execution-one" not in json.dumps(later)
        later_first = json.loads(run("resolve", "--profile", "v2-profile", "--execution-id", "execution-two", "--execution-version", "1", "--workspace-id", workspace_two, root=project).stdout)
        later_second = json.loads(run("resolve", "--profile", "v2-profile", "--execution-id", "execution-two", "--execution-version", "1", "--workspace-id", workspace_two, root=project).stdout)
        assert later_first["mode"] == later_second["mode"] == "legacy"
        later_identity = {
            "executionId": "execution-two", "executionVersion": 1,
            "workspaceId": workspace_two, "profileId": "v2-profile",
            "projectRootBinding": later["projectRootBinding"],
        }
        later_key = hashlib.sha256(json.dumps(
            later_identity, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        later_head = json.loads((project / ".mana/context-runtime/decisions" / later_key / "HEAD/decision-head-v1.json").read_text())
        assert "execution-one" not in (project / later_head["bundlePath"] / "decision-v1.json").read_text()

        # The same policy-to-decision derivation is used for first resolve,
        # materialization and committed reuse across every supported mode and
        # every legacy classification.
        value["profiles"].update({
            "cycle-pinned": {"mode": "legacy"},
            "cycle-pinned-false": {"mode": "legacy", "exempted": False},
            "cycle-exempt": {"mode": "legacy", "exempted": True},
            "cycle-inherited": {"mode": "inherited"},
            "cycle-v2": {"mode": "v2", "failClosed": True},
            "cycle-shadow": {"mode": "shadow", "failClosed": True},
            "cycle-compare": {"mode": "compare", "failClosed": True},
        })
        policy.write_text(json.dumps(value) + "\n")
        cycles = {
            "cycle-pinned": "legacy", "cycle-pinned-false": "legacy",
            "cycle-exempt": "legacy", "cycle-inherited": "legacy",
            "cycle-global": "legacy", "cycle-v2": "v2",
            "cycle-shadow": "shadow", "cycle-compare": "compare",
        }
        for ordinal, (cycle_profile, expected_mode) in enumerate(cycles.items(), 3):
            execution_id = f"execution-cycle-{ordinal}"
            workspace_id = "W-" + format(ordinal, "x") * 64
            initial = json.loads(run("candidate", "--profile", cycle_profile, root=project).stdout)
            materialized = json.loads(run(
                "materialize-decision", "--profile", cycle_profile,
                "--execution-id", execution_id, "--execution-version", "1",
                "--workspace-id", workspace_id, root=project,
            ).stdout)
            reused = [json.loads(run(
                "resolve", "--profile", cycle_profile,
                "--execution-id", execution_id, "--execution-version", "1",
                "--workspace-id", workspace_id, root=project,
            ).stdout) for _ in range(2)]
            assert initial["mode"] == materialized["effectiveMode"] == expected_mode
            assert [item["mode"] for item in reused] == [expected_mode, expected_mode]

        # A decision JSON never authenticates itself.  The immutable bundle
        # binds all children, and the separately published parent HEAD/commit
        # binds that bundle manifest and its file instance.
        rollout = load_rollout_module()
        value["profiles"]["authority"] = {"mode": "v2", "failClosed": True}
        policy.write_text(json.dumps(value) + "\n")

        def canonical(item: object) -> bytes:
            return (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode()

        def file_instance(path: Path) -> dict[str, int]:
            info = path.stat(follow_symlinks=False)
            return {
                "device": info.st_dev, "inode": info.st_ino, "mode": info.st_mode,
                "size": info.st_size, "mtime_ns": info.st_mtime_ns,
                "ctime_ns": info.st_ctime_ns,
            }

        def authority_case(name: str) -> dict[str, object]:
            execution_id = "execution-authority-" + name
            workspace_id = "W-" + hashlib.sha256(name.encode()).hexdigest()
            artifact_value = json.loads(run(
                "materialize-decision", "--profile", "authority",
                "--execution-id", execution_id, "--execution-version", "1",
                "--workspace-id", workspace_id, root=project,
            ).stdout)
            identity = {key: artifact_value[key] for key in (
                "executionId", "executionVersion", "workspaceId", "profileId",
                "projectRootBinding",
            )}
            namespace = project / rollout._decision_namespace(identity)
            head_path = namespace / "HEAD/decision-head-v1.json"
            head_commit_path = namespace / "HEAD/decision-head-commit-v1.json"
            head = json.loads(head_path.read_text())
            bundle_path = project / head["bundlePath"]
            resolve_args = [
                "resolve", "--profile", "authority", "--execution-id", execution_id,
                "--execution-version", "1", "--workspace-id", workspace_id,
            ]
            return {
                "artifact": artifact_value, "identity": identity,
                "namespace": namespace, "bundle": bundle_path,
                "decision": bundle_path / "decision-v1.json",
                "snapshot": bundle_path / "policy-snapshot-v1.json",
                "receipt": bundle_path / "decision-receipt-v1.json",
                "manifest": bundle_path / "bundle-manifest-v1.json",
                "head": head_path, "headCommit": head_commit_path,
                "args": resolve_args,
            }

        def rejected(case: dict[str, object]) -> None:
            result = run(*case["args"], root=project, ok=False)
            assert result.returncode == 2
            assert "CTX10_DECISION_AUTHORITY_REJECTED" in result.stderr

        mutations = {
            "configured": lambda item: item.update(configuredMode="shadow"),
            "effective": lambda item: item.update(effectiveMode="shadow"),
            "coherent-modes": lambda item: item.update(configuredMode="shadow", effectiveMode="shadow"),
            "policy-digest": lambda item: item.update(policyDigest="sha256:" + "0" * 64),
            "source": lambda item: item.update(decisionSource="caller-policy"),
            "reason": lambda item: item.update(decisionReason="caller-reason"),
            "execution": lambda item: item.update(executionId="execution-foreign"),
            "version": lambda item: item.update(executionVersion=2),
            "workspace": lambda item: item.update(workspaceId="W-" + "f" * 64),
            "profile": lambda item: item.update(profileId="foreign-profile"),
        }
        for name, mutate in mutations.items():
            case_value = authority_case(name)
            changed = json.loads(case_value["decision"].read_text())
            mutate(changed)
            case_value["decision"].write_bytes(canonical(changed))
            rejected(case_value)

        # E: the snapshot alone is made internally coherent for shadow.
        snapshot_case = authority_case("snapshot-coherent")
        changed_snapshot = json.loads(snapshot_case["snapshot"].read_text())
        changed_snapshot["policy"]["profiles"]["authority"] = {"mode": "shadow", "failClosed": True}
        changed_snapshot["policyDigest"] = rollout._sha256(canonical(changed_snapshot["policy"]))
        snapshot_case["snapshot"].write_bytes(canonical(changed_snapshot))
        rejected(snapshot_case)

        # F: receipt/file commitments and bundle manifest are rewritten
        # coherently, while the external parent stays unchanged.
        receipt_case = authority_case("receipt-coherent")
        receipt_case["receipt"].write_bytes(receipt_case["receipt"].read_bytes())
        changed_manifest = json.loads(receipt_case["manifest"].read_text())
        receipt_raw = receipt_case["receipt"].read_bytes()
        changed_manifest["artifacts"]["decisionReceipt"]["digest"] = rollout._sha256(receipt_raw)
        changed_manifest["artifacts"]["decisionReceipt"]["fileInstance"] = file_instance(receipt_case["receipt"])
        changed_manifest["receiptDigest"] = rollout._sha256(receipt_raw)
        changed_manifest["childCommitmentsDigest"] = rollout._sha256(canonical(changed_manifest["artifacts"]))
        receipt_case["manifest"].write_bytes(canonical(changed_manifest))
        rejected(receipt_case)

        # G: decision, snapshot and receipt are all coherently rewritten and
        # every child/bundle digest is recalculated.  Only the unchanged parent
        # manifest commitment rejects the forged chain.
        coherent = authority_case("all-coherent")
        snapshot = json.loads(coherent["snapshot"].read_text())
        snapshot["policy"]["profiles"]["authority"] = {"mode": "shadow", "failClosed": True}
        snapshot["policyDigest"] = rollout._sha256(canonical(snapshot["policy"]))
        coherent["snapshot"].write_bytes(canonical(snapshot))
        decision = json.loads(coherent["decision"].read_text())
        decision.update(configuredMode="shadow", effectiveMode="shadow",
                        policyDigest=snapshot["policyDigest"], decisionReason="profile-opt-in")
        coherent["decision"].write_bytes(canonical(decision))
        receipt_body = {
            "schemaVersion": rollout.DECISION_RECEIPT_VERSION,
            "executionIdentityDigest": rollout._sha256(canonical(coherent["identity"])),
            "policySnapshot": {
                "path": "policy-snapshot-v1.json",
                "digest": rollout._sha256(coherent["snapshot"].read_bytes()),
                "fileInstance": file_instance(coherent["snapshot"]),
            },
            "rolloutDecision": {
                "path": "decision-v1.json",
                "digest": rollout._sha256(coherent["decision"].read_bytes()),
                "fileInstance": file_instance(coherent["decision"]),
            },
        }
        receipt = {**receipt_body, "receiptId": rollout._receipt_id(receipt_body)}
        coherent["receipt"].write_bytes(canonical(receipt))
        manifest = json.loads(coherent["manifest"].read_text())
        for role, key in (("policySnapshot", "snapshot"), ("rolloutDecision", "decision"), ("decisionReceipt", "receipt")):
            manifest["artifacts"][role]["digest"] = rollout._sha256(coherent[key].read_bytes())
            manifest["artifacts"][role]["fileInstance"] = file_instance(coherent[key])
        manifest.update(
            policySnapshotDigest=manifest["artifacts"]["policySnapshot"]["digest"],
            rolloutDecisionDigest=manifest["artifacts"]["rolloutDecision"]["digest"],
            receiptDigest=manifest["artifacts"]["decisionReceipt"]["digest"],
            configuredMode="shadow", effectiveMode="shadow", receiptId=receipt["receiptId"],
        )
        manifest["childCommitmentsDigest"] = rollout._sha256(canonical(manifest["artifacts"]))
        coherent["manifest"].write_bytes(canonical(manifest))
        rejected(coherent)

        # R2.5 regression: this entire CTX-10 closure was accepted by R2.4.
        # Keep the external intent and selection commitment byte/instance-identical.
        full = authority_case("full-ctx10-rewrite")
        parent = project / rollout._intent_namespace(full["identity"])
        parent_files = sorted(path for path in parent.rglob("*") if path.is_file())
        def parent_snapshot():
            return {
                str(path.relative_to(parent)): (path.read_bytes(), file_instance(path))
                for path in parent_files
            }
        parent_before = parent_snapshot()
        full_snapshot = json.loads(full["snapshot"].read_text())
        full_snapshot["policy"]["profiles"]["authority"] = {"mode": "shadow", "failClosed": True}
        full_snapshot["policyDigest"] = rollout._sha256(canonical(full_snapshot["policy"]))
        full["snapshot"].write_bytes(canonical(full_snapshot))
        full_decision = json.loads(full["decision"].read_text())
        full_decision.update(configuredMode="shadow", effectiveMode="shadow",
                             policyDigest=full_snapshot["policyDigest"])
        full["decision"].write_bytes(canonical(full_decision))
        full_receipt_body = {
            "schemaVersion": rollout.DECISION_RECEIPT_VERSION,
            "executionIdentityDigest": rollout._sha256(canonical(full["identity"])),
            "policySnapshot": {"path": "policy-snapshot-v1.json",
                               "digest": rollout._sha256(full["snapshot"].read_bytes()),
                               "fileInstance": file_instance(full["snapshot"])},
            "rolloutDecision": {"path": "decision-v1.json",
                                "digest": rollout._sha256(full["decision"].read_bytes()),
                                "fileInstance": file_instance(full["decision"])},
        }
        full_receipt = {**full_receipt_body, "receiptId": rollout._receipt_id(full_receipt_body)}
        full["receipt"].write_bytes(canonical(full_receipt))
        full_manifest = json.loads(full["manifest"].read_text())
        for role, name in (("policySnapshot", "snapshot"), ("rolloutDecision", "decision"),
                           ("decisionReceipt", "receipt")):
            full_manifest["artifacts"][role]["digest"] = rollout._sha256(full[name].read_bytes())
            full_manifest["artifacts"][role]["fileInstance"] = file_instance(full[name])
        full_manifest.update(
            policySnapshotDigest=full_manifest["artifacts"]["policySnapshot"]["digest"],
            rolloutDecisionDigest=full_manifest["artifacts"]["rolloutDecision"]["digest"],
            receiptDigest=full_manifest["artifacts"]["decisionReceipt"]["digest"],
            configuredMode="shadow", effectiveMode="shadow", receiptId=full_receipt["receiptId"],
            childCommitmentsDigest=rollout._sha256(canonical(full_manifest["artifacts"])),
        )
        full["manifest"].write_bytes(canonical(full_manifest))
        full_head = json.loads(full["head"].read_text())
        full_head.update(bundleDigest=rollout._sha256(full["manifest"].read_bytes()),
                         bundleManifest={"path": full_manifest["bundlePath"] + "/bundle-manifest-v1.json",
                                         "digest": rollout._sha256(full["manifest"].read_bytes()),
                                         "fileInstance": file_instance(full["manifest"])},
                         configuredMode="shadow", effectiveMode="shadow",
                         childCommitmentsDigest=full_manifest["childCommitmentsDigest"])
        head_body = {key: value for key, value in full_head.items() if key != "authorityId"}
        full_head["authorityId"] = rollout._authority_id(head_body)
        full["head"].write_bytes(canonical(full_head))
        full_commit = json.loads(full["headCommit"].read_text())
        full_commit.update(authorityId=full_head["authorityId"],
                           headDigest=rollout._sha256(full["head"].read_bytes()),
                           headFile=file_instance(full["head"]),
                           bundleManifestDigest=rollout._sha256(full["manifest"].read_bytes()),
                           bundleManifestFile=file_instance(full["manifest"]))
        full["headCommit"].write_bytes(canonical(full_commit))
        assert rollout._load_decision_head(
            project, full["identity"], "authority")["effectiveMode"] == "shadow"
        full_result = run(*full["args"], root=project, ok=False)
        assert full_result.returncode == 2
        assert "CTX10_DECISION_AUTHORITY_REJECTED" in full_result.stderr
        assert "shadow" not in full_result.stdout
        assert parent_snapshot() == parent_before

        # The selected trust root is outside CTX-10. Ordinary corruption of
        # that root fails closed; arbitrary coherent same-UID rewrite is out
        # of the local threat model.
        for name in ("missing-intent", "invalid-intent-schema", "intent-digest",
                     "foreign-intent-identity", "wrong-intent-path", "intent-symlink",
                     "intent-fifo", "partial-selection", "missing-bundle-reference",
                     "foreign-bundle-reference", "stale-bundle-reference"):
            root_case = authority_case("root-" + name)
            authority = project / rollout._intent_namespace(root_case["identity"])
            intent_path = authority / "execution-intent-v1.json"
            commit_path = authority / "intent-commit-v1.json"
            selection_path = authority / "SELECTION/rollout-decision-commitment-v1.json"
            if name == "missing-intent":
                intent_path.unlink()
            elif name == "invalid-intent-schema":
                item = json.loads(intent_path.read_text()); item["schemaVersion"] = "invalid"
                intent_path.write_bytes(canonical(item))
            elif name == "intent-digest":
                item = json.loads(commit_path.read_text()); item["intentDigest"] = "sha256:" + "0" * 64
                commit_path.write_bytes(canonical(item))
            elif name == "foreign-intent-identity":
                item = json.loads(intent_path.read_text())
                item["executionIdentity"]["executionId"] = "execution-foreign"
                intent_path.write_bytes(canonical(item))
            elif name == "wrong-intent-path":
                item = json.loads(commit_path.read_text()); item["intentPath"] = "foreign/path.json"
                commit_path.write_bytes(canonical(item))
            elif name == "intent-symlink":
                intent_path.unlink(); intent_path.symlink_to(root_case["decision"])
            elif name == "intent-fifo":
                intent_path.unlink(); os.mkfifo(intent_path)
            elif name == "partial-selection":
                selection_path.write_bytes(b"{\"schemaVersion\":")
            else:
                item = json.loads(selection_path.read_text())
                if name == "missing-bundle-reference":
                    item["bundleId"] = "B-" + "0" * 64
                elif name == "foreign-bundle-reference":
                    item["bundlePath"] = "foreign/bundle"
                else:
                    item["bundleDigest"] = "sha256:" + "0" * 64
                selection_path.write_bytes(canonical(item))
            rejected(root_case)

        # H/I: neither the bundle manifest nor parent HEAD can be revised in
        # place without the outer parent commitment detecting it.
        manifest_case = authority_case("manifest-tamper")
        changed_manifest = json.loads(manifest_case["manifest"].read_text())
        changed_manifest["effectiveMode"] = "shadow"
        manifest_case["manifest"].write_bytes(canonical(changed_manifest))
        rejected(manifest_case)
        head_case = authority_case("head-tamper")
        changed_head = json.loads(head_case["head"].read_text())
        changed_head["effectiveMode"] = "shadow"
        head_case["head"].write_bytes(canonical(changed_head))
        rejected(head_case)

        missing_parent = authority_case("missing-parent")
        shutil.rmtree(missing_parent["namespace"] / "HEAD")
        rejected(missing_parent)

        old_ctx10_only = authority_case("old-ctx10-only")
        shutil.rmtree(project / rollout._intent_namespace(old_ctx10_only["identity"]))
        rejected(old_ctx10_only)
        old_reuse = run(
            "materialize-decision", "--profile", "authority",
            "--execution-id", old_ctx10_only["identity"]["executionId"],
            "--execution-version", "1", "--workspace-id",
            old_ctx10_only["identity"]["workspaceId"], root=project, ok=False)
        assert "CTX10_DECISION_AUTHORITY_REJECTED" in old_reuse.stderr

        # Same bytes on the same inode are ordinary reuse.  Replacing any
        # committed child, the manifest, or HEAD with a new inode is rejected.
        stable_case = authority_case("same-inode-same-bytes")
        before_inode = stable_case["receipt"].stat().st_ino
        assert json.loads(run(*stable_case["args"], root=project).stdout)["mode"] == "v2"
        assert stable_case["receipt"].stat().st_ino == before_inode
        for role in ("snapshot", "decision", "receipt", "manifest", "head"):
            instance_case = authority_case("new-inode-" + role)
            target_path = instance_case[role]
            replacement = target_path.with_name(target_path.name + ".replacement")
            replacement.write_bytes(target_path.read_bytes())
            os.replace(replacement, target_path)
            rejected(instance_case)

        same_inode_changed = authority_case("same-inode-changed")
        changed = bytearray(same_inode_changed["decision"].read_bytes())
        changed[-2] = ord(" ")
        same_inode_changed["decision"].write_bytes(bytes(changed))
        rejected(same_inode_changed)
        new_inode_changed = authority_case("new-inode-changed")
        replacement = new_inode_changed["decision"].with_name("changed.replacement")
        replacement.write_bytes(b"{}\n")
        os.replace(replacement, new_inode_changed["decision"])
        rejected(new_inode_changed)
        mode_case = authority_case("mode-change")
        os.chmod(mode_case["receipt"], 0o640)
        rejected(mode_case)

        for kind in ("symlink", "fifo"):
            special = authority_case("special-" + kind)
            original = special["receipt"]
            original.unlink()
            if kind == "symlink":
                original.symlink_to(outside)
            else:
                os.mkfifo(original)
            rejected(special)

        # An unreferenced bundle is never selected while a valid HEAD remains.
        reachable = authority_case("head-reachable")
        foreign_bundle = authority_case("unreachable-source")["bundle"]
        shutil.copytree(foreign_bundle, reachable["namespace"] / "bundles" / foreign_bundle.name)
        assert json.loads(run(*reachable["args"], root=project).stdout)["mode"] == "v2"

        # J/K: copying a complete authority graph under a foreign execution or
        # workspace-derived namespace cannot rebind its committed identities.
        source_case = authority_case("copy-source")
        for suffix, foreign_execution, foreign_workspace, foreign_profile in (
            ("execution", "execution-authority-copy-target", source_case["artifact"]["workspaceId"], "authority"),
            ("workspace", source_case["artifact"]["executionId"], "W-" + "e" * 64, "authority"),
            ("profile", source_case["artifact"]["executionId"], source_case["artifact"]["workspaceId"], "foreign-profile"),
        ):
            foreign_identity = {
                **source_case["identity"], "executionId": foreign_execution,
                "workspaceId": foreign_workspace, "profileId": foreign_profile,
            }
            foreign_namespace = project / rollout._decision_namespace(foreign_identity)
            foreign_namespace.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_case["namespace"], foreign_namespace)
            foreign_parent = project / rollout._intent_namespace(foreign_identity)
            foreign_parent.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(project / rollout._intent_namespace(source_case["identity"]), foreign_parent)
            foreign_args = [
                "resolve", "--profile", foreign_profile, "--execution-id", foreign_execution,
                "--execution-version", "1", "--workspace-id", foreign_workspace,
            ]
            result = run(*foreign_args, root=project, ok=False)
            assert "CTX10_DECISION_AUTHORITY_REJECTED" in result.stderr

        copied = Path(temporary) / "copied-project"; copied.mkdir()
        run("bootstrap", root=copied)
        copied_source = authority_case("copied-root")
        source_artifact = copied_source["artifact"]
        copied_identity = {
            **{key: source_artifact[key] for key in (
                "executionId", "executionVersion", "workspaceId", "profileId",
            )},
            "projectRootBinding": rollout._project_root_binding(copied),
        }
        copied_namespace = copied / rollout._decision_namespace(copied_identity)
        copied_namespace.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(copied_source["namespace"], copied_namespace)
        copied_parent = copied / rollout._intent_namespace(copied_identity)
        copied_parent.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(project / rollout._intent_namespace({key: source_artifact[key] for key in (
            "executionId", "executionVersion", "workspaceId", "profileId", "projectRootBinding")}), copied_parent)
        copied_rejected = run(
            "resolve", "--profile", "authority",
            "--execution-id", str(source_artifact["executionId"]),
            "--execution-version", "1", "--workspace-id", str(source_artifact["workspaceId"]),
            root=copied, ok=False,
        )
        assert "CTX10_DECISION_AUTHORITY_REJECTED" in copied_rejected.stderr
        # Prefix/user bytes, mode and CRLF survive a replacement exactly.
        target = project / ".codex/config.toml"; target.parent.mkdir(exist_ok=True)
        user = b"# user comment\r\n[custom]\r\nvalue = 'keep'\r\n"
        target.write_bytes(user); os.chmod(target, 0o640)
        refresh(project, ".codex/config.toml", "managed = true")
        first = target.read_bytes(); assert first.startswith(user) and b"\r\n" in first and (target.stat().st_mode & 0o777) == 0o640
        refresh(project, ".codex/config.toml", "managed = true")
        assert target.read_bytes() == first
        refresh(project, ".codex/config.toml", "managed = false")
        assert target.read_bytes().startswith(user) and b"managed = false" in target.read_bytes()
        # Marker-looking user prose is not a marker.  Exact marker grammar is.
        target.write_bytes(user + b"note: mana:context-runtime: this is user prose\r\n")
        refresh(project, ".codex/config.toml", "grammar = true")
        assert b"this is user prose" in target.read_bytes()
        digest = hashlib.sha256(b"x\n").hexdigest().encode()
        stale = b"# mana:context-runtime:begin version=1 id=fixture digest=" + digest + b"\nx\n# mana:context-runtime:end id=fixture\n"
        target.write_bytes(user + stale)
        stale_result = json.loads(refresh(project, ".codex/config.toml", "x").stdout)
        assert stale_result["state"] == "stale"
        target.write_bytes(user + b"# mana:context-runtime:begin version=2 id=fixture digest=" + digest + b"\nchanged\n# mana:context-runtime:end id=fixture\n")
        assert refresh(project, ".codex/config.toml", "x", ok=False).returncode == 2
        # Future, incomplete, duplicate and nested markers fail closed without a rewrite.
        future = b"# mana:context-runtime:begin version=99 id=fixture digest=" + b"0" * 64 + b"\n# x\n# mana:context-runtime:end id=fixture\n"
        target.write_bytes(user + future); original = target.read_bytes()
        assert refresh(project, ".codex/config.toml", "x", ok=False).returncode == 2 and target.read_bytes() == original
        target.write_text("mana:context-runtime:begin version=2 id=fixture digest=" + "0" * 64 + "\n")
        assert refresh(project, ".codex/config.toml", "x", ok=False).returncode == 2
        target.write_text("mana:context-runtime:begin version=2 id=fixture digest=" + "0" * 64 + "\nmana:context-runtime:end id=fixture\n" * 2)
        assert refresh(project, ".codex/config.toml", "x", ok=False).returncode == 2
        for malformed in (
            b"# mana:context-runtime:end id=fixture\n",
            b"# mana:context-runtime:begin version=x id=fixture digest=" + b"0" * 64 + b"\n",
            b"# mana:context-runtime:begin version=2 id=fixture digest=" + b"0" * 64 + b" extra=x\n",
            b"# mana:context-runtime:begin version=2 id=fixture digest=" + b"0" * 64 + b"\n# mana:context-runtime:begin version=2 id=other digest=" + b"0" * 64 + b"\n",
        ):
            target.write_bytes(user + malformed)
            assert refresh(project, ".codex/config.toml", "x", ok=False).returncode == 2
        # All declared failure points leave user bytes recoverable and no staging residue.
        target.write_bytes(user); refresh(project, ".codex/config.toml", "stable")
        stable = target.read_bytes()
        for point in ("after-read", "after-parse", "during-managed-block-replacement", "before-publication", "during-publication", "after-publication-pre-cleanup"):
            assert refresh(project, ".codex/config.toml", "changed", fault=point, ok=False).returncode == 2
            assert target.read_bytes() == stable, point
            assert not list(target.parent.glob("*.mana-context-runtime.*"))
        # Symlinks, hardlinks and unsafe parent traversal cannot escape the project root.
        target.unlink(); target.symlink_to(outside)
        assert refresh(project, ".codex/config.toml", "x", ok=False).returncode == 2 and outside.read_text() == "sentinel\n"
        target.unlink(); target.hardlink_to(outside)
        assert refresh(project, ".codex/config.toml", "x", ok=False).returncode == 2 and outside.read_text() == "sentinel\n"
        target.unlink(); os.mkfifo(target)
        assert refresh(project, ".codex/config.toml", "x", ok=False).returncode == 2
        target.unlink()
        assert refresh(project, "../outside", "x", ok=False).returncode == 2 and outside.read_text() == "sentinel\n"
        # Two refreshes converge; none can leave a transient artifact behind.
        target.write_bytes(user)
        processes = [subprocess.Popen([*TOOL, "refresh-block", "--project-root", str(project), "--target", ".codex/config.toml", "--block-id", "fixture", "--content", "parallel"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = [(item.wait(timeout=15), item.communicate()[1]) for item in processes]
        assert all(code == 0 for code, _error in results), results
        assert target.read_bytes().startswith(user) and not list(target.parent.glob("*.mana-context-runtime.*"))
        # Provider absence is distinct from a missing managed block: no project
        # config is materialized, user config is untouched, and status warns.
        absent = Path(temporary) / "project with spaces"; absent.mkdir()
        fake_home = Path(temporary) / "user-home"; (fake_home / ".codex").mkdir(parents=True)
        user_configs = {
            "codex": fake_home / ".codex/config.toml",
            "claude": fake_home / "CLAUDE.md",
            "opencode": fake_home / "opencode.jsonc",
        }
        for name, user_config in user_configs.items():
            user_config.write_bytes((name + "-user-only\n").encode())
        absent_env = {**os.environ, "PATH": ""}
        boot = json.loads(run("bootstrap", root=absent, env=absent_env).stdout)
        for provider, relative in (("codex", ".codex/config.toml"), ("claude", "CLAUDE.md"), ("opencode", "opencode.jsonc")):
            assert boot["providers"][provider]["state"] == "unavailable"
            assert not (absent / relative).exists()
            assert json.loads(run("status", root=absent, env=absent_env).stdout)["providers"][provider]["managedBlock"] == "unavailable"
        for name, user_config in user_configs.items():
            assert user_config.read_bytes() == (name + "-user-only\n").encode()
        assert not list(absent.rglob("*.lnk")) and not any(path.is_symlink() for path in absent.rglob("*"))
        # Doctor diagnoses an unbootstrapped project without creating .mana,
        # links, an evidence index or any ignored/cache artifact.  The complete
        # snapshot intentionally includes tracked/untracked/ignored state,
        # inode, type/mode, bytes and symlink target.
        doctor = Path(temporary) / "doctor-project"; doctor.mkdir()
        subprocess.run(["git", "init", "--quiet", str(doctor)], check=True)
        (doctor / ".gitignore").write_text("ignored-cache/\n")
        (doctor / "tracked.txt").write_text("tracked\n")
        (doctor / "ignored-cache").mkdir(); (doctor / "ignored-cache/cache.txt").write_text("ignored\n")
        subprocess.run(["git", "-C", str(doctor), "add", ".gitignore", "tracked.txt"], check=True)
        before_doctor = inventory(doctor)
        doctor_result = subprocess.run([str(ROOT / "scripts/mana-doctor.sh"), "--root", str(ROOT), "--project", str(doctor)], text=True, capture_output=True, env={**os.environ, "MANA_UPDATE_CHECK": "off"})
        doctor_output = doctor_result.stdout + doctor_result.stderr
        assert "no-links=true" in doctor_output and "evidence index is unavailable/not-materialized" in doctor_output
        assert not (doctor / ".mana").exists() and before_doctor == inventory(doctor)
        # Each provider's permanent state matrix is independently asserted;
        # status never calls an absent provider or treats absence as missing.
        matrix = Path(temporary) / "provider-matrix"; matrix.mkdir()
        provider_bin = Path(temporary) / "provider-presence-bin"; provider_bin.mkdir()
        provider_stub_marker = Path(temporary) / "provider-presence-stub-executed"
        for provider in ("codex", "claude", "opencode"):
            stub = provider_bin / provider
            stub.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' provider-presence-stub-executed > {shlex.quote(str(provider_stub_marker))}\n"
                "echo 'provider presence stub must not be executed' >&2\n"
                "exit 97\n"
            )
            stub.chmod(0o755)
        provider_env = os.environ.copy()
        provider_env["PATH"] = str(provider_bin) + os.pathsep + provider_env["PATH"]
        marker_digest = hashlib.sha256(b"payload\n").hexdigest()
        provider_specs = (("codex", ".codex/config.toml", "# ", "codex-runtime-v2"), ("claude", "CLAUDE.md", "# ", "claude-runtime-v2"), ("opencode", "opencode.jsonc", "// ", "opencode-runtime-v2"))
        for name, relative, prefix, block_id in provider_specs:
            target_provider = matrix / relative; target_provider.parent.mkdir(parents=True, exist_ok=True)
            def write_version(version: str, payload: bytes = b"payload\n") -> None:
                target_provider.write_bytes((prefix + f"mana:context-runtime:begin version={version} id={block_id} digest={marker_digest}\n").encode() + payload + (prefix + f"mana:context-runtime:end id={block_id}\n").encode())
            write_version("2")
            current = json.loads(run("status", root=matrix, env=provider_env).stdout)["providers"][name]
            assert current["installed"] is True and current["managedBlock"] == "current"
            write_version("1")
            stale = json.loads(run("status", root=matrix, env=provider_env).stdout)["providers"][name]
            assert stale["installed"] is True and stale["managedBlock"] == "stale"
            write_version("99")
            future = json.loads(run("status", root=matrix, env=provider_env).stdout)["providers"][name]
            assert future["installed"] is True and future["managedBlock"] == "future"
            write_version("2", b"tampered\n")
            invalid = json.loads(run("status", root=matrix, env=provider_env).stdout)["providers"][name]
            assert invalid["installed"] is True and invalid["managedBlock"] == "invalid"
        assert not provider_stub_marker.exists()
        # Stable warning matrix and per-profile effective selection are pure
        # diagnostics.  This executes all migration warning classes without
        # materializing policy, provider config or capability evidence.
        rollout = load_rollout_module()
        providers = {
            "codex": {"installed": False, "managedBlock": "unavailable"},
            "claude": {"installed": True, "managedBlock": "missing"},
            "opencode": {"installed": True, "managedBlock": "stale"},
        }
        policy_value = {"profiles": {"optin": {"mode": "v2", "failClosed": True}, "pinned": {"mode": "legacy"}, "exempt": {"mode": "legacy", "exempted": True}}}
        diagnostics = rollout._profile_diagnostics(matrix, policy_value, "current", providers)
        optin = next(value for value in diagnostics if value["profileId"] == "optin")
        exempt = next(value for value in diagnostics if value["profileId"] == "exempt")
        codes = {warning["code"] for value in diagnostics for warning in value["migrationWarnings"]}
        assert optin["configuredSelection"] == "v2" and optin["effectiveRuntime"] == "v2" and optin["blockingCapabilityGaps"]
        assert exempt["configuredSelection"] == "legacy" and exempt["effectiveRuntime"] == "legacy"
        assert {"CTX10_MANIFEST_NOT_COMPILABLE", "CTX10_PROVIDER_CAPABILITY_GAP", "CTX10_BOOTSTRAP_STALE", "CTX10_MANAGED_BLOCK_MISSING", "profile-exempted", "profile-pinned-legacy", "CTX10_PROVIDER_UNAVAILABLE"} <= codes
        with mock.patch.object(rollout.Path, "is_file", return_value=False):
            assert "CTX10_PIPELINE_V2_ABSENT" in {warning["code"] for value in rollout._profile_diagnostics(matrix, policy_value, "current", providers) for warning in value["migrationWarnings"]}
        future = {**providers, "opencode": {"installed": True, "managedBlock": "future"}}
        assert "CTX10_MANAGED_BLOCK_FUTURE" in {warning["code"] for value in rollout._profile_diagnostics(matrix, policy_value, "current", future) for warning in value["migrationWarnings"]}
        assert "CTX10_INVALID_POLICY" in {warning["code"] for value in rollout._profile_diagnostics(matrix, None, "invalid", providers) for warning in value["migrationWarnings"]}
        for warning in (warning for value in diagnostics for warning in value["migrationWarnings"]):
            assert set(warning) == {"code", "severity", "profileId", "currentRuntime", "reason", "recommendedNextAction"}
        # Inspect rejects a merely named run: required CTX-06 state fields,
        # structural schema, identity and the authoritative chain are distinct.
        run_dir = project / ".mana/runtime/runs/execution-fixture"; run_dir.mkdir(parents=True)
        run_dir.joinpath("run-state-v1.json").write_text(json.dumps({"executionId": "execution-fixture", "executionVersion": 1, "phaseOrder": ["plan"], "currentPhaseId": "plan", "latestCheckpointRef": "cp-1", "status": "active"}))
        metrics = project / ".mana/runtime/metrics/execution-fixture"; metrics.mkdir(parents=True)
        metrics.joinpath("usage-summary-v1.json").write_text(json.dumps({"usageStatus": "measured", "rawTrace": "secret-token-must-not-leak"}))
        inspect_before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
        inspected = json.loads(run("inspect", "--profile", "v2-profile", "--execution", "execution-fixture", root=project).stdout)
        assert inspected["runtimeMode"] == "legacy" and inspected["runState"]["artifactStatus"] == "partial" and "secret-token-must-not-leak" not in json.dumps(inspected)
        assert inspect_before == {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
        state = {"schemaVersion": "mana.context-runtime.run-state/v1", "executionId": "execution-fixture", "executionVersion": 1, "profileId": "v2-profile", "revision": 0, "status": "active", "currentPhaseId": "plan", "currentPhaseOrdinal": 1, "currentAttempt": 1, "latestCheckpointRef": None, "transitionId": None, "previousStateDigest": None, "attempts": {"plan": 1}}
        run_dir.joinpath("run-state-v1.json").write_text(json.dumps({**state, "schemaVersion": "wrong"}))
        assert json.loads(run("inspect", "--profile", "v2-profile", "--execution", "execution-fixture", root=project).stdout)["runState"]["artifactStatus"] == "invalid"
        run_dir.joinpath("run-state-v1.json").write_text(json.dumps({**state, "executionId": "execution-foreign"}))
        assert json.loads(run("inspect", "--profile", "v2-profile", "--execution", "execution-fixture", root=project).stdout)["runState"]["artifactStatus"] == "foreign"
        run_dir.joinpath("run-state-v1.json").write_text(json.dumps(state))
        assert json.loads(run("inspect", "--profile", "v2-profile", "--execution", "execution-fixture", root=project).stdout)["runState"]["artifactStatus"] == "stale"
        # CTX-09 fixtures are published by its real host writer and registered
        # through its real CLI. Inspect must discover their canonical namespaces
        # rather than the obsolete run-directory aliases.
        comparison_spec = importlib.util.spec_from_file_location("ctx10_ctx09_comparison", ROOT / "scripts/lib/context-comparison.py")
        assert comparison_spec and comparison_spec.loader
        comparison = importlib.util.module_from_spec(comparison_spec); comparison_spec.loader.exec_module(comparison)
        harness_spec = importlib.util.spec_from_file_location("ctx10_ctx09_harness", ROOT / "tests/fixtures/context-runtime/ctx09b-producer-harness.py")
        assert harness_spec and harness_spec.loader
        harness = importlib.util.module_from_spec(harness_spec); harness_spec.loader.exec_module(harness)
        baseline = json.loads((ROOT / "tests/fixtures/context-runtime/comparison/baseline.json").read_bytes())
        execution = "execution-inspect-real"
        harness.publish_pair(comparison.mode, project, execution, comparison.mode.canonical(baseline), comparison.mode.canonical(baseline))
        registered = subprocess.run([sys.executable, str(ROOT / "scripts/context-runtime-mode.py"), "compare", "--project-root", str(project), "--execution-id", execution, "--profile-id", "fixture-review", "--target-key", "a" * 64, "--legacy-artifact", "artifacts/legacy.json", "--v2-artifact", "artifacts/v2.json"], capture_output=True)
        assert registered.returncode == 0, registered.stderr
        comparison.run(str(project), execution, write_report=True)
        real = json.loads(run("inspect", "--profile", "fixture-review", "--execution", execution, root=project).stdout)
        assert real["producerReceipt"]["status"] == "current" and real["shadowComparison"]["status"] == "current" and real["shadowComparison"]["comparisonStatus"] == "equivalent"
        foreign = json.loads(run("inspect", "--profile", "other-profile", "--execution", execution, root=project).stdout)
        assert foreign["producerReceipt"]["status"] == "foreign"
        # Altering a real artifact leaves its canonical receipt present but
        # makes the file-instance/digest binding stale.
        artifact = project / "artifacts/v2.json"
        artifact.write_bytes(comparison.mode.canonical({**baseline, "profileId": "wrong"}))
        stale = json.loads(run("inspect", "--profile", "fixture-review", "--execution", execution, root=project).stdout)
        assert stale["producerReceipt"]["status"] == "stale"
        # A committed-looking receipt with a missing commit/artifact cannot be
        # current. The canonical reader classifies it as non-authority.
        namespace, key = comparison.mode.receipt_location(execution, "artifacts/v2.json")
        (project / namespace / (key + ".commit") / "producer-commit-v1.json").unlink()
        orphan = json.loads(run("inspect", "--profile", "fixture-review", "--execution", execution, root=project).stdout)
        assert orphan["producerReceipt"]["status"] in {"partial", "stale", "invalid"} and orphan["producerReceipt"]["status"] != "current"

        # A new CTX-06 run binds its pre-runtime intent. A run initialized
        # before the policy cannot be retroactively promoted into authority.
        framework = ROOT / "tests/fixtures/context-runtime/ctx06a-framework"
        def initialize_fixture(target_project: Path, execution_id: str) -> None:
            workspace = target_project / ".mana/sessions/ctx06c-fixture"
            workspace.mkdir(parents=True)
            (workspace / "manifest.yaml").write_text(
                'workspace_type: "session"\nworkspace_id: "ctx06c-fixture"\n')
            initialized = subprocess.run([
                str(ROOT / "scripts/mana-context-pipeline.sh"), "initialize", "ctx06c-fixture",
                "--framework-root", str(framework), "--project-root", str(target_project),
                "--execution-id", execution_id, "--provider", "codex",
                "--workspace", ".mana/sessions/ctx06c-fixture", "--objective", "Fixture phase.",
            ], capture_output=True, text=True)
            assert initialized.returncode == 0, initialized.stderr

        fixture_policy = {"schemaVersion": rollout.POLICY_VERSION, "defaultMode": "legacy",
                          "profiles": {"ctx06c-fixture": {"mode": "v2", "failClosed": True}}}
        linked_project = Path(temporary) / "intent-linked"; linked_project.mkdir()
        rollout._atomic_replace(linked_project, rollout.POLICY_RELATIVE,
                                canonical(fixture_policy), source=None)
        initialize_fixture(linked_project, "execution-intent-linked")
        envelope_path = linked_project / ".mana/runtime/runs/execution-intent-linked/execution-envelope-v1.json"
        linked_envelope = json.loads(envelope_path.read_text())
        assert linked_envelope["schemaVersion"] == "mana.context-runtime.execution-envelope/v2"
        linked = rollout.execution_identity(linked_project, "execution-intent-linked", framework)
        run("materialize-decision", "--profile", "ctx06c-fixture",
            "--execution-id", linked["executionId"], "--execution-version", "1",
            "--workspace-id", linked["workspaceId"], root=linked_project)
        linked_args = ("resolve", "--profile", "ctx06c-fixture", "--execution-id",
                       linked["executionId"], "--execution-version", "1",
                       "--workspace-id", linked["workspaceId"])
        assert json.loads(run(*linked_args, root=linked_project).stdout)["mode"] == "v2"
        # execution intent, external SELECTION, envelope-v2, bundle, HEAD and
        # receipt keep identity/binding but never the temporary project path.
        assert_durable_path_containment(project, Path(temporary))
        assert_durable_path_containment(linked_project, Path(temporary))
        linked_envelope["executionIntent"]["intentDigest"] = "sha256:" + "0" * 64
        envelope_path.write_bytes(canonical(linked_envelope))
        assert "CTX10_DECISION_AUTHORITY_REJECTED" in run(
            *linked_args, root=linked_project, ok=False).stderr

        old_project = Path(temporary) / "old-run"; old_project.mkdir()
        initialize_fixture(old_project, "execution-old-unanchored")
        rollout._atomic_replace(old_project, rollout.POLICY_RELATIVE,
                                canonical(fixture_policy), source=None)
        old_envelope = json.loads((old_project / ".mana/runtime/runs/execution-old-unanchored/execution-envelope-v1.json").read_text())
        assert old_envelope["schemaVersion"] == "mana.context-runtime.execution-envelope/v1"
        old_workspace = old_envelope["workspaceId"]
        old_result = run("materialize-decision", "--profile", "ctx06c-fixture",
                         "--execution-id", "execution-old-unanchored",
                         "--execution-version", "1", "--workspace-id", old_workspace,
                         root=old_project, ok=False)
        assert "CTX10_DECISION_AUTHORITY_REJECTED" in old_result.stderr
        assert not (old_project / ".mana/runtime/execution-intents").exists()
    print("Context Runtime CTX-10-R2.5 rollout tests passed (external intent, full closure rewrite, lifecycle, managed blocks, no-links, privacy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
