"""v2.8.0 tests: Quick Estimate (built-up area only -> full estimate).

The app smoke test runs on a THROW-AWAY COPY in a temp folder; the real database is never used.
"""
import importlib.util, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

import quick_v280 as q
import smart_estimate_v260 as se

HERE = Path(__file__).resolve().parent
HAVE_FASTAPI = importlib.util.find_spec('fastapi') is not None


class ParseTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(q.parse_quick({'area': '1,000', 'floors': '2'}), (1000.0, 2))
        self.assertEqual(q.parse_quick({'area': '1200'}), (1200.0, 1))
        for bad in ({'area': ''}, {'area': 'abc'}, {'area': '50'}, {'area': '2000000'},
                    {'area': '1000', 'floors': '0'}, {'area': '1000', 'floors': 'x'}):
            with self.assertRaises(ValueError):
                q.parse_quick(bad)

    def test_inputs_split_area_over_floors(self):
        inp = q.quick_inputs(2000, 2)                      # 1000 sq.ft per floor
        side = (1000 / se.SQFT_PER_M2) ** 0.5
        self.assertAlmostEqual(inp['length']['value'], round(side, 2), places=2)
        self.assertEqual(inp['floors']['value'], 2)
        self.assertEqual(inp['floors']['source'], 'user')
        self.assertIn('2,000 sq.ft ÷ 2 floor(s)', inp['length']['note'])


@unittest.skipUnless(HAVE_FASTAPI, 'needs fastapi (intelligent_recognition imports it)')
class EstimateTests(unittest.TestCase):
    def test_1000_sqft_gives_every_main_material(self):
        from engineering import takeoff
        inp, opts, r = q.quick_estimate(1000, 1, takeoff)
        agg = q.material_totals(r['rows'])
        for key, unit, _ in q.GUEST_KEYS:
            self.assertGreater(agg.get((key, unit), 0), 0, key)
        self.assertAlmostEqual(r['builtup_sqft'], 1000, delta=1)
        # sanity ranges for a 1,000 sq.ft RCC-framed ground floor (planning thumb rules)
        self.assertTrue(80 < agg[('Cement', 'bags (50 kg)')] < 250)
        self.assertTrue(2000 < agg[('Steel planning allowance (not BBS)', 'kg')] < 6000)

    def test_same_total_more_floors_more_frame(self):
        from engineering import takeoff
        _, _, g = q.quick_estimate(2000, 1, takeoff)
        _, _, g1 = q.quick_estimate(2000, 2, takeoff)
        self.assertAlmostEqual(g['builtup_sqft'], g1['builtup_sqft'], delta=2)
        self.assertGreater(g1['frame']['column'], g['frame']['column'])   # taller columns
        self.assertLess(g1['frame']['footing'], g['frame']['footing'])    # smaller footprint, fewer footings


SMOKE = textwrap.dedent(r'''
    import re, sqlite3
    from fastapi.testclient import TestClient
    from app import app

    def tok(html):
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    # guest: quantities only, nothing saved
    g = TestClient(app)
    home = g.get('/').text
    assert 'action="/quick"' in home
    r = g.post('/quick', data={'confirm': '1', 'csrf_token': tok(home), 'area': '1000', 'floors': '1'})
    assert r.status_code == 200 and 'NOT SAVED' in r.text and 'Cement' in r.text and 'Create free account' in r.text, r.text[:300]
    bad = g.post('/quick', data={'confirm': '1', 'csrf_token': tok(home), 'area': '20'})
    assert 'must be between' in bad.text

    # signed in: project + priced draft BOQ in one click
    c = TestClient(app)
    c.post('/register', data={'name': 'Quick User', 'username': 'quick_user', 'password': 'quick-password-1', 'remember': '',
                              'csrf_token': tok(c.get('/register').text)})
    c.post('/rates', data={'csrf_token': tok(c.get('/rates').text), 'cement_bag': '420', 'steel': '68', 'rmc': '5600', 'labour_sqft': '450'})
    home = c.get('/').text
    r = c.post('/quick', data={'confirm': '1', 'csrf_token': tok(home), 'area': '1000', 'floors': '2'}, follow_redirects=False)
    assert r.status_code == 303 and '/workflow?estimate=' in r.headers['location'], (r.status_code, r.text[:300])
    w = c.get(r.headers['location']).text
    assert 'Estimate ready' in w and 'conic-gradient' in w and 'per sq.ft' in w
    assert 'Quick estimate – 1,000 sq.ft' in c.get('/projects').text
    P = r.headers['location'].split('/workflow')[0]
    boq = re.search(r'href="(/projects/[^"]+/boq/[^"]+)"', w).group(1)
    d = c.get(boq).text
    assert 'QUICK ESTIMATE from built-up area only' in d and 'Ready-mix concrete' in d
    assert c.get(boq + '/excel').content[:2] == b'PK'
    # project-level quick estimate (from the Smart Estimate page)
    sp = c.get(P + '/smart').text
    assert 'Only know the area?' in sp and P + '/quick' in sp
    r = c.post(P + '/quick', data={'confirm': '1', 'csrf_token': tok(sp), 'floors': '1'}, follow_redirects=False)
    assert r.status_code == 303
    # another user cannot run it on this project
    o = TestClient(app)
    o.post('/register', data={'name': 'Other', 'username': 'other_quick', 'password': 'other-password-1', 'remember': '',
                              'csrf_token': tok(o.get('/register').text)})
    assert o.post(P + '/quick', data={'confirm': '1', 'csrf_token': tok(o.get('/rates').text)}).status_code == 404
    assert 'Ran Quick Estimate' in c.get(P + '/team').text
    con = sqlite3.connect('data/buildquant.db')
    assert '2.8.0' in {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    print('QUICK SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab')
           if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'Quick Estimate smoke test skipped; missing: ' + ', '.join(MISSING))
class QuickSmokeTest(unittest.TestCase):
    def test_quick_estimate_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            (tmp / '_quick_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_quick_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('QUICK SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
