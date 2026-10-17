"""v2.4 end-to-end smoke test of the whole application.

Runs against a THROW-AWAY COPY of the source in a temp folder, so the real
data/buildquant.db and uploads are never touched.
Needs: fastapi, httpx, ezdxf, PyMuPDF, opencv (all in requirements.txt).
"""
import importlib.util, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEEDED = ('fastapi', 'httpx', 'ezdxf', 'fitz', 'cv2', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab')
MISSING = [m for m in NEEDED if importlib.util.find_spec(m) is None]

SMOKE = textwrap.dedent(r'''
    import re, sys
    from collections import Counter
    from pathlib import Path
    from fastapi.testclient import TestClient
    from app import app

    # 1. Every (method, path) must be registered exactly once.
    keys = [(m, r.path) for r in app.routes for m in (getattr(r, 'methods', None) or ())]
    dup = sorted(k for k, n in Counter(keys).items() if n > 1)
    assert not dup, 'Duplicate routes: %s' % dup

    c = TestClient(app)
    def tok(html):
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        assert m, 'No CSRF token on page'
        return m.group(1)
    def ok(url, code=200):
        r = c.get(url)
        assert r.status_code == code, '%s -> HTTP %s: %s' % (url, r.status_code, r.text[:300])
        return r

    # 2. Account + project
    r = c.post('/register', data={'name': 'Smoke Test', 'username': 'smoke_tester', 'password': 'smoke-password-1',
                                   'remember': '', 'csrf_token': tok(ok('/register').text)}, follow_redirects=False)
    assert r.status_code == 303, 'register %s' % r.status_code
    r = c.post('/projects/new', data={'name': 'Smoke Project', 'type': 'Residential', 'location': 'Chennai',
                                       'area': '1162', 'csrf_token': tok(ok('/projects/new').text)}, follow_redirects=False)
    assert r.status_code == 303, 'project %s' % r.status_code
    pid = r.headers['location'].rstrip('/').rsplit('/', 1)[1]
    P = '/projects/' + pid

    # 3. Upload the sample DXF
    dxf = Path('sample_drawings/Civora_Complete_Test_Plan.dxf').read_bytes()
    r = c.post(P + '/upload', data={'csrf_token': tok(ok(P).text)},
               files={'file': ('Civora_Complete_Test_Plan.dxf', dxf, 'application/dxf')}, follow_redirects=False)
    assert r.status_code == 303, 'upload %s %s' % (r.status_code, r.text[:200])
    fid = r.headers['location'].rstrip('/').rsplit('/', 1)[1]
    D = P + '/drawings/' + fid

    for url in (P + '/drawings', D, D + '/media', D + '/auto', D + '/adaptive', D + '/recognition',
                P + '/drawings/boq', P + '/materials', P + '/takeoff'):
        ok(url)

    # 4. Drawing Intelligence auto-calculation from the DXF schedule
    page = ok(D + '/intelligence').text
    r = c.post(D + '/intelligence', data={'csrf_token': tok(page), 'page': '0', 'rcc_mode': 'rmc',
                                          'measurement_basis': 'centreline'})
    assert r.status_code == 200, 'intelligence %s %s' % (r.status_code, r.text[:300])
    html = r.text
    assert 'RCC slab (rmc)' in html, 'RCC slab row missing'
    assert '16.200' in html, 'Slab volume 16.200 m3 missing'
    assert 'MAIN DOOR' in html and 'INTERNAL DOOR' in html, 'Opening labels not parsed'
    assert 'name="measurement_basis"' in page, 'Basis selector missing on Intelligence form'
    assert 'Measurement basis: <b>Centreline</b>' in html, 'Basis banner missing'
    assert '109.380' in html, 'Centreline masonry net face 109.380 m2 missing'
    assert '112.140' in html, 'External plaster face 112.140 m2 missing'
    assert '29.310' in html, 'Centreline 3x2 grid partition length 29.310 m missing'
    signed = re.search(r'name="signed_preview" value="([^"]+)"', html).group(1)

    # 5. Save draft BOQ, enter rates, cost extras, export
    r = c.post(D + '/boq/save', data={'csrf_token': tok(html), 'signed_preview': signed,
                                      'confirm_assumptions': 'yes'}, follow_redirects=False)
    assert r.status_code == 303, 'boq save %s %s' % (r.status_code, r.text[:200])
    B = r.headers['location']
    detail = ok(B).text
    rates = {name: '10' for name in re.findall(r'name="(rate_\d+_\d+)"', detail)}
    assert rates, 'No rate inputs on saved BOQ'
    r = c.post(B + '/rates', data={'csrf_token': tok(detail), **rates}, follow_redirects=False)
    assert r.status_code == 303, 'rates %s' % r.status_code
    r = c.post(B + '/costs', data={'csrf_token': tok(ok(B).text), 'labour': '1000', 'transport': '500',
                                   'other': '0', 'tax_percent': '18'}, follow_redirects=False)
    assert r.status_code == 303, 'costs %s' % r.status_code
    assert 'Measurement basis (masonry): <b>Centreline</b>' in ok(B).text, 'Basis not shown on saved BOQ'
    xl = ok(B + '/excel').content
    assert xl[:2] == b'PK', 'Excel export broken'
    import io as _io; from openpyxl import load_workbook as _lw
    assert _lw(_io.BytesIO(xl))['Material BOQ']['B4'].value == 'Centreline', 'Basis missing in Excel'
    assert ok(B + '/pdf').content[:4] == b'%PDF', 'PDF export broken'

    # 6. Structural modules v2.0 - v2.3
    page = ok(P + '/structural').text
    r = c.post(P + '/structural/add', data={'confirm': '1', 'csrf_token': tok(page), 'reference': 'S1', 'kind': 'slab', 'count': '1',
                                            'length': '12', 'width': '9', 'depth': '0.15', 'openings': '0', 'waste': '5'},
               follow_redirects=False)
    assert r.status_code == 303, 'v2.0 add %s' % r.status_code
    ok(P + '/structural/export.csv')
    page = ok(P + '/structural/advanced').text
    r = c.post(P + '/structural/advanced/add', data={'confirm': '1', 'csrf_token': tok(page), 'reference': 'S1', 'kind': 'slab',
               'count': '1', 'length': '12', 'width': '9', 'depth': '0.15', 'deduction': '0', 'waste': '5',
               'formwork': '108'}, follow_redirects=False)
    assert r.status_code == 303, 'v2.1 add %s' % r.status_code
    for ext, sig in (('xlsx', b'PK'), ('pdf', b'%PDF')):
        assert ok(P + '/structural/advanced/export.' + ext).content[:len(sig)] == sig, ext + ' export broken'
    ok(P + '/structural/advanced/export.csv')
    ok(P + '/structural/design')
    review = ok(P + '/structural/review').text
    assert 'RCC 16.200' in review, 'Review page did not reconcile the v2.1 slab'
    ok(P + '/structural/review/export.csv'); ok(P + '/structural/review/report.html')
    # 7. v2.4.2 data safety on the real app database
    import sqlite3, data_safety
    con = sqlite3.connect('data/buildquant.db')
    versions = {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    assert {'2.3.0', '2.4.0', '2.4.1', '2.4.2'} <= versions, 'Migration history incomplete: %s' % versions
    made = data_safety.backup_database(reason='manual')
    assert made and data_safety.integrity_check(made)[0] == 'ok', 'Backup of app database failed'
    print('SMOKE OK')
''')


@unittest.skipIf(MISSING, 'Full-app smoke test skipped; missing: ' + ', '.join(MISSING))
class AppSmokeTest(unittest.TestCase):
    def test_full_workflow_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            shutil.copytree(HERE / 'sample_drawings', tmp / 'sample_drawings')
            (tmp / '_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
