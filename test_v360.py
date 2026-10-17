"""v3.6.0 tests: cloud backup / restore, multi-drawing analysis, Vastu guide, per sq.ft rate.
Pure unit tests - no server, no network, no real database touched."""
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import persistence_v360 as pv
import sqft_rate_v360 as sq
import vastu_v360 as vastu

HAVE_CALC = importlib.util.find_spec('fastapi') is not None   # intelligent_recognition imports fastapi


def make_data(folder, users=1, projects=1, files=2):
    folder = Path(folder)
    (folder / 'uploads').mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(folder / 'buildquant.db')
    c.execute('CREATE TABLE users(id TEXT PRIMARY KEY, name TEXT)')
    c.execute('CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT)')
    c.executemany('INSERT INTO users VALUES(?,?)', [(f'u{i}', 'User') for i in range(users)])
    c.executemany('INSERT INTO projects VALUES(?,?)', [(f'p{i}', 'House') for i in range(projects)])
    c.commit(); c.close()
    (folder / 'session.key').write_text('KEY123')
    for i in range(files):
        (folder / 'uploads' / f'f{i}.png').write_bytes(b'x' * 1000)
    return folder


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.pop(k, None) for k in ('CIVORA_DATA_DIR', 'CIVORA_BACKUP_REPO', 'CIVORA_BACKUP_TOKEN', 'RENDER', 'CIVORA_SECRET_KEY')}

    def tearDown(self):
        for k, v in self._env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_snapshot_round_trip_restores_users_projects_files_and_key(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            make_data(a, users=2, projects=3)
            blob, manifest, skipped = pv.build_snapshot(a, 25)
            self.assertEqual((manifest['users'], manifest['projects'], skipped), (2, 3, 0))
            m = pv.restore_snapshot(blob, b)
            self.assertEqual(m['projects'], 3)
            self.assertEqual(pv._count(Path(b) / 'buildquant.db', 'users'), 2)
            self.assertEqual((Path(b) / 'session.key').read_text(), 'KEY123')
            self.assertTrue((Path(b) / 'uploads' / 'f1.png').is_file())

    def test_upload_budget_skips_large_files(self):
        with tempfile.TemporaryDirectory() as a:
            make_data(a, files=1)
            (Path(a) / 'uploads' / 'big.pdf').write_bytes(b'x' * 3 * 1024 * 1024)
            blob, manifest, skipped = pv.build_snapshot(a, 1)
            self.assertEqual(skipped, 1)
            self.assertIn('big.pdf', manifest['skipped_files'])

    def test_restore_ignores_unsafe_names(self):
        import io, tarfile
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            make_data(a)
            good, _, _ = pv.build_snapshot(a, 25)
            buf = io.BytesIO()
            with tarfile.open(fileobj=io.BytesIO(good), mode='r:gz') as src, tarfile.open(fileobj=buf, mode='w:gz') as out:
                for m in src.getmembers():
                    out.addfile(m, src.extractfile(m))
                evil = tarfile.TarInfo('../evil.txt'); evil.size = 3
                out.addfile(evil, io.BytesIO(b'bad'))
            pv.restore_snapshot(buf.getvalue(), b)
            self.assertFalse((Path(b).parent / 'evil.txt').exists())

    def test_empty_database_detection(self):
        with tempfile.TemporaryDirectory() as a:
            self.assertTrue(pv.db_is_empty(Path(a) / 'missing.db'))
            make_data(a, users=0, projects=0)
            self.assertTrue(pv.db_is_empty(Path(a) / 'buildquant.db'))
        with tempfile.TemporaryDirectory() as a:
            make_data(a)
            self.assertFalse(pv.db_is_empty(Path(a) / 'buildquant.db'))

    def test_modes(self):
        self.assertEqual(pv.storage_mode(), 'local')
        os.environ['RENDER'] = 'true'
        self.assertEqual(pv.storage_mode(), 'temporary')
        os.environ['CIVORA_BACKUP_REPO'] = 'me/civora-data'; os.environ['CIVORA_BACKUP_TOKEN'] = 't'
        self.assertEqual(pv.storage_mode(), 'cloud-backup')
        os.environ['CIVORA_DATA_DIR'] = '/tmp/x'
        self.assertEqual(pv.storage_mode(), 'disk+cloud-backup')

    def test_secret_key_from_env_or_file(self):
        with tempfile.TemporaryDirectory() as a:
            k = Path(a) / 'session.key'
            first = pv.secret_key(k)
            self.assertEqual(pv.secret_key(k), first)          # stable across restarts when the file is kept
            os.environ['CIVORA_SECRET_KEY'] = 'from-env'
            self.assertEqual(pv.secret_key(k), 'from-env')

    def test_fingerprint_changes_with_data(self):
        with tempfile.TemporaryDirectory() as a:
            make_data(a)
            f1 = pv.fingerprint(a)
            (Path(a) / 'uploads' / 'new.png').write_bytes(b'y')
            self.assertNotEqual(f1, pv.fingerprint(a))


class SqftRateTests(unittest.TestCase):
    def test_example_1000_sqft_at_2500(self):
        c = sq.calc(1000, 2500, 2300000)
        self.assertEqual(c['total'], 2500000)
        self.assertEqual(c['diff'], 200000)
        self.assertEqual(c['boq_per_sqft'], 2300)
        self.assertEqual(sq.inr(c['total']), '₹ 25,00,000')

    def test_validation(self):
        self.assertEqual(sq.validate_rate('2,500'), 2500)
        for bad in ('abc', '5', '999999'):
            with self.assertRaises(ValueError):
                sq.validate_rate(bad)

    def test_box_without_saving(self):
        h = sq.box_html('', 1000, 0, save=False, rate=2500)
        self.assertIn('₹ 25,00,000', h)
        self.assertNotIn('<form', h)


class VastuTests(unittest.TestCase):
    def test_classic_layout_scores_well(self):
        r = vastu.evaluate('E', {'entrance': 'E', 'pooja': 'NE', 'kitchen': 'SE', 'master': 'SW', 'toilet': 'NW'})
        self.assertEqual(r['score'], 100)
        self.assertEqual(r['grade'][0], 'Very good')

    def test_avoid_placements_flagged_with_suggestion(self):
        r = vastu.evaluate('N', {'kitchen': 'NE', 'toilet': 'NE'})
        self.assertTrue(all(i['status'] == 'avoid' and i['tip'] for i in r['items']))
        self.assertEqual(r['score'], 0)

    def test_entrance_depends_on_facing(self):
        self.assertEqual(vastu.check('entrance', 'S', 'S'), 'ideal')
        self.assertEqual(vastu.check('entrance', 'S', 'E'), 'avoid')
        self.assertEqual(vastu.check('entrance', 'SW', 'W'), 'avoid')

    def test_one_avoid_caps_grade(self):
        r = vastu.evaluate('E', {'entrance': 'E', 'pooja': 'NE', 'kitchen': 'SE', 'master': 'SW', 'toilet': 'NE'})
        self.assertLess(r['score'], 80)

    def test_parse_requires_facing(self):
        with self.assertRaises(ValueError):
            vastu.parse({'z_kitchen': 'SE'})
        self.assertEqual(vastu.parse({'facing': 'W', 'z_kitchen': 'SE', 'z_pooja': 'XX'}), ('W', {'kitchen': 'SE'}))


@unittest.skipUnless(HAVE_CALC, 'needs fastapi (calculation module imports it)')
class MultiDrawingTests(unittest.TestCase):
    def setUp(self):
        import multi_drawing_v360 as md
        import smart_estimate_v260 as se
        from engineering import takeoff
        from test_v260_smart import plan_schedule
        self.md, self.se, self.takeoff, self.plan = md, se, takeoff, plan_schedule

    def _tot(self, r):
        from collections import defaultdict
        d = defaultdict(float)
        for _, _, items in r['rows']:
            for it in items:
                d[(it['material'], it['unit'])] += float(it['quantity'])
        return d

    def test_two_identical_floors_equal_two_floor_single_estimate(self):
        se, sch = self.se, self.plan()
        inp = se.build_inputs(sch, 1162)
        two = dict(inp); two['floors'] = {'value': 2, 'source': 'user', 'note': ''}
        a = se.estimate(two, se.default_options(), self.takeoff, sch)
        b = self.md.combined_estimate([('GF', inp, sch), ('FF', inp, sch)], se.default_options(), self.takeoff)
        ta, tb = self._tot(a), self._tot(b)
        for k in set(ta) | set(tb):
            self.assertAlmostEqual(ta[k], tb[k], delta=0.01 * max(abs(ta[k]), 1), msg=k)
        self.assertAlmostEqual(a['builtup_sqft'], b['builtup_sqft'], places=3)

    def test_smaller_first_floor_measured_on_own_size(self):
        se, sch = self.se, self.plan()
        sch2 = self.plan(); sch2['evidence']['overall_length']['value'] = 10.0
        g = se.build_inputs(sch, 1162); f = se.build_inputs(sch2, 1000)
        b = self.md.combined_estimate([('GF', g, sch), ('FF', f, sch2)], se.default_options(), self.takeoff)
        self.assertAlmostEqual(b['builtup_sqft'], (12 * 9 + 10 * 9) * se.SQFT_PER_M2, places=2)
        roof = [r for r in b['rows'] if 'Roof waterproofing' in r[0]]
        self.assertEqual(len(roof), 1)
        self.assertTrue(roof[0][0].startswith('FF'))

    def test_checks(self):
        md, sch = self.md, self.plan()
        sheets = [{'name': 'a', 'role': 'ff', 'schedule': sch, 'digest': '1'},
                  {'name': 'b', 'role': 'ff', 'schedule': sch, 'digest': '1'}]
        texts = ' '.join(t for _, t in md.compare(sheets))
        self.assertIn('same file', texts)
        self.assertIn('No sheet is marked as Ground floor', texts)
        self.assertIn('More than one sheet', texts)

    def test_role_guess_and_fill(self):
        md, sch = self.md, self.plan()
        self.assertEqual(md.guess_role('First Floor Plan.pdf', sch, {'gf'}), 'ff')
        self.assertEqual(md.guess_role('SECTION A-A.dxf', sch, set()), 'section')
        self.assertEqual(md.guess_role('plan.png', sch, set()), 'gf')
        plan = {'evidence': {'overall_length': {'value': 12, 'source': ''}}}
        filled = md.fill_from(plan, [{'name': 'sec', 'schedule': {'evidence': {'height': {'value': 3.2, 'source': 'FFL'}}}}])
        self.assertEqual(filled['evidence']['height']['value'], 3.2)
        self.assertIn('from sec', filled['evidence']['height']['source'])


if __name__ == '__main__':
    unittest.main()
