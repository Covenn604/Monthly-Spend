from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import migration

class MigrationTests(unittest.TestCase):
    def test_committed_wal_data_and_all_user_folders_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for folder in [root,root/'users'/'2',root/'users'/'3']:
                folder.mkdir(parents=True,exist_ok=True)
                path=folder/'monthly-spend.sqlite3'
                subprocess.run([sys.executable,'-c',"import sqlite3,sys,os; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA journal_mode=WAL'); c.execute('CREATE TABLE saved(value)'); c.execute('INSERT INTO saved VALUES (42)'); c.commit(); os._exit(0)",str(path)],check=True)
            migration.migrate_all(root)
            migration.migrate_all(root)
            for folder in [root,root/'users'/'2',root/'users'/'3']:
                self.assertFalse((folder/'monthly-spend.sqlite3').exists())
                with sqlite3.connect(folder/'spearmint.sqlite3') as c:
                    self.assertEqual(c.execute('SELECT value FROM saved').fetchone()[0],42)
    def test_conflicting_files_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'monthly-spend.sqlite3').write_bytes(b'old')
            (folder/'spearmint.sqlite3').write_bytes(b'new')
            with self.assertRaises(ValueError): migration.financial_database(folder)
            self.assertEqual((folder/'monthly-spend.sqlite3').read_bytes(),b'old')
            self.assertEqual((folder/'spearmint.sqlite3').read_bytes(),b'new')
