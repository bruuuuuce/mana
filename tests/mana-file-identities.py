#!/usr/bin/env python3
"""Preserve full NTFS identities in both derived SQLite indexes."""
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

knowledge = load('mana-knowledge')
catalog = knowledge.catalog

class FileIdentityTest(unittest.TestCase):
    def test_wide_ids_reuse_and_replacement_keep_all_bits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / '.mana/global/architecture.md'
            source.parent.mkdir(parents=True)
            source.write_text('# Architecture\nWide file identity.\n')
            stat = source.stat()
            info = SimpleNamespace(**{name: getattr(stat, name) for name in ('st_size', 'st_mode', 'st_mtime_ns', 'st_ctime_ns')}, st_dev=(1 << 80) + 5, st_ino=(1 << 120) + 7)
            database = root / 'catalog.sqlite'
            admitted = [(source.relative_to(root).as_posix(), source, info)]
            with patch.object(catalog, 'discover', return_value=(admitted, {})):
                first = catalog.build_database(root, database, 'test-project')
                self.assertEqual(first['hashed_files'], 1)
                self.assertEqual(catalog.build_database(root, database, 'test-project')['reused_files'], 1)
                with sqlite3.connect(database) as connection:
                    row = connection.execute('SELECT device,inode,typeof(device),typeof(inode) FROM entries').fetchone()
                self.assertEqual(row, (f'integer:{info.st_dev}', f'integer:{info.st_ino}', 'text', 'text'))
                # Same bytes, size and times; a new wide ID must invalidate reuse.
                info.st_ino += 1
                self.assertEqual(catalog.build_database(root, database, 'test-project')['hashed_files'], 1)
            target = knowledge.Source('doc:test', admitted[0][0], source, 'project', 'active', None, info, False)
            with patch.object(catalog, 'status', return_value=('current', '', {})), patch.object(knowledge, 'discover', return_value=([target], [], 'wide-id-signature')):
                knowledge.build(root, database, 'test-project')
            with sqlite3.connect(database) as connection:
                row = connection.execute('SELECT device,inode,typeof(inode) FROM knowledge_documents').fetchone()
            self.assertEqual(row, (f'integer:{info.st_dev}', f'integer:{info.st_ino}', 'text'))
            self.assertEqual(catalog.sqlite_file_identity(123), 123)
            self.assertNotEqual(catalog.sqlite_file_identity(info.st_ino), catalog.sqlite_file_identity(info.st_ino + 1))

if __name__ == '__main__':
    unittest.main()
