"""v3.8.0: Recycle Bin, site owner, six sections, market rates, new structural elements."""
import os
import sqlite3
import unittest

import admin_v380 as av
import rates_v260 as rv
import structural_v210 as sv
import ui_shell


def mem():
    c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
    c.executescript('''CREATE TABLE users(id TEXT PRIMARY KEY, name TEXT, username TEXT);
    CREATE TABLE projects(id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id), name TEXT);
    CREATE TABLE uploads(id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), stored_name TEXT);
    CREATE TABLE civora_boq_reports(id TEXT PRIMARY KEY, project_id TEXT, payload TEXT);''')
    c.execute('CREATE TABLE civora_bin_v380 (id TEXT PRIMARY KEY, batch TEXT NOT NULL, tbl TEXT NOT NULL, row_json TEXT NOT NULL, project_id TEXT, deleted_by TEXT, deleted_at INTEGER NOT NULL, label TEXT NOT NULL DEFAULT \'\')')
    c.execute('PRAGMA foreign_keys=ON')
    c.execute("INSERT INTO users VALUES('u1','Ravi','ravi'),('o','Owner','nishanth_s')")
    c.execute("INSERT INTO projects VALUES('p1','u1','House')")
    c.execute("INSERT INTO uploads VALUES('f1','p1','f1.png')")
    c.execute("INSERT INTO civora_boq_reports VALUES('b1','p1','{}'),('b2','p1','{}')")
    return av.BinConnection(c)


class BinTests(unittest.TestCase):
    def test_delete_goes_to_bin_and_restores(self):
        c = mem()
        tok = av.CTX.set({'uid': 'u1', 'path': '/x'})
        try:
            c.execute('DELETE FROM civora_boq_reports WHERE id=? AND project_id=?', ('b1', 'p1'))
        finally:
            av.CTX.reset(tok)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM civora_boq_reports').fetchone()[0], 1)
        bs = av.batches(c)
        self.assertEqual(len(bs), 1)
        self.assertEqual(bs[0]['who'], 'u1')
        av.restore(c, bs[0]['batch'])
        self.assertEqual(c.execute('SELECT COUNT(*) FROM civora_boq_reports').fetchone()[0], 2)
        self.assertEqual(av.batches(c), [])

    def test_whole_user_in_one_batch_and_purge(self):
        c = mem()
        c.execute('CREATE TABLE remember_tokens(token_hash TEXT, user_id TEXT)')
        tok = av.CTX.set({'uid': 'o', 'path': '/admin'})
        try:
            av.delete_user_rows(c, 'u1')
        finally:
            av.CTX.reset(tok)
        self.assertIsNone(c.execute("SELECT 1 FROM users WHERE id='u1'").fetchone())
        b = av.batches(c)
        self.assertEqual(len(b), 1)
        title, what = av.describe(av.batch_rows(c, b[0]['batch']))
        self.assertIn('project', what)
        av.restore(c, b[0]['batch'])
        self.assertEqual(c.execute("SELECT COUNT(*) FROM uploads").fetchone()[0], 1)
        tok = av.CTX.set({'uid': 'o'})
        try:
            av.delete_user_rows(c, 'u1')
        finally:
            av.CTX.reset(tok)
        names = av.purge(c, av.batches(c)[0]['batch'], '/tmp')
        self.assertEqual(names, ['f1.png'])
        self.assertEqual(av.batches(c), [])

    def test_failed_delete_leaves_no_bin_rows(self):
        c = mem()
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("DELETE FROM projects WHERE id='p1'")          # uploads still point to it
        self.assertEqual(av.batches(c), [])

    def test_guard_protects_site_owner(self):
        c = mem()
        c.execute("INSERT INTO projects VALUES('po','o','Mine')")

        class R:
            method = 'POST'
            class url:
                path = '/projects/po/data/estimates/b1/delete'
        p = c.execute("SELECT * FROM projects WHERE id='po'").fetchone()
        with self.assertRaises(PermissionError):
            av.guard(c, R, p, 'u1')
        av.guard(c, R, p, 'o')                                         # the owner may


class ShellTests(unittest.TestCase):
    def test_sections(self):
        self.assertEqual(len(ui_shell.SECTIONS), 6)
        for path, want in (('/', '/'), ('/projects', '/projects'), ('/projects/x/smart/1', '/estimate'), ('/projects/x/bbs', '/structure'),
                           ('/projects/x/vastu', '/guide'), ('/rates', '/more'), ('/admin/users', '/more'), ('/projects/x', '/projects'),
                           ('/projects/x/boq', '/estimate'), ('/bin', '/more')):
            self.assertEqual(ui_shell.section_of(path), want, path)


class RateTests(unittest.TestCase):
    def test_market_defaults_editable(self):
        eff = rv.effective_rates({'cement_bag': 430, 'steel': 0})
        self.assertEqual(eff['cement_bag'], 430)
        self.assertEqual(eff['steel'], 0)                              # a saved 0 means "do not price"
        self.assertEqual(eff['brick'], rv.MARKET_RATES['brick'])
        self.assertEqual(set(rv.MARKET_RATES), set(rv.RATE_KEYS))


class ElementTests(unittest.TestCase):
    def test_round_and_triangular(self):
        import math
        self.assertAlmostEqual(sv.quantity('pile', 4, .45, .45, 9)['gross_m3'], 4 * math.pi / 4 * .45 ** 2 * 9)
        self.assertAlmostEqual(sv.quantity('stair_steps', 10, .3, 1.0, .15)['gross_m3'], 10 * .5 * .3 * .15)
        self.assertGreaterEqual(len(sv.ELEMENTS), 48)


if __name__ == '__main__':
    unittest.main()
