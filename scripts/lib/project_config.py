"""Resolve project preferences under a locally registered workspace root."""

import os
import re
import stat
from pathlib import Path

LIMIT = 65536
TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class ConfigError(ValueError):
    pass


def fail(path, key, message):
    raise ConfigError(f"{path}: {key}: {message}")


def config_path():
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    if not base.is_absolute():
        fail(base, "locations", "configuration directory must be absolute")
    return base / "mana" / "locations.toml"


def read_config(path, dir_fd=None):
    if not hasattr(os, "O_NOFOLLOW"):
        try:
            path.lstat()
        except FileNotFoundError:
            return None
        fail(path, "file", "host cannot open configuration files without following links")
    try:
        fd = os.open(path.name if dir_fd is not None else path,
                     os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        fail(path, "file", str(exc))
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            fail(path, "file", "expected a regular, single-link file")
        raw = source.read(LIMIT + 1)
    if len(raw) > LIMIT:
        fail(path, "file", "configuration exceeds 64 KiB")
    try:
        import tomllib
    except ImportError:
        fail(path, "file", "TOML configuration requires Python 3.11 or later")
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        fail(path, "TOML", str(exc))
    if type(data.get("version")) is not int or data["version"] != 1:
        fail(path, "version", "expected version = 1")
    return data


def table(value, path, key, keys=None):
    if not isinstance(value, dict):
        fail(path, key, "expected a table")
    if keys is not None:
        for name in sorted(value.keys() - keys):
            fail(path, f"{key}.{name}" if key else name, "unknown key")
    return value


def token(value, path, key):
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        fail(path, key, "expected a lowercase identifier")
    return value


def flag(value, path, key):
    if type(value) is not bool:
        fail(path, key, "expected a boolean")
    return value


def directory(value, path, key):
    if not isinstance(value, str) or not Path(value).is_absolute():
        fail(path, key, "expected an absolute directory path")
    try:
        declared = Path(value)
        result = declared.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        fail(path, key, str(exc))
    if result != declared:
        fail(path, key, "use a canonical path without symbolic links or parent traversal")
    return result


def named_paths(data, path, key):
    return {
        token(name, path, key): directory(value, path, f"{key}.{name}")
        for name, value in table(data, path, key).items()
    }


def allowed(values, bindings, path, key):
    if not isinstance(values, list):
        fail(path, key, "expected an array of aliases")
    result = {}
    for value in values:
        name = token(value, path, key)
        if name not in bindings or name in result:
            fail(path, key, f"unknown or repeated alias {name}")
        result[name] = bindings[name]
    return result


def contains(parent, child):
    if child.is_relative_to(parent):
        return True
    if parent.exists():
        for part in (child, *child.parents):
            if part.exists() and part.samefile(parent):
                return True
    return False


def directory_identity(path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise ConfigError(f"{path}: expected a directory")
    return info.st_dev, info.st_ino


def registry(path):
    data = read_config(path)
    if data is None:
        return {}
    table(data, path, "", {"version", "roots", "vaults", "knowledge"})
    vaults = named_paths(data.get("vaults", {}), path, "vaults")
    knowledge = named_paths(data.get("knowledge", {}), path, "knowledge")
    personal_root = knowledge.get("personal")
    if personal_root is not None:
        for alias, source in knowledge.items():
            if alias != "personal" and (contains(source, personal_root) or contains(personal_root, source)):
                fail(path, f"knowledge.{alias}", "shared and personal knowledge locations must not overlap")
    roots = {}
    declared_paths = set()
    for name, value in table(data.get("roots", {}), path, "roots").items():
        key = f"roots.{token(name, path, 'roots')}"
        entry = table(value, path, key, {"path", "vaults", "knowledge", "allow_personal", "allow_runtime"})
        root = directory(entry.get("path"), path, key + ".path")
        identity = directory_identity(root)
        if (root == Path(root.anchor) or root in declared_paths or
                (identity is not None and identity in roots)):
            fail(path, key + ".path", "filesystem root or duplicate workspace root")
        declared_paths.add(root)
        personal = flag(entry.get("allow_personal", False), path, key + ".allow_personal")
        sources = allowed(entry.get("knowledge", []), knowledge, path, key + ".knowledge")
        if "personal" in sources and not personal:
            fail(path, key + ".knowledge", "personal requires allow_personal = true")
        bindings = {
            "name": name,
            "vaults": allowed(entry.get("vaults", []), vaults, path, key + ".vaults"),
            "knowledge": sources,
            "allow_runtime": flag(entry.get("allow_runtime", False), path, key + ".allow_runtime"),
        }
        if identity is not None:
            roots[identity] = bindings
    return roots


def preferences(data, path, project, scope):
    table(data, path, "", {"version", "export", "knowledge", "profiles", "project"})
    identity = table(data.get("project", {}), path, "project", {"id"})
    if "project" in data and path.parent != project:
        fail(path, "project", "identity belongs in the project directory")
    if "id" in identity:
        yield "project.id", token(identity["id"], path, "project.id")
    export = table(data.get("export", {}), path, "export", {"vault"})
    if "vault" in export:
        alias = token(export["vault"], path, "export.vault")
        if alias not in scope["vaults"]:
            fail(path, "export.vault", f"vault alias {alias} is not enabled for this root")
        yield "export.vault", alias
    kb = table(data.get("knowledge", {}), path, "knowledge", {"sources"})
    for name, value in table(kb.get("sources", {}), path, "knowledge.sources").items():
        key = f"knowledge.sources.{token(name, path, 'knowledge.sources')}"
        enabled = flag(value, path, key)
        if name not in scope["knowledge"] and (enabled or name != "personal"):
            fail(path, key, "knowledge alias is not enabled for this root")
        yield key, enabled
    for name, value in table(data.get("profiles", {}), path, "profiles").items():
        key = f"profiles.{token(name, path, 'profiles')}"
        profile = table(value, path, key, {"runtime", "skills"})
        if "runtime" in profile:
            mode = profile["runtime"]
            if mode not in ("legacy", "v2", "shadow"):
                fail(path, key + ".runtime", "expected legacy, v2 or shadow")
            yield key + ".runtime", mode
        for skill, enabled in table(profile.get("skills", {}), path, key + ".skills").items():
            skill_key = f"{key}.skills.{token(skill, path, key + '.skills')}"
            yield skill_key, flag(enabled, path, skill_key)


def resolve(project):
    project = Path(project).resolve(strict=True)
    if not project.is_dir():
        fail(project, "project", "expected a directory")
    locations = config_path()
    roots = registry(locations)
    root = None
    scope = {}
    if roots:
        for candidate in (project, *project.parents):
            match = roots.get(directory_identity(candidate))
            if match is not None:
                root, scope = candidate, match
                break
    result = {
        "schema": "mana.project-config/v1",
        "projectRoot": str(project),
        "workspaceRoot": str(root) if root else None,
        "reason": "unregistered-project",
        "files": [],
        "settings": {},
        "defaults": {"runtime": "legacy", "export": "manual"},
    }
    if root is None:
        return result, {}
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root, flags)
    parent = root
    try:
        root_info = os.fstat(fd)
        if roots.get((root_info.st_dev, root_info.st_ino)) is not scope:
            fail(root, "workspace root", "directory changed during configuration discovery")
        for component in (None, *project.relative_to(root).parts):
            if component is not None:
                child = os.open(component, flags, dir_fd=fd)
                os.close(fd)
                fd = child
                parent /= component
            path = parent / "mana.toml"
            data = read_config(path, fd)
            if data is None:
                continue
            result["files"].append(str(path))
            for key, value in preferences(data, path, project, scope):
                result["settings"][key] = {"value": value, "source": str(path)}
    finally:
        os.close(fd)
    result["reason"] = "resolved" if result["files"] else "no-project-config"
    return result, scope
