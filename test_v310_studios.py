"""v3.1.0 tests: Cost Intelligence Center, Structural Studio, BBS Studio, return-to middleware.

The app smoke test runs on a THROW-AWAY COPY in a temp folder; the real database is never used.
"""
import importlib.util, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

import studio_v310 as s31

HERE = Path(__file__).resolve().parent


class HelperTests(unittest.TestCase):
    def test_stage_of(self):
        self.assertEqual(s31.stage_of('Excavation for footings – preliminary'), 'foundation')
        self.assertEqual(s31.stage_of('RCC footings – preliminary'), 'foundation')
        self.assertEqual(s31.stage_of('RCC columns – preliminary'), 'frame')
        self.assertEqual(s31.stage_of('RCC slab (rmc)'), 'frame')
        self.assertEqual(s31.stage_of('External masonry – indicative (net openings, centreline)'), 'walls')
        self.assertEqual(s31.stage_of('Ceiling plaster'), 'finishes')
        self.assertEqual(s31.stage_of('Floor tiles × 2 floors'), 'finishes')
        self.assertEqual(s31.stage_of('Roof waterproofing (top roof only)'), 'roof')

    def test_source_labels(self):
        self.assertEqual(s31.source_of('RCC columns – preliminary', {})[0], 'Typical size')
        self.assertEqual(s31.source_of('Internal masonry – provisional (net doors)', {})[0], 'Provisional')
        self.assertEqual(s31.source_of('Floor tiles', {'source_detail': 'quick_v280'})[0], 'Area only')
        self.assertEqual(s31.source_of('Floor tiles', {})[0], 'Measured')

    def test_analysis(self):
        payload = {'rows': [
            {'work': 'RCC slab (rmc)', 'items': [{'material': 'Ready-mix concrete (RMC)', 'quantity': 10, 'unit': 'm³', 'rate': 5000},
                                                 {'material': 'Steel planning allowance (not BBS)', 'quantity': 900, 'unit': 'kg', 'rate': 0}]},
            {'work': 'External masonry – indicative', 'items': [{'material': 'Bricks', 'quantity': 1000, 'unit': 'nos', 'rate': 8}]}]}
        a = s31.boq_analysis(payload)
        self.assertEqual(a['stages']['frame'], 50000)
        self.assertEqual(a['stages']['walls'], 8000)
        self.assertEqual(a['material'], 58000)
        self.assertEqual(a['unpriced'], 1)
        self.assertEqual(a['top'][0], ('Ready-mix concrete (RMC)', 50000))

    def test_safe_return(self):
        post = '/projects/abc/structural/advanced/add'
        self.assertEqual(s31._safe_return('/projects/abc/structure', post), '/projects/abc/structure')
        self.assertEqual(s31._safe_return('/projects/abc/boq?rev=1#lines', post), '/projects/abc/boq?rev=1#lines')
        for bad in ('/projects/other/structure', 'https://evil.example/x', '//evil.example', '/rates', ''):
            self.assertEqual(s31._safe_return(bad, post), '', bad)
        self.assertEqual(s31._safe_return('/projects/abc/x', '/rates'), '')

    def test_bars_for_and_sketch(self):
        bars = [{'mark': 'C1-MAIN'}, {'mark': 'c1'}, {'mark': 'C10-MAIN'}, {'mark': 'B1'}]
        self.assertEqual([b['mark'] for b in s31.bars_for('C1', bars)], ['C1-MAIN', 'c1'])
        svg = s31.bar_svg({'length': 3.5, 'hook': 0.1, 'bend': 0})
        self.assertIn('role="img"', svg)
        self.assertIn('with hooks', svg)
        self.assertNotIn('with bends', svg)


SMOKE = textwrap.dedent(r'''
    import re, sqlite3, html as H
    from collections import Counter
    from fastapi.testclient import TestClient
    from app import app

    keys = [(m, r.path) for r in app.routes for m in (getattr(r, 'methods', None) or ())]
    assert not [k for k, n in Counter(keys).items() if n > 1], 'duplicate routes'
    def tok(h):
        return re.search(r'name="csrf_token" value="([^"]+)"', h).group(1)
    def action(h, contains):
        for a in re.findall(r'<form method="post" action="([^"]+)"', h):
            a = H.unescape(a)
            if contains in a:
                return a
        raise AssertionError('no form posting to ' + contains)
    def user(name):
        c = TestClient(app)
        c.post('/register', data={'name': name.title(), 'username': name, 'password': 'studio-password-1', 'remember': '',
                                  'csrf_token': tok(c.get('/register').text)})
        return c

    c = user('studio_owner')
    c.post('/rates', data={'csrf_token': tok(c.get('/rates').text), 'cement_bag': '420', 'rmc': '5600', 'brick': '9', 'labour_sqft': '450', 'tax_percent': '18'})
    r = c.post('/projects/new', data={'csrf_token': tok(c.get('/projects/new').text), 'name': 'Studio House', 'type': 'Residential',
                                      'location': 'Trichy', 'area': '1200', 'floors': '1', 'next': 'quick'}, follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    P = r.headers['location'].split('/workflow')[0]

    # ---- Cost Intelligence Center
    b = c.get(P + '/boq').text
    for text in ('Cost &amp; BOQ', 'Grand total', 'Work items by stage', 'Foundation', 'Frame &amp; slab', 'Walls', 'Finishes',
                 'Material cost by stage', 'Biggest material costs', 'Revisions', 'Rev 1', 'name="rate_0_0"', 'Typical size'):
        assert text in b, text
    assert 'have no rate' not in b                                     # v3.8: every line priced from the market rates
    rates_url = action(b, '/rates?return=')
    assert '/boq/' in rates_url and 'return=%2Fprojects%2F' in rates_url
    form = {k: v for k, v in re.findall(r'name="(rate_\d+_\d+)"[^>]*value="([^"]+)"', b)}
    form['rate_0_0'] = '999'
    r = c.post(rates_url, data={'csrf_token': tok(b), **form}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].startswith(P + '/boq?rev='), r.headers.get('location')
    assert 'value="999.00"' in c.get(P + '/boq').text
    costs_url = action(b, '/costs?return=')
    r = c.post(costs_url, data={'csrf_token': tok(b), 'labour': '100000', 'transport': '5000', 'other': '0', 'tax_percent': '18'}, follow_redirects=False)
    assert r.status_code == 303 and '/boq?rev=' in r.headers['location']
    assert 'value="100000"' in c.get(P + '/boq').text

    # ---- Structural Studio
    s = c.get(P + '/structure').text
    assert 'Structural Studio' in s and 'Measured quantity ≠ validated design' in s and 'Add element' in s
    add_url = action(s, '/structural/advanced/add')
    r = c.post(add_url, data={'confirm': '1', 'csrf_token': tok(s), 'kind': 'column', 'reference': 'C1', 'count': '4', 'length': '0.23', 'width': '0.3',
                              'depth': '3.15', 'deduction': '0', 'waste': '5', 'formwork': '0'}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == P + '/structure', r.headers.get('location')
    r = c.post(add_url, data={'confirm': '1', 'csrf_token': tok(s), 'kind': 'slab', 'reference': 'S1', 'count': '1', 'length': '10', 'width': '10',
                              'depth': '0.125', 'deduction': '0', 'waste': '5', 'formwork': '0'}, follow_redirects=False)
    assert r.status_code == 303
    s = c.get(P + '/structure').text
    el = re.search(r'/structure\?el=([0-9a-f-]{36})"><b>C1', s).group(1)
    assert 'Columns &amp; walls' in s and 'Stairs, tanks &amp; others' in s
    # alert: RCC slab in both the BOQ and the Structural Studio
    assert 'Possible double counting' in c.get(P + '/boq').text

    # ---- BBS Studio
    bb = c.get(P + '/bbs').text
    assert 'Bar Bending Schedule' in bb and 'No bars yet' in bb
    r = c.post(action(bb, '/bbs/add'), data={'confirm': '1', 'csrf_token': tok(bb), 'reference': 'C1-MAIN', 'diameter': '12', 'count': '16', 'length': '3.5',
                                             'bend': '0', 'hook': '0.1', 'lap': '0.6', 'waste': '3'}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == P + '/bbs'
    bb = c.get(P + '/bbs').text
    assert 'Order list by diameter' in bb and '12 mm' in bb and 'Manual entry' in bb
    bar = re.search(r'/bbs\?bar=([0-9a-f-]{36})', bb).group(1)
    det = c.get(P + '/bbs?bar=' + bar).text
    assert 'Cut length = straight + hook + lap − bend deductions' in det and '4.200 m' in det and 'role="img"' in det
    # 16 bars x 4.2 m x 12²/162 = 59.733 kg
    assert '59.73 kg' in det, 'bar weight'
    # element page links the steel and shows the calculation trace
    e = c.get(P + '/structure?el=' + el).text
    assert 'Gross = count × length × width × depth = 4 × 0.23 × 0.3 × 3.15' in e and 'C1-MAIN' in e and ('kg of steel per m³' in e or 'outside the usual' in e)
    # return to ANOTHER project is ignored (falls back to the route's own redirect)
    other = c.post('/projects/new', data={'csrf_token': tok(c.get('/projects/new').text), 'name': 'Other', 'type': 'Residential',
                                          'location': 'X', 'area': '500'}, follow_redirects=False).headers['location']
    r = c.post(P + '/structural/advanced/add?return=' + other.replace('/', '%2F') + '%2Fstructure', data={'confirm': '1', 'csrf_token': tok(s), 'kind': 'lintel',
               'reference': 'L1', 'count': '1', 'length': '1.2', 'width': '0.23', 'depth': '0.15'}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].endswith('/structural/advanced'), r.headers.get('location')
    # delete a bar from the side panel
    r = c.post(action(det, '/delete?return='), data={'csrf_token': tok(det)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == P + '/bbs'

    # ---- viewer: sees everything, cannot change anything
    v = user('studio_viewer')
    tm = c.get(P + '/team').text
    c.post(P + '/team/add', data={'csrf_token': tok(tm), 'username': 'studio_viewer', 'role': 'customer'})
    vb = v.get(P + '/boq').text
    assert 'Grand total' in vb and 'name="rate_0_0"' not in vb and 'Save charges' not in vb
    vs = v.get(P + '/structure').text
    assert 'Add element' not in vs
    assert v.post(add_url, data={'csrf_token': tok(vs), 'kind': 'slab', 'reference': 'X', 'count': '1', 'length': '1', 'width': '1', 'depth': '0.1'}).status_code == 403
    assert user('studio_outsider').get(P + '/boq').status_code == 404

    # context bar tabs
    assert 'class="cv-cb-tab on" href="' + P + '/structure"' in c.get(P + '/bbs').text     # v3.8: BBS is inside Structure
    assert 'class="cv-cb-tab on" href="' + P + '/structure"' in c.get(P + '/structure').text
    con = sqlite3.connect('data/buildquant.db')
    assert '3.1.0' in {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    print('V310 SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab') if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'v3.1 smoke test skipped; missing: ' + ', '.join(MISSING))
class StudioSmokeTest(unittest.TestCase):
    def test_studios_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            (tmp / '_v310_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_v310_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('V310 SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
