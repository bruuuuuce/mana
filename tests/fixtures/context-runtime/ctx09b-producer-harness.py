"""TEST ONLY: local producers use fixed host runtime publication entry points.

Not installed, not a comparator option, and never an existing-file attestor.
Replacing a previous fixture models a distinct test execution/publication.
"""
from pathlib import Path


def publish_pair(mode, project, execution_id, left, right, profile_id="fixture-review", target_key="a" * 64):
    directory = Path(project) / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    for name, payload, publisher in (("legacy", left, mode.publish_legacy_artifact),
                                     ("v2", right, mode.publish_v2_artifact)):
        path = directory / (name + ".json")
        if path.exists():
            path.unlink()
        options = {"execution_version": 1} if name == "v2" else {}
        publisher(project, execution_id, profile_id, target_key, "artifacts/" + name + ".json", payload, **options)
