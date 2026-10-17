"""v2.4.2 data-safety tests. Everything runs in a temporary folder; the real database is never used."""
import sqlite3, tempfile, unittest
from pathlib import Path
import data_safety as ds


def make_db(path, marker='original'):
    c = sqlite3.connect(path)
    c.executescript('CREATE TABLE users(id TEXT); CREATE TABLE projects(id TEXT, name TEXT);')
    c.execute('INSERT INTO projects VALUES(?,?)', ('p1', marker)); c.commit(); c.close()


def project_name(path):
    c = sqlite3.connect(path)
    try: return c.execute('SELECT name FROM projects').fetchone()[0]
    finally: c.close()


class DataSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / 'buildquant.db'
        self.bk = self.root / 'backups'
        make_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_is_complete_copy(self):
        b = ds.backup_database(self.db, self.bk, 'manual')
        self.assertTrue(b.is_file())
        self.assertEqual(project_name(b), 'original')
        self.assertEqual(ds.integrity_check(b)[0], 'ok')

    def test_no_database_no_backup(self):
        self.assertIsNone(ds.backup_database(self.root / 'missing.db', self.bk))

    def test_daily_backup_only_once_per_day(self):
        self.assertIsNotNone(ds.daily_startup_backup(self.db, self.bk, today=None))
        self.assertIsNone(ds.daily_startup_backup(self.db, self.bk, today=None))
        self.assertEqual(len(ds.list_backups(self.bk)), 1)

    def test_prune_keeps_manual_backups(self):
        self.bk.mkdir()
        for day in range(1, 36):
            (self.bk / f'buildquant_202601{day:02d}_000000_auto.db').write_bytes(b'x') if day <= 31 else \
                (self.bk / f'buildquant_202602{day-31:02d}_000000_auto.db').write_bytes(b'x')
        (self.bk / 'buildquant_20250101_000000_manual.db').write_bytes(b'x')
        removed = ds.prune_auto_backups(self.bk, keep=30)
        self.assertEqual(len(removed), 5)
        names = [p.name for p in ds.list_backups(self.bk)]
        self.assertIn('buildquant_20250101_000000_manual.db', names)
        self.assertEqual(sum('_auto' in n for n in names), 30)

    def test_migrations_recorded_once(self):
        c = sqlite3.connect(self.db)
        ds.record_migration(c, '2.4.2', 'first'); ds.record_migration(c, '2.4.2', 'second')
        c.commit()
        hist = ds.migration_history(c); c.close()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0][1], 'first')

    def test_restore_replaces_and_saves_current(self):
        good = ds.backup_database(self.db, self.bk, 'manual')
        c = sqlite3.connect(self.db); c.execute("UPDATE projects SET name='changed'"); c.commit(); c.close()
        safety = ds.restore_database(good, self.db, self.bk, check_server=False)
        self.assertEqual(project_name(self.db), 'original')      # restored
        self.assertEqual(project_name(safety), 'changed')        # the replaced state was kept

    def test_restore_rejects_non_civora_file(self):
        other = self.root / 'other.db'
        c = sqlite3.connect(other); c.execute('CREATE TABLE x(a)'); c.commit(); c.close()
        with self.assertRaises(RuntimeError):
            ds.restore_database(other, self.db, self.bk, check_server=False)
        self.assertEqual(project_name(self.db), 'original')

    def test_restore_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            ds.restore_database(self.root / 'nope.db', self.db, self.bk, check_server=False)


if __name__ == '__main__':
    unittest.main()
