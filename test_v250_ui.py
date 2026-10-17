"""v2.5.0 tests: new interface shell, dashboard, project workflow page and Download All.

Unit tests use an in-memory database. The app smoke test runs on a THROW-AWAY COPY in a
temp folder, so the real data/buildquant.db and uploads are never touched.
"""
import importlib.util, io, json, shutil, sqlite3, subprocess, sys, tempfile, textwrap, time, unittest, zipfile
from pathlib import Path

import ui_shell
import workflow_v250 as wf

HERE = Path(__file__).resolve().parent


def _db():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE projects(id TEXT PRIMARY KEY,owner_id TEXT,name TEXT,type TEXT,location TEXT,area REAL,created INTEGER);
    CREATE TABLE uploads(id TEXT PRIMARY KEY,project_id TEXT,original_name TEXT,stored_name TEXT,content_type TEXT,created INTEGER);
    CREATE TABLE material_takeoffs(id TEXT PRIMARY KEY,project_id TEXT,work_key TEXT,input_json TEXT,result_json TEXT,created INTEGER);
    CREATE TABLE civora_boq_reports(id TEXT PRIMARY KEY,project_id TEXT,drawing_id TEXT,payload TEXT,created INTEGER);
    CREATE TABLE civora_structural_v210(id TEXT PRIMARY KEY,project_id TEXT,kind TEXT,reference TEXT,drawing_ref TEXT,payload TEXT,created INTEGER);
    CREATE TABLE civora_bbs_v210(id TEXT PRIMARY KEY,project_id TEXT,reference TEXT,payload TEXT,created INTEGER);
    CREATE TABLE civora_rates_v210(project_id TEXT PRIMARY KEY,concrete_rate REAL,steel_rate REAL,formwork_rate REAL,excavation_rate REAL,backfill_rate REAL,pcc_rate REAL,updated INTEGER);
    ''')
    c.execute("INSERT INTO projects VALUES('p1','u1','Villa <One>','Residential','Chennai',1162,?)", (int(time.time()),))
    return c


def _project(c):
    return c.execute("SELECT * FROM projects WHERE id='p1'").fetchone()


BOQ = {'drawing_name': 'plan.dxf', 'measurement_basis': 'centreline', 'measurement_basis_label': 'Centreline',
       'rows': [{'work': 'RCC slab', 'area': 108, 'items': [
           {'material': 'Cement', 'quantity': 100, 'unit': 'bag', 'rate': 400},
           {'material': 'Steel', 'quantity': 1000, 'unit': 'kg', 'rate': 0}]}],
       'cost_extras': {'labour': 10000, 'transport': 2000, 'other': 0, 'tax_percent': 18}}


def _structural(c, ref, kind, net, order, form):
    c.execute('INSERT INTO civora_structural_v210 VALUES(?,?,?,?,?,?,?)',
              (ref + kind, 'p1', kind, ref, '', json.dumps({'result': {'net_m3': net, 'order_m3': order, 'formwork_m2': form}}), 1))


class ShellTests(unittest.TestCase):
    def test_inr_short(self):
        self.assertEqual(ui_shell.inr_short(999), '₹ 999')
        self.assertEqual(ui_shell.inr_short(425000), '₹ 4.25 L')
        self.assertEqual(ui_shell.inr_short(12000000), '₹ 1.20 Cr')

    def test_stepper_states(self):
        h = ui_shell.stepper({'setup', 'input'})
        self.assertEqual(h.count('cv-step done'), 2)
        self.assertEqual(h.count('cv-step now'), 1)          # next step highlighted
        self.assertEqual(h.count('cv-step todo'), 3)
        for _, _, title, *_ in ui_shell.STEPS:
            self.assertIn(title.replace('&', '&amp;'), h)

    def test_page_escapes_and_marks_active(self):
        user = {'name': '<script>x</script>', 'username': 'nish'}
        h = ui_shell.page('T<1>', '<p>body</p>', user=user, pid='abc', path='/projects', csrf_token='tok"1')
        self.assertNotIn('<script>x</script>', h)
        self.assertIn('T&lt;1&gt; | Civora AI', h)
        self.assertIn('value="tok&quot;1"', h)
        self.assertIn('class="cv-nl on" href="/projects"', h)
        self.assertIn('href="/estimate"', h)
        self.assertIn('Civora <i>AI</i>', h)

    def test_guest_page_has_no_logout(self):
        h = ui_shell.page('Home', 'x', user=None, path='/')
        self.assertNotIn('action="/logout"', h)
        self.assertIn('href="/register"', h)

    def test_auth_page_wrapper(self):
        self.assertIn('loginwrap', ui_shell.page('Login', 'form', auth_page=True))

    def test_home_guest_and_user(self):
        g = ui_shell.home_html(None)
        self.assertIn('Enter the area. Get the full estimate.', g)
        self.assertIn('Sign in to see your projects', g)
        u = ui_shell.home_html({'name': 'Nishanth S'}, [{'id': 'p1', 'name': 'Villa', 'type': 'Residential',
                                                         'location': 'Chennai', 'done': {'setup'}}],
                               {'id': 'p1', 'name': 'Villa', 'done': {'setup'}}, '', 3)
        self.assertIn('Welcome back, Nishanth', u)
        self.assertIn('/projects/p1/workflow', u)
        self.assertIn('/projects/p1/smart', u)                 # main action goes to Smart Estimate
        self.assertEqual(u.count('class="cv-qa'), 4)          # v2.6: 4 shortcuts only
        self.assertIn(f'3 of {len(__import__("rates_v260").RATE_KEYS)} rates set', u)
        nop = ui_shell.home_html({'name': 'N'}, [], None)
        self.assertIn('/projects/new?next=smart', nop)

    def test_menu_is_short_with_advanced_group(self):
        h = ui_shell.nav_html({'name': 'N'}, 'p1', '/projects/p1/takeoff')
        self.assertEqual(h.count('class="cv-nl'), 6)           # v3.8: six sections only
        self.assertIn('class="cv-nl on" href="/estimate"', h)  # takeoff lives in Estimate
        self.assertNotIn('Coming soon', h)


class WorkflowTests(unittest.TestCase):
    def test_empty_project(self):
        c = _db()
        st = wf.project_status(c, 'p1')
        self.assertEqual(st['done'], {'setup'})
        h = wf.workflow_cards(_project(c), st)
        self.assertEqual(h.count('class="cv-card cv-fc"'), 6)
        self.assertIn('DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED', h)
        self.assertIn('Villa &lt;One&gt;', wf.workflow_page_html(_project(c), st))
        self.assertNotIn('Download All (ZIP)', h)

    def test_missing_tables_are_tolerated(self):
        c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
        c.execute('CREATE TABLE uploads(id TEXT,project_id TEXT,original_name TEXT,created INTEGER)')
        self.assertEqual(wf.project_status(c, 'p1')['done'], {'setup'})

    def test_full_project_stages_and_cost(self):
        c = _db()
        c.execute("INSERT INTO uploads VALUES('f1','p1','plan.png','x','image/png',1)")
        c.execute("INSERT INTO civora_boq_reports VALUES('b1','p1','f1',?,2)", (json.dumps(BOQ),))
        _structural(c, 'F1', 'slab', 34.5, 36.0, 10)
        _structural(c, 'F1', 'raft', 2.5, 2.6, 4)
        c.execute('INSERT INTO civora_bbs_v210 VALUES(?,?,?,?,?)', ('bb', 'p1', 'F1', json.dumps({'result': {'steel_kg': 150.5}}), 1))
        c.execute("INSERT INTO civora_rates_v210 VALUES('p1',5000,70,0,0,0,0,1)")
        st = wf.project_status(c, 'p1')
        self.assertEqual(st['done'], set(ui_shell.STEP_KEYS))
        self.assertAlmostEqual(st['structural_totals']['rcc_m3'], 37.0)
        self.assertAlmostEqual(st['structural_totals']['steel_kg'], 150.5)
        seg = dict((n, v) for n, v, _ in st['cost']['segments'])
        self.assertAlmostEqual(seg['Materials & services'], 40000)
        self.assertAlmostEqual(seg['Structural works'], 38.6 * 5000 + 150.5 * 70)
        self.assertAlmostEqual(seg['Tax (18%)'], (40000 + 10000 + 2000) * 0.18)
        self.assertEqual(st['cost']['unrated'], 1)
        self.assertTrue(st['duplicate_marks'] and st['duplicate_marks'][0].startswith('F1'))
        h = wf.workflow_cards(_project(c), st)
        self.assertIn('conic-gradient', h)
        self.assertIn('Same mark used for different elements', h)
        self.assertIn('basis: Centreline', h)
        self.assertIn('/projects/p1/drawings/f1/boq/b1/excel', h)
        self.assertIn('Download All (ZIP)', h)
        self.assertIn('counted in both', h)

    def test_takeoff_materials_when_no_boq(self):
        c = _db()
        res = {'work': 'Brickwork', 'items': [{'material': 'Bricks', 'quantity': 5000, 'unit': 'nos'},
                                              {'material': 'Cement', 'quantity': 20, 'unit': 'bag'}]}
        c.execute("INSERT INTO material_takeoffs VALUES('t1','p1','brick','{}',?,1)", (json.dumps(res),))
        c.execute("INSERT INTO material_takeoffs VALUES('t2','p1','brick','{}',?,2)", (json.dumps(res),))
        rows, n, src = wf.material_summary(wf.project_status(c, 'p1'))
        self.assertEqual(dict((m, q) for m, q, _ in rows), {'Bricks': 10000, 'Cement': 40})
        self.assertIn('2 saved material takeoff', src)

    def test_zip_pack(self):
        c = _db()
        c.execute("INSERT INTO civora_boq_reports VALUES('b1','p1','f1',?,2)", (json.dumps(BOQ),))
        _structural(c, 'S1', 'slab', 16.2, 17.0, 108)
        st = wf.project_status(c, 'p1')
        z = zipfile.ZipFile(io.BytesIO(wf.build_zip(_project(c), st, st['structural_items'])))
        names = z.namelist()
        self.assertTrue(any(n.endswith('_Summary.txt') for n in names))
        self.assertTrue(any(n.endswith('_Material_BOQ.xlsx') for n in names))
        self.assertTrue(any(n.endswith('_Material_BOQ.pdf') for n in names))
        self.assertTrue(any(n.endswith('_Structural_Quantities.csv') for n in names))
        summary = z.read([n for n in names if n.endswith('_Summary.txt')][0]).decode()
        self.assertIn('ENGINEER REVIEW REQUIRED', summary)
        self.assertTrue(all('<' not in n and '>' not in n for n in names))


SMOKE = textwrap.dedent(r'''
    import io, json, re, sqlite3, time, zipfile
    from collections import Counter
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

    home = ok('/').text
    assert 'cv-side' in home and 'How big is your building?' in home
    login = ok('/login').text
    assert 'loginwrap' in login, 'Login page lost the welcome panel'
    r = c.post('/register', data={'name': 'Nishanth S', 'username': 'ui_tester', 'password': 'ui-password-123',
                                   'remember': '', 'csrf_token': tok(ok('/register').text)}, follow_redirects=False)
    assert r.status_code == 303
    newp = ok('/projects/new?type=Commercial&q=Mall').text
    assert 'value="Commercial" checked' in newp and 'value="Mall"' in newp
    r = c.post('/projects/new', data={'name': 'UI Villa', 'type': 'Residential', 'location': 'Madurai', 'area': '1500',
                                       'csrf_token': tok(newp)}, follow_redirects=False)
    pid = r.headers['location'].rstrip('/').rsplit('/', 1)[1]
    P = '/projects/' + pid
    detail = ok(P).text
    assert P + '/workflow' in detail and 'id="upload"' in detail

    # empty workflow
    w = ok(P + '/workflow').text
    assert w.count('class="cv-card cv-fc"') == 6 and 'DESIGN INCOMPLETE' in w and '1 of 6 steps done' in w

    # structural data through the real routes
    page = ok(P + '/structural/advanced').text
    for ref, kind in (('F1', 'slab'), ('F1', 'raft')):
        r = c.post(P + '/structural/advanced/add', data={'confirm': '1', 'csrf_token': tok(page), 'reference': ref, 'kind': kind,
                   'count': '1', 'length': '12', 'width': '9', 'depth': '0.15', 'deduction': '0', 'waste': '5',
                   'formwork': '108'}, follow_redirects=False)
        assert r.status_code == 303, 'structural add %s %s' % (r.status_code, r.text[:200])

    # a saved BOQ (inserted directly into this TEMP copy's database)
    payload = {'drawing_name': 'plan.png', 'measurement_basis': 'external', 'measurement_basis_label': 'External face',
               'rows': [{'work': 'Brickwork', 'area': 50, 'items': [{'material': 'Cement', 'quantity': 40, 'unit': 'bag', 'rate': 420}]}],
               'breakdown': [], 'notes': [], 'skipped': [], 'cost_extras': {'labour': 15000, 'transport': 0, 'other': 0, 'tax_percent': 18}}
    con = sqlite3.connect('data/buildquant.db')
    con.execute("INSERT INTO uploads VALUES('f-ui',?,'plan.png','none.png','image/png',?)", (pid, int(time.time())))
    con.execute('INSERT INTO civora_boq_reports VALUES(?,?,?,?,?)', ('b-ui', pid, 'f-ui', json.dumps(payload), int(time.time())))
    con.commit(); con.close()

    w = ok(P + '/workflow').text
    assert 'conic-gradient' in w, 'Cost donut missing'
    assert 'Same mark used for different elements' in w, 'Duplicate mark warning missing'
    assert 'Download All (ZIP)' in w
    zr = ok(P + '/workflow/download-all')
    assert zr.headers['content-type'].startswith('application/zip')
    names = zipfile.ZipFile(io.BytesIO(zr.content)).namelist()
    assert any(n.endswith('_Material_BOQ.xlsx') for n in names) and any(n.endswith('_Structural_Quantities.csv') for n in names), names

    home = ok('/').text
    assert 'UI Villa' in home and ', Nishanth' in home and 'href="/estimate"' in home     # v3.8: six-section menu
    s = ok('/projects?q=madurai').text
    assert 'UI Villa' in s
    assert 'No projects match' in ok('/projects?q=zzzz').text

    # every older module page still renders inside the new shell
    for url in (P + '/takeoff', P + '/materials', P + '/drawings', P + '/drawings/boq', P + '/structural',
                P + '/structural/advanced', P + '/structural/design', P + '/structural/review', '/guest'):
        assert 'cv-side' in ok(url).text, url

    # other users cannot see the workflow
    c2 = TestClient(app)
    r = c2.post('/register', data={'name': 'Other', 'username': 'other_user', 'password': 'other-password-1',
                                    'remember': '', 'csrf_token': re.search(r'name="csrf_token" value="([^"]+)"', c2.get('/register').text).group(1)},
                follow_redirects=False)
    assert c2.get(P + '/workflow').status_code == 404
    assert c2.get(P + '/workflow/download-all').status_code == 404

    con = sqlite3.connect('data/buildquant.db')
    assert '2.5.0' in {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    print('UI SMOKE OK')
''')

NEEDED = ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab')
MISSING = [m for m in NEEDED if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'UI smoke test skipped; missing: ' + ', '.join(MISSING))
class UISmokeTest(unittest.TestCase):
    def test_ui_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            (tmp / '_ui_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_ui_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('UI SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
