"""v3.2.0 tests: reinforcement detail drawings, site detail sheet, structural rates from Rate Master.

The app smoke test runs on a THROW-AWAY COPY in a temp folder; the real database is never used.
"""
import importlib.util, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

import detailing_v320 as rd

HERE = Path(__file__).resolve().parent


def el(kind, mark, n, L, W, D):
    return {'kind': kind, 'mark': mark, 'p': {'count': n, 'length_m': L, 'width_m': W, 'depth_m': D}}


def bar(mark, dia, cnt, lap=0, bend=0, hook=0):
    return {'mark': mark, 'p': {'diameter_mm': dia, 'count': cnt, 'length': 3, 'lap': lap, 'bend': bend, 'hook': hook}}


class RoleTests(unittest.TestCase):
    def test_roles(self):
        cases = {('C1-MAIN', 'C1'): 'main', ('C1', 'C1'): 'main', ('c1-ties', 'C1'): 'ties', ('B1-STIR', 'B1'): 'ties',
                 ('B1-TOP', 'B1'): 'top', ('B1-BOT', 'B1'): 'bottom', ('F1-X', 'F1'): 'x', ('F1-MESH', 'F1'): 'mesh',
                 ('S1-DIST', 'S1'): 'dist', ('C1-EXTRA', 'C1'): 'extra', ('C10-MAIN', 'C1'): None, ('B1-TOP', 'C1'): None}
        for (m, e), want in cases.items():
            self.assertEqual(rd.bar_role(m, e), want, (m, e))

    def test_per_element_counts(self):
        bars = [bar('C1-MAIN', 16, 54, lap=0.8), bar('C1-TIES', 8, 270), bar('C1-MAIN-2', 12, 9)]
        got = rd.linked_bars(el('column', 'C1', 9, .23, .38, 3.2), bars)
        self.assertEqual(got['main']['per'], 6)          # 54 bars over 9 columns
        self.assertEqual(got['ties']['per'], 30)
        self.assertEqual(got['main']['lap'], 0.8)        # first main mark wins, not overwritten

    def test_spacing(self):
        self.assertEqual(rd.spacing_mm(1.5, 5, 50), 350)  # (1500 - 100) / 4
        self.assertIsNone(rd.spacing_mm(1.5, 1, 50))
        self.assertIsNone(rd.spacing_mm(0, 5, 50))


class DrawingTests(unittest.TestCase):
    BARS = [bar('F1-MESH', 12, 90, bend=.2), bar('C1-MAIN', 16, 54, lap=.8), bar('C1-TIES', 8, 270),
            bar('B1-TOP', 12, 2), bar('B1-BOT', 16, 3, lap=.8), bar('B1-STIR', 8, 28), bar('S1-MAIN', 10, 30), bar('S1-DIST', 8, 24)]

    def check(self, e, must):
        svg, notes, linked = rd.detail(e, self.BARS)
        self.assertTrue(svg.startswith('<svg') and svg.endswith('</svg>'))
        self.assertIn('role="img"', svg)
        for m in must:
            self.assertIn(m, svg + ' '.join(notes), m)
        return svg, notes, linked

    def test_footing(self):
        self.check(el('isolated_footing', 'F1', 9, 1.5, 1.5, .4), ['PLAN', 'SECTION A', '5 nos 12 mm @ ≈350 c/c', 'L-bend up', 'column starter bars', 'cover'])

    def test_column(self):
        self.check(el('column', 'C1', 9, .23, .38, 3.2), ['6 nos 16 mm', 'LAP ZONE', 'lap 800 mm (entered)', 'middle half', 'closer ties', '135° hooks', 'never at the floor'])

    def test_beam(self):
        self.check(el('roof_beam', 'B1', 1, 4.2, .23, .45), ['LAP top bars here (mid-span)', 'LAP bottom bars here', 'closer stirrups', '2 nos 12 mm', '3 nos 16 mm', 'never at mid-span'])

    def test_slab(self):
        self.check(el('slab', 'S1', 1, 6, 4, .125), ['cranked', 'span/7', 'Main (short span): 30 nos 10 mm', 'SHORTER direction (4 m)'])

    def test_no_bars_typical_warning_and_not_detailable(self):
        block = rd.detail_block(el('column', 'C9', 1, .3, .3, 3), [])
        self.assertIn('No bars linked yet', block)
        self.assertIn('not a design', block)
        self.assertIsNone(rd.detail(el('excavation', 'EX1', 1, 1, 1, 1), []))
        self.assertEqual(rd.detail_block(el('pcc', 'P1', 1, 1, 1, .1), []), '')

    def test_labels_are_escaped(self):
        svg, *_ = rd.detail(el('column', '<C1>', 1, .3, .3, 3), [])
        self.assertNotIn('<C1>', svg)


SMOKE = textwrap.dedent(r'''
    import re, sqlite3, html as H
    from fastapi.testclient import TestClient
    from app import app

    def tok(h):
        return re.search(r'name="csrf_token" value="([^"]+)"', h).group(1)
    def action(h, contains):
        for a in re.findall(r'<form method="post" action="([^"]+)"', h):
            a = H.unescape(a)
            if contains in a:
                return a
        raise AssertionError('no form posting to ' + contains)
    c = TestClient(app)
    c.post('/register', data={'name': 'Detail Owner', 'username': 'detail_owner', 'password': 'detail-password-1', 'remember': '',
                              'csrf_token': tok(c.get('/register').text)})
    c.post('/rates', data={'csrf_token': tok(c.get('/rates').text), 'rmc': '5600', 'steel': '68', 'formwork': '450'})
    r = c.post('/projects/new', data={'csrf_token': tok(c.get('/projects/new').text), 'name': 'Detail House', 'type': 'Residential',
                                      'location': 'Trichy', 'area': '1000'}, follow_redirects=False)
    P = r.headers['location']
    assert 'No footings, columns, beams or slabs yet' in c.get(P + '/structure/details').text
    s = c.get(P + '/structure').text
    add = action(s, '/structural/advanced/add')
    for kind, ref, n, L, W, D in (('isolated_footing', 'F1', 9, 1.5, 1.5, .4), ('column', 'C1', 9, .23, .38, 3.2), ('roof_beam', 'B1', 1, 4.2, .23, .45),
                                  ('slab', 'S1', 1, 6, 4, .125), ('excavation', 'EX1', 9, 1.8, 1.8, 1.5)):
        assert c.post(add, data={'confirm': '1', 'csrf_token': tok(s), 'kind': kind, 'reference': ref, 'count': n, 'length': L, 'width': W, 'depth': D},
                      follow_redirects=False).status_code == 303
    bb = c.get(P + '/bbs').text
    badd = action(bb, '/bbs/add')
    for ref, d, n, lap in (('F1-MESH', 12, 90, 0), ('C1-MAIN', 16, 54, .8), ('C1-TIES', 8, 270, 0), ('B1-TOP', 12, 2, 0), ('B1-BOT', 16, 3, .8),
                           ('B1-STIR', 8, 28, 0), ('S1-MAIN', 10, 30, 0), ('S1-DIST', 8, 24, 0)):
        assert c.post(badd, data={'confirm': '1', 'csrf_token': tok(bb), 'reference': ref, 'diameter': d, 'count': n, 'length': 3, 'lap': lap},
                      follow_redirects=False).status_code == 303
    s = c.get(P + '/structure').text
    ids = dict((m, i) for i, m in re.findall(r'/structure\?el=([0-9a-f-]{36})"><b>([^<]+)<', s))
    col = c.get(P + '/structure?el=' + ids['C1']).text
    assert 'Reinforcement detail' in col and 'LAP ZONE' in col and '6 nos 16 mm' in col and 'class="rd-svg"' in col
    assert 'Reinforcement detail' not in c.get(P + '/structure?el=' + ids['EX1']).text     # excavation has no drawing
    sheet = c.get(P + '/structure/details').text
    assert sheet.count('class="rd-svg"') == 4 and 'Print / save PDF' in sheet
    # structural rates from Rate Master -> existing route, back to the studio
    assert 'Use my Rate Master rates' in s
    r = c.post(action(s, '/structural/advanced/rates'), data=dict(re.findall(r'<input type="hidden" name="([a-z_]+_rate|csrf_token)" value="([^"]+)"', s)),
               follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == P + '/structure', r.headers.get('location')
    con = sqlite3.connect('data/buildquant.db')
    rate = con.execute('SELECT concrete_rate, steel_rate, formwork_rate FROM civora_rates_v210 WHERE project_id=?', (P.rsplit('/', 1)[1],)).fetchone()
    assert rate == (5600, 68, 450), rate
    assert 'Structural rates match your Rate Master' in c.get(P + '/structure').text
    assert 'not priced' not in c.get(P + '/boq').text.split('Structural Studio quantities')[1].split('</section>')[0]
    # viewer can open the sheet, outsider cannot
    o = TestClient(app)
    o.post('/register', data={'name': 'Out', 'username': 'detail_out', 'password': 'detail-password-1', 'remember': '', 'csrf_token': tok(o.get('/register').text)})
    assert o.get(P + '/structure/details').status_code == 404
    assert '3.2.0' in {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    print('V320 SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab') if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'v3.2 smoke test skipped; missing: ' + ', '.join(MISSING))
class DetailingSmokeTest(unittest.TestCase):
    def test_details_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            (tmp / '_v320_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_v320_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('V320 SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
