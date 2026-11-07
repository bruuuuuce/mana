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
        line = re.sub(r'(?i)file://[^/\s]+(?=/)', 'file://', line)
    return line


def violations(path, content):
    allowed = EXCEPTIONS.get(path, set())
    for number, line in enumerate(content.splitlines(), 1):
        for match in PATTERN.finditer(normalize(line)):
            if (match.group('root'), match.group('account')) not in allowed:
                yield number


def text_content(data):
    try:
        if data.startswith((b'\xff\xfe', b'\xfe\xff')):
            return data.decode('utf-16')
        if b'\0' not in data:
            return data.decode('utf-8')
    except UnicodeDecodeError:
        if b'\0' not in data:
            return data.decode('latin-1')
    return None


def main(root):
    root = Path(root).resolve()
    try:
        entries = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--stage', '-z'])
        indexed = []
        for entry in entries.split(b'\0'):
            if not entry:
                continue
            metadata, raw_name = entry.split(b'\t', 1)
            mode, oid, stage = metadata.split()
            if stage != b'0':
                print('Unmerged index entries cannot be validated', file=sys.stderr)
                return 2
            indexed.append((raw_name.decode('utf-8', 'surrogateescape'), oid))
        indexed.sort()
        blobs = subprocess.check_output(
            ['git', '-C', str(root), 'cat-file', '--batch'],
            input=b''.join(oid + b'\n' for _, oid in indexed),
        )
        offset = 0
        count = 0
        for name, oid in indexed:
            end = blobs.index(b'\n', offset)
            header = blobs[offset:end].split()
            if len(header) != 3 or header[0] != oid or header[1] != b'blob':
                raise ValueError('invalid Git blob')
            size = int(header[2])
            offset = end + 1
            index_data = blobs[offset:offset + size]
            offset += size + 1
            target = root / name
            try:
                work_data = target.readlink().as_posix().encode() if target.is_symlink() else target.read_bytes()
            except OSError as error:
                print(f'{name!r}: cannot read tracked file: {error.strerror}', file=sys.stderr)
                return 2
            found = set()
            for data in (index_data, work_data):
                content = text_content(data)
                if content is not None:
                    found.update(violations(name, content))
            for number in sorted(found):
                print(f'{name!r}:{number}: personal home path detected', file=sys.stderr)
                count += 1
        return 1 if count else 0
    except (OSError, subprocess.CalledProcessError, ValueError, IndexError):
        print('Unable to enumerate or read tracked files', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
