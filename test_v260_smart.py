"""v2.6.0 tests: Smart Estimate (drawing -> full estimate) and Rate Master.

Unit tests use synthetic drawing schedules; the app smoke test runs on a THROW-AWAY COPY
in a temp folder, so the real data/buildquant.db and uploads are never touched.
"""
import importlib.util, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

import rates_v260 as rv
import smart_estimate_v260 as se
from engineering import takeoff

HERE = Path(__file__).resolve().parent
HAVE_FASTAPI = importlib.util.find_spec('fastapi') is not None


def plan_schedule():
    """The sample 12 m x 9 m test plan as the drawing reader returns it."""
    ev = lambda v, s='drawing note': {'value': v, 'source': s}
    rooms = [{'name': n, 'length': 4.0, 'width': 4.5, 'area': 18.0} for n in
             ('BEDROOM 1', 'BEDROOM 2', 'KITCHEN', 'LIVING', 'DINING', 'BATHROOM')]
    return {'method': 'test', 'warnings': [], 'rooms': rooms,
            'evidence': {'overall_length': ev(12.0), 'overall_width': ev(9.0), 'floor_area': ev(108.0), 'slab_area': ev(108.0),
                         'external_thickness': ev(0.23), 'internal_thickness': ev(0.115), 'height': ev(3.0),
                         'slab_thickness': ev(0.15), 'external_plaster_thickness': ev(0.015), 'internal_plaster_thickness': ev(0.012),
                         'kitchen_tile_area_each': ev(0.09, 'KITCHEN WALL TILE 300 X 300 MM; HEIGHT 0.60 M'),
                         'bathroom_tile_area_each': ev(0.09, 'BATHROOM WALL TILE 300 X 300 MM; HEIGHT 2.10 M'),
                         'roof_waterproof_area': ev(108.0)},
            'openings': [{'label': 'DOOR D1', 'width': 1.2, 'height': 2.1, 'count': 1, 'area': 2.52, 'source': 'MAIN'},
                         {'label': 'DOOR D2', 'width': 0.9, 'height': 2.1, 'count': 5, 'area': 9.45, 'source': 'INTERNAL'},
                         {'label': 'WINDOW W1', 'width': 1.5, 'height': 1.2, 'count': 6, 'area': 10.8, 'source': ''},
                         {'label': 'VENTILATOR V1', 'width': 0.6, 'height': 0.45, 'count': 2, 'area': 0.54, 'source': ''}]}


def rows_by_label(result):
    return {label: items for label, _, items in result['rows']}


def qty(items, material):
    return sum(float(i['quantity']) for i in items if i['material'] == material)


class InputTests(unittest.TestCase):
    def test_reads_everything_the_drawing_has(self):
        inp = se.build_inputs(plan_schedule(), 1162)
        self.assertEqual(inp['length']['source'], 'drawing')
        self.assertEqual(inp['ext_open']['source'], 'derived')
        self.assertAlmostEqual(inp['ext_open']['value'], 2.52 + 10.8 + 0.54)
        self.assertAlmostEqual(inp['int_open']['value'], 9.45)
        self.assertEqual(inp['int_length']['source'], 'derived')        # regular 3x2 grid detected
        self.assertAlmostEqual(inp['int_length']['value'], 29.31)
        # kitchen 2(4+4.5)*0.6 = 10.2 ; bathroom 17*2.1 - door 1.89 = 33.81
        self.assertAlmostEqual(inp['wall_tile']['value'], 44.01)
        found, check = se.summary_counts(inp)
        self.assertEqual(check, 3)                                        # floors, plinth height, parapet height to confirm
        self.assertEqual(found, 13)
        self.assertTrue(all(inp[k]['source'] == 'typical' for k in ('columns', 'ftg_l', 'beam_d')))

    def test_missing_drawing_falls_back_to_typical_values(self):
        inp = se.build_inputs({}, 1076.39)                                # 100 m²
        self.assertAlmostEqual(inp['length']['value'], 10.0, places=2)
        self.assertEqual(inp['length']['source'], 'typical')
        self.assertEqual(inp['height']['value'], 3.0)
        self.assertEqual(inp['ext_thick']['value'], 0.23)
        self.assertGreater(inp['ext_open']['value'], 0)
        found, check = se.summary_counts(inp)
        self.assertEqual(found, 0)
        self.assertGreater(check, 8)

    def test_form_changes_become_user_values(self):
        base = se.build_inputs(plan_schedule(), 1162)
        inp = se.parse_form({'floors': '2', 'height': '3'}, base)
        self.assertEqual(inp['floors']['source'], 'user')
        self.assertEqual(inp['height']['source'], 'drawing')               # unchanged value keeps its source
        with self.assertRaises(ValueError):
            se.parse_form({'floors': '1.5'}, base)
        with self.assertRaises(ValueError):
            se.parse_form({'height': '40'}, base)
        with self.assertRaises(ValueError):
            se.parse_form({'length': 'abc'}, base)
        with self.assertRaises(ValueError):
            se.parse_options({'waste': '50'})


@unittest.skipUnless(HAVE_FASTAPI, 'needs fastapi (intelligent_recognition imports it)')
class EstimateTests(unittest.TestCase):
    def run_estimate(self, **changes):
        sch = plan_schedule()
        inp = se.parse_form(changes, se.build_inputs(sch, 1162))
        opts = se.parse_options(changes)
        return inp, opts, se.estimate(inp, opts, takeoff, sch)

    def test_single_floor_full_estimate(self):
        inp, opts, r = self.run_estimate()
        rows = rows_by_label(r)
        # centreline brickwork face (verified in v2.4.1): 109.38 m²; 230 mm wall
        masonry = next(v for k, v in rows.items() if k.startswith('External masonry'))
        # v3.7.0: net of lintels, beam drop (300-150 mm) and 12 wall columns -> 90.84 m² x 0.23 m x 500/m³ x 1.05
        self.assertAlmostEqual(qty(masonry, 'Bricks'), 10970, delta=2)
        for needed in ('Inner face plaster of external walls', 'Ceiling plaster', 'Wall tiles (kitchen / bathrooms)',
                       'Roof waterproofing (top roof only)', 'RCC footings – preliminary', 'RCC columns – preliminary',
                       'Excavation for footings – preliminary', 'Backfilling around footings – preliminary'):
            self.assertIn(needed, rows)
        slab = next(v for k, v in rows.items() if k.startswith('RCC slab'))
        self.assertAlmostEqual(qty(slab, 'Ready-mix concrete (RMC)'), 108 * 0.15 * 1.05, places=2)
        self.assertAlmostEqual(qty(slab, 'Steel planning allowance (not BBS)'), 108 * 0.15 * 90 * 1.05, places=1)
        self.assertEqual(r['frame']['columns'], 16)
        self.assertNotIn('Brick masonry (net of openings)', r['skipped'])
        self.assertAlmostEqual(r['builtup_sqft'], 108 * se.SQFT_PER_M2)

    def test_two_floors_double_walls_but_not_roof_or_footings(self):
        _, _, one = self.run_estimate()
        _, _, two = self.run_estimate(floors='2')
        r1, r2 = rows_by_label(one), rows_by_label(two)
        m1 = next(v for k, v in r1.items() if k.startswith('External masonry'))
        m2 = next(v for k, v in r2.items() if k.startswith('External masonry'))
        self.assertAlmostEqual(qty(m2, 'Bricks'), 2 * qty(m1, 'Bricks'))
        self.assertEqual(r1['Roof waterproofing (top roof only)'], r2['Roof waterproofing (top roof only)'])
        self.assertEqual(r1['RCC footings – preliminary'], r2['RCC footings – preliminary'])
        self.assertGreater(two['frame']['column'], one['frame']['column'])

    def test_frame_can_be_switched_off_and_is_validated(self):
        _, _, r = self.run_estimate(frame='no')
        self.assertFalse(any(k.startswith(('RCC footings', 'RCC columns', 'RCC plinth beam', 'RCC floor/roof beams')) for k in rows_by_label(r)))
        self.assertTrue(any(k.startswith('RCC lintels') for k in rows_by_label(r)))      # lintels are needed with or without a frame
        with self.assertRaises(ValueError):
            self.run_estimate(ftg_t='1.6', fdn_depth='1.5')

    def test_site_mix_steel_not_doubled(self):
        _, _, r = self.run_estimate(rcc_mode='site')
        cols = rows_by_label(r)['RCC columns – preliminary']
        self.assertEqual(sum(1 for i in cols if i['material'] == 'Steel planning allowance (not BBS)'), 1)

    def test_payload_lists_assumptions(self):
        sch = plan_schedule()
        inp = se.build_inputs(sch, 1162)
        opts = se.default_options()
        r = se.estimate(inp, opts, takeoff, sch)
        pl = se.build_payload({'id': 'p1'}, {'id': 'f1', 'original_name': 'plan.png'}, inp, opts, r, sch)
        self.assertIn('TYPICAL ASSUMPTIONS', pl['notes'][0])
        self.assertIn('Number of columns', pl['notes'][0])
        self.assertTrue(any('ENGINEER REVIEW REQUIRED' in n for n in pl['notes']))
        self.assertEqual(pl['source'], 'smart_estimate_v260')
        self.assertEqual(len(pl['inputs']), len(se.FIELDS))


class RateTests(unittest.TestCase):
    def test_matching(self):
        self.assertEqual(rv.rate_key_for({'material': 'Cement', 'unit': 'bags (50 kg)'}), 'cement_bag')
        self.assertIsNone(rv.rate_key_for({'material': 'Cement', 'unit': 'kg'}))      # site-mix kg line: not priced twice
        self.assertEqual(rv.rate_key_for({'material': 'Cement 50 kg bags', 'unit': 'bags (50 kg)'}), 'cement_bag')
        self.assertEqual(rv.rate_key_for({'material': 'Steel planning allowance (not BBS)', 'unit': 'kg'}), 'steel')
        self.assertIsNone(rv.rate_key_for({'material': 'M-sand', 'unit': 'kg'}))
        self.assertIsNone(rv.rate_key_for({'material': 'Mixing water', 'unit': 'litres'}))

    def test_validation(self):
        r = rv.validate_rates({'cement_bag': '420', 'steel': '', 'tax_percent': '18'})
        self.assertEqual(r['cement_bag'], 420)
        self.assertNotIn('steel', r)                                 # v3.8.0: blank = market rate
        self.assertEqual(rv.effective_rates(r)['steel'], rv.MARKET_RATES['steel'])
        for bad in ({'cement_bag': '-1'}, {'tax_percent': '150'}, {'brick': 'ten'}):
            with self.assertRaises(ValueError):
                rv.validate_rates(bad)

    def test_apply(self):
        payload = {'rows': [{'work': 'w', 'items': [
            {'material': 'Cement', 'quantity': 10, 'unit': 'bags (50 kg)', 'rate': 0},
            {'material': 'Cement', 'quantity': 500, 'unit': 'kg'},
            {'material': 'Bricks', 'quantity': 1000, 'unit': 'nos', 'rate': 8},
            {'material': 'Sand', 'quantity': 2, 'unit': 'm³'}]}]}
        priced, unpriced = rv.apply_rates(payload, {'cement_bag': 400, 'labour_sqft': 100, 'transport_pct': 5, 'tax_percent': 18}, 1000)
        items = payload['rows'][0]['items']
        self.assertEqual(items[0]['rate'], 400)
        self.assertNotIn('rate', items[1])
        self.assertEqual(items[2]['rate'], 8)                    # existing manual rate kept when master has none
        self.assertEqual((priced, unpriced), (2, 1))              # sand has no rate yet
        ex = payload['cost_extras']
        self.assertEqual(ex['labour'], 100000)
        self.assertEqual(ex['transport'], round((4000 + 8000) * 0.05, 2))
        self.assertEqual(ex['tax_percent'], 18)


SMOKE = textwrap.dedent(r'''
    import re, sqlite3
    from collections import Counter
    from pathlib import Path
    from fastapi.testclient import TestClient
    from app import app

    keys = [(m, r.path) for r in app.routes for m in (getattr(r, 'methods', None) or ())]
    dup = sorted(k for k, n in Counter(keys).items() if n > 1)
    assert not dup, 'Duplicate routes: %s' % dup
    c = TestClient(app)
    def tok(html):
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    def ok(url, code=200):
        r = c.get(url)
        assert r.status_code == code, '%s -> HTTP %s: %s' % (url, r.status_code, r.text[:300])
        return r

    r = c.post('/register', data={'name': 'Smart Tester', 'username': 'smart_tester', 'password': 'smart-password-1',
                                   'remember': '', 'csrf_token': tok(ok('/register').text)}, follow_redirects=False)
    assert r.status_code == 303
    # new project straight into Smart Estimate
    r = c.post('/projects/new', data={'name': 'Smart House', 'type': 'Residential', 'location': 'Trichy', 'area': '1162',
                                       'next': 'smart', 'csrf_token': tok(ok('/projects/new?next=smart').text)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].endswith('/smart'), r.headers.get('location')
    P = r.headers['location'][:-len('/smart')]
    start = ok(P + '/smart').text
    assert 'Upload your building plan' in start and P + '/smart/manual' in start

    # Rate Master
    rates = ok('/rates').text
    assert 'Rate Master' in rates and 'சிமெண்ட்' in rates
    r = c.post('/rates', data={'csrf_token': tok(rates), 'cement_bag': '420', 'steel': '68', 'brick': '9', 'sand': '4500',
                               'rmc': '5600', 'labour_sqft': '450', 'tax_percent': '18'}, follow_redirects=False)
    assert r.status_code == 303
    assert 'value="420"' in ok('/rates?saved=1').text
    bad = c.post('/rates', data={'csrf_token': tok(rates), 'tax_percent': '500'}).text
    assert 'percentage must be 100 or less' in bad

    # Smart Estimate without a drawing (manual sizes), 2 floors
    form = ok(P + '/smart/manual').text
    assert 'Check the measurements' in form and 'Please check' in form
    # v3.7.0: the first press only shows a preview; nothing is saved yet
    pv = c.post(P + '/smart/manual', data={'csrf_token': tok(form), 'length': '12', 'width': '9', 'floors': '2', 'height': '3',
                                          'frame': 'yes', 'frame_present': '1'})
    assert pv.status_code == 200 and 'PREVIEW' in pv.text and 'Save estimate' in pv.text, pv.text[:300]
    r = c.post(P + '/smart/manual', data={'confirm': '1', 'csrf_token': tok(form), 'length': '12', 'width': '9', 'floors': '2', 'height': '3',
                                         'frame': 'yes', 'frame_present': '1'}, follow_redirects=False)
    assert r.status_code == 303 and '/workflow?estimate=' in r.headers['location'], (r.status_code, r.text[:400])
    w = ok(r.headers['location']).text
    assert 'Estimate ready' in w and 'typical assumptions' in w
    assert 'conic-gradient' in w and 'per sq.ft' in w, 'Rates were not applied automatically'
    assert 'Preliminary frame from Smart Estimate' in w
    boq_url = re.search(r'href="(/projects/[^"]+/boq/[^"]+)"', w).group(1)
    detail = ok(boq_url).text
    assert 'Ready-mix concrete' in detail and 'value="420.00"' in detail
    xl = ok(boq_url + '/excel').content
    assert xl[:2] == b'PK'
    assert ok(boq_url + '/pdf').content[:4] == b'%PDF'
    assert ok(P + '/workflow/download-all').content[:2] == b'PK'
    # invalid value comes back as a friendly message
    err = c.post(P + '/smart/manual', data={'confirm': '1', 'csrf_token': tok(form), 'height': '45'}).text
    assert 'must be between' in err
    # apply rates again after a change
    r = c.post(P + '/rates/apply', data={'csrf_token': tok(w)}, follow_redirects=False)
    assert r.status_code == 303 and 'priced=1' in r.headers['location']

    # Smart Estimate with an uploaded drawing
    png = Path('sample_drawings/Civora_Complete_Test_Plan.png')
    if png.is_file():
        r = c.post(P + '/smart/upload', data={'csrf_token': tok(start)}, files={'file': ('plan.png', png.read_bytes(), 'image/png')},
                   follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
        review = ok(r.headers['location']).text
        assert 'Check the measurements' in review
    r = c.post(P + '/smart/upload', data={'csrf_token': tok(start)}, files={'file': ('notes.txt', b'hello', 'text/plain')})
    assert r.status_code == 400

    # the normal project upload still works after the store_upload refactor
    r = c.post(P + '/upload', data={'csrf_token': tok(ok(P).text)}, files={'file': ('boq.csv', b'a,b\n1,2\n', 'text/csv')}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].endswith(P), r.headers.get('location')
    assert c.post(P + '/upload', data={'csrf_token': tok(ok(P).text)}, files={'file': ('x.png', b'not a png', 'image/png')}).status_code == 400
    # simplified pages
    home = ok('/').text
    assert 'href="/estimate"' in home and 'Coming soon' not in home and home.count('class="cv-nl') == 6
    assert 'Start Smart Estimate' in ok(P).text

    # another user cannot touch this project
    c2 = TestClient(app)
    c2.post('/register', data={'name': 'Other', 'username': 'other_smart', 'password': 'other-password-1', 'remember': '',
                               'csrf_token': tok(c2.get('/register').text)}, follow_redirects=False)
    t2 = tok(c2.get('/rates').text)
    assert c2.get(P + '/smart').status_code == 404
    assert c2.post(P + '/rates/apply', data={'csrf_token': t2}).status_code == 404
    assert c2.post(P + '/smart/manual', data={'confirm': '1', 'csrf_token': t2}).status_code == 404

    con = sqlite3.connect('data/buildquant.db')
    assert '2.6.0' in {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    print('SMART SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab')
           if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'Smart Estimate smoke test skipped; missing: ' + ', '.join(MISSING))
class SmartSmokeTest(unittest.TestCase):
    def test_smart_estimate_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            if (HERE / 'sample_drawings').is_dir():
                shutil.copytree(HERE / 'sample_drawings', tmp / 'sample_drawings')
            (tmp / '_smart_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_smart_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('SMART SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
