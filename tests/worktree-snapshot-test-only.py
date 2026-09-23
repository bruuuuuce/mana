#!/usr/bin/env python3
"""Canonical CTX-09G filesystem inventory; excludes only the Git database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb", buffering=0) as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def record(root: Path, path: Path) -> dict[str, object]:
    info = path.lstat()
    mode = stat.S_IMODE(info.st_mode)
    relative = "." if path == root else path.relative_to(root).as_posix()
    common: dict[str, object] = {
        "path": relative,
        "mode": mode,
        "size": info.st_size,
        "device": info.st_dev,
        "inode": info.st_ino,
    }
    if stat.S_ISREG(info.st_mode):
        return {**common, "type": "file", "sha256": digest(path)}
    if stat.S_ISDIR(info.st_mode):
        return {**common, "type": "directory"}
    if stat.S_ISLNK(info.st_mode):
        return {**common, "type": "symlink", "target": os.readlink(path)}
    kinds = ((stat.S_ISFIFO, "fifo"), (stat.S_ISSOCK, "socket"),
             (stat.S_ISCHR, "character"), (stat.S_ISBLK, "block"))
    return {**common, "type": next((name for check, name in kinds if check(info.st_mode)), "other")}


def walk(root: Path):
    yield root
    stack = [root]
    while stack:
        parent = stack.pop()
        children = sorted((Path(item.path) for item in os.scandir(parent)),
                          key=lambda item: os.fsencode(item.name), reverse=True)
        for child in children:
            if parent == root and child.name == ".git":
                continue
            yield child
            if child.is_dir() and not child.is_symlink():
                stack.append(child)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    args = parser.parse_args()
    root = Path(args.root).resolve(strict=True)
    for path in sorted(walk(root), key=lambda item: os.fsencode(str(item.relative_to(root))) if item != root else b""):
        print(json.dumps(record(root, path), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
