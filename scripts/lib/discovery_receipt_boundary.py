"""Reserved Discovery diagnostic paths and descriptor-based publisher admission."""
import os
from pathlib import Path
import re
import stat

NAMESPACE = '.mana-story-start-discovery'
_LEGACY_NAME = re.compile(r'(?:story-start-discovery-failure-[0-9a-f]{32}\.json|\.discovery-receipt-[0-9a-f]{32})', re.IGNORECASE)


def is_private_discovery_path(relative):
    """Reserve exact operational components, never fold workspace/artifact IDs."""
    parts = relative.split('/')
    if len(parts) < 4 or parts[0].casefold() != '.mana' or parts[1].casefold() not in ('features', 'sessions'):
        return False
    if not parts[2]:
        return False
    if parts[3].casefold() == NAMESPACE:
        return True
    return len(parts) == 5 and parts[3].casefold() == 'evidence' and _LEGACY_NAME.fullmatch(parts[4]) is not None


def directory_flags():
    # POSIX publisher capability; read-only path policy remains importable on Windows.
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def require_canonical_entry(parent, name, opened=None):
    """Reject case aliases, including distinct aliases on case-sensitive volumes.

    Enumeration checks the stored spelling; lstat/fstat binds it to the opened
    object rather than trusting the caller's spelling of a filesystem alias.
    """
    names = [entry for entry in os.listdir(parent) if entry.casefold() == name]
    if any(entry != name for entry in names):
        raise ValueError('noncanonical diagnostic path')
    if opened is not None:
        if names != [name]:
            raise ValueError('missing canonical diagnostic directory')
        entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
        actual = os.fstat(opened)
        if not stat.S_ISDIR(entry.st_mode) or (entry.st_dev, entry.st_ino) != (actual.st_dev, actual.st_ino):
            raise ValueError('diagnostic directory identity changed')


def open_discovery_workspace(workspace):
    """Pin the workspace and validate the reserved workspace ancestry, if used.

    Standalone host-owned workspaces remain supported. Under .mana the accepted
    layout is exactly .mana/{features,sessions}/<opaque workspace ID>.
    """
    flags = directory_flags()
    path = Path(os.path.abspath(workspace))
    parts = path.parts
    if not any(part.casefold() == '.mana' for part in parts):
        return os.open(workspace, flags)
    if len(parts) < 4 or parts[-3] != '.mana' or parts[-2] not in ('features', 'sessions'):
        raise ValueError('noncanonical diagnostic workspace path')
    parents = []
    try:
        # Open each relevant component relative to a pinned project directory.
        # O_NOFOLLOW on the last workspace alone would not reject a symlink in
        # .mana or features/sessions, even if its target had canonical names.
        current = os.open(path.parents[2], flags)
        parents.append(current)
        for index, name in enumerate(parts[-3:]):
            opened = os.open(name, flags, dir_fd=current)
            parents.append(opened)
            if index < 2:
                require_canonical_entry(current, name, opened)
            current = opened
        return parents.pop()
    finally:
        for descriptor in reversed(parents):
            os.close(descriptor)
