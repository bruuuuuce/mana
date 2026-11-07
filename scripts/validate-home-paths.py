#!/usr/bin/env python3
"""Reject personal home paths in tracked UTF-8 text files."""
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

# Exact fixture roots, restricted to the tests that exercise those platforms.
EXCEPTIONS = {
    'tests/mana-catalog.py': {('/Users/', 'test'), ('/home/', 'test')},
    'tests/context-runtime-delegation.py': {('/Users/', 'fixture-home')},
}
PATTERN = re.compile(r'(?i)(?<![\w])(?P<root>/users/|/home/|[a-z]:/users/)(?P<account>[^/\s"\'<>|:;,)}\]]+)')
ESCAPE = re.compile(r'\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})')


def normalize(line):
    for _ in range(2):
        line = unquote(line)
        line = ESCAPE.sub(lambda m: chr(int(m.group(1) or m.group(2), 16)), line)
        line = line.replace('\\/', '/').replace('\\\\', '/').replace('\\', '/')
    return line


def violations(path, content):
    allowed = EXCEPTIONS.get(path, set())
    for number, line in enumerate(content.splitlines(), 1):
        for match in PATTERN.finditer(normalize(line)):
            if (match.group('root'), match.group('account')) not in allowed:
                yield number


def main(root):
    root = Path(root).resolve()
    try:
        names = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z'])
        count = 0
        for raw in sorted(names.split(b'\0')):
            if not raw:
                continue
            name = raw.decode('utf-8', 'surrogateescape')
            try:
                target = root / name
                data = target.readlink().as_posix().encode() if target.is_symlink() else target.read_bytes()
            except OSError as error:
                print(f'{name!r}: cannot read tracked file: {error.strerror}', file=sys.stderr)
                return 2
            try:
                if data.startswith((b'\xff\xfe', b'\xfe\xff')):
                    content = data.decode('utf-16')
                elif b'\0' in data:
                    continue
                else:
                    content = data.decode('utf-8')
            except UnicodeDecodeError:
                continue
            for number in violations(name, content):
                print(f'{name!r}:{number}: personal home path detected', file=sys.stderr)
                count += 1
        return 1 if count else 0
    except (OSError, subprocess.CalledProcessError):
        print('Unable to enumerate tracked files', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
