"""v3.0.0 tests: redesigned shell, dashboard, portfolio, wizard, workspace, Drawing Studio, settings.

The app smoke test runs on a THROW-AWAY COPY in a temp folder; the real database is never used.
"""
import importlib.util, shutil, sqlite3, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

import settings_v300
import studio_v300
import ui_shell

HERE = Path(__file__).resolve().parent


def st(done=('setup',), boq=None, takeoffs=(), items=(), frame=None, signoff=None, total=0.0):
    return {'done': set(done), 'boq': boq, 'takeoffs': list(takeoffs), 'structural_items': list(items), 'boq_frame': frame or {},
            'signoff': signoff, 'cost': {'total': total}, 'uploads': []}


class StatusTests(unittest.TestCase):
    def test_status_flow(self):
        self.assertEqual(studio_v300.status_of(st()), 'draft')
        self.assertEqual(studio_v300.status_of(st(('setup', 'materials'), boq={'id': 'b'})), 'input')
        full = ('setup', 'input', 'materials', 'structure', 'cost', 'reports')
        self.assertEqual(studio_v300.status_of(st(full, boq={'id': 'b'}, frame={'columns': 9})), 'review')
        self.assertEqual(studio_v300.status_of(st(full, boq={'id': 'b'}, frame={'columns': 9}, signoff={'who': 'E'})), 'checked')
        self.assertEqual(studio_v300.status_of(st(full, boq={'id': 'b'})), 'progress')
        for key in studio_v300.STATUS:                      # every status has a text label, not colour alone
            self.assertIn(studio_v300.STATUS[key][0], studio_v300.status_chip(key))


class ShellTests(unittest.TestCase):
    def test_grouped_menu_and_tamil(self):
        en = ui_shell.nav_html({'name': 'N'}, 'p1', '/projects/p1/studio')
        self.assertEqual([l for _, l, _ in ui_shell.SECTIONS], ['Home', 'Projects', 'Estimate', 'Structure', 'Guide', 'More'])
        self.assertIn('class="cv-nl on" href="/estimate"', en)
        ta = ui_shell.nav_html({'name': 'N'}, 'p1', '/', 'ta')
        self.assertIn('திட்டங்கள்', ta)
        self.assertIn('மதிப்பீடு', ta)

    def test_context_bar(self):
        bar = ui_shell.context_bar({'id': 'p1', 'name': 'Villa <1>', 'type': 'Residential', 'location': 'Trichy', 'stage': 'cost',
                                    'revisions': 2, 'role': 'engineer', 'path': '/projects/p1/studio'})
        self.assertIn('Villa &lt;1&gt;', bar)
        self.assertIn('Next: Cost &amp; budget', bar)
        self.assertIn('Estimate rev 2', bar)
        self.assertIn('Engineer', bar)
        self.assertIn('class="cv-cb-tab on" href="/projects/p1/smart"', bar)      # Drawing Studio is inside Estimate
        self.assertEqual(ui_shell.context_bar(None), '')

    def test_mode_class_on_body(self):
        h = ui_shell.page('T', 'x', {'name': 'A', 'username': 'a'}, prefs={'mode': 'expert', 'lang': 'ta'})
        self.assertIn('cv-mode-expert cv-lang-ta', h)

    def test_prefs_defaults_and_storage(self):
        c = sqlite3.connect(':memory:')
        self.assertEqual(settings_v300.get_prefs(c, 'u1'), {'mode': 'guided', 'lang': 'en'})   # no table yet
        settings_v300.init(lambda: _Ctx(c))
        c.execute("INSERT INTO civora_user_prefs_v300 VALUES('u1','expert','ta',1)")
        self.assertEqual(settings_v300.get_prefs(c, 'u1'), {'mode': 'expert', 'lang': 'ta'})
        c.execute("INSERT INTO civora_user_prefs_v300 VALUES('u2','weird','xx',1)")
        self.assertEqual(settings_v300.get_prefs(c, 'u2'), {'mode': 'guided', 'lang': 'en'})


class ScreenTests(unittest.TestCase):
    def test_wizard_posts_the_same_fields(self):
        h = studio_v300.wizard_html('tok', 'Commercial', 'Mall', 'smart')
        for field in ('name="csrf_token"', 'name="name"', 'name="type"', 'name="location"', 'name="area"', 'name="floors"', 'name="next"'):
            self.assertIn(field, h)
        self.assertIn('value="Commercial" checked', h)
        self.assertIn('value="smart" checked', h)
        self.assertIn('action="/projects/new"', h)

    def test_portfolio_filters(self):
        def row(name, t, status):
            return {'p': {'id': name, 'name': name, 'type': t, 'location': 'X', 'area': 1000}, 'st': st(), 'role': 'owner',
                    'status': status, 'updated': 0}
        rows = [row('A', 'Residential', 'draft'), row('B', 'Commercial', 'review')]
        h = studio_v300.portfolio_html(rows, ftype='Commercial')
        self.assertIn('>B<', h)
        self.assertNotIn('>A<', h)
        self.assertIn('No projects match', studio_v300.portfolio_html(rows, fstatus='checked'))
        self.assertIn('pf-card', studio_v300.portfolio_html(rows, view='cards'))

    def test_guest_dashboard(self):
        h = studio_v300.dashboard_html(None, {}, 'tok')
        self.assertIn('How big is your building?', h)
        self.assertIn('action="/quick"', h)
        self.assertIn('Create free account', h)


class _Ctx:
    def __init__(self, c): self.c = c
    def __enter__(self): return self.c
    def __exit__(self, *a): self.c.commit()


SMOKE = textwrap.dedent(r'''
    import re, sqlite3
    from pathlib import Path
    from fastapi.testclient import TestClient
    from app import app

    def tok(html):
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    c = TestClient(app)
    c.post('/register', data={'name': 'Nishanth S', 'username': 'v3_user', 'password': 'v3-password-123', 'remember': '',
                              'csrf_token': tok(c.get('/register').text)})
    home = c.get('/').text
    for text in ('How big is your building?', 'Active projects', 'Needs engineer review', 'Recent activity', 'href="/estimate"', 'href="/guide"'):
        assert text in home, text

    # wizard -> area only -> estimate in one go
    wz = c.get('/projects/new').text
    assert 'How do you want to start?' in wz
    r = c.post('/projects/new', data={'csrf_token': tok(wz), 'name': 'Wizard House', 'type': 'Residential', 'location': 'Trichy',
                                      'area': '2000', 'floors': '2', 'next': 'quick'}, follow_redirects=False)
    assert r.status_code == 303 and '/workflow?estimate=' in r.headers['location'], (r.status_code, r.headers.get('location'))
    P = r.headers['location'].split('/workflow')[0]
    ws = c.get(P).text
    assert 'cv-ctx' in ws and 'Wizard House' in ws and 'Estimate rev 1' in ws and 'Creator' in ws
    assert 'Next step' in ws or 'All six steps are done' in ws

    # portfolio
    pf = c.get('/projects').text
    assert 'Wizard House' in pf and 'pf-table' in pf
    assert 'Wizard House' in c.get('/projects?type=Residential&view=cards').text
    assert 'No projects match' in c.get('/projects?type=Industrial').text
    assert 'Wizard House' not in c.get('/projects?status=input').text  # v3.8: priced from market rates at once

    # drawing studio
    empty = c.get(P + '/studio', follow_redirects=False)
    assert empty.status_code == 200 and 'No drawing yet' in empty.text
    png = Path('sample_drawings/Civora_Complete_Test_Plan.png')
    if png.is_file():
        r = c.post(P + '/upload', data={'csrf_token': tok(ws), 'next': 'studio'}, files={'file': ('plan.png', png.read_bytes(), 'image/png')},
                   follow_redirects=False)
        assert r.status_code == 303 and '/studio/' in r.headers['location'], r.headers.get('location')
        sp = c.get(r.headers['location']).text
        assert 'What Civora read' in sp and 'sizes found' in sp and '/media?page=0' in sp and 'Smart Estimate from this drawing' in sp
        assert c.get(P + '/studio', follow_redirects=False).status_code == 303
        assert c.get(P + '/studio/not-a-file').status_code == 404

    # BBS & BOQ opens the v3.1 Cost Intelligence Center
    r = c.get(P + '/boq', follow_redirects=False)
    assert r.status_code == 200 and 'Cost &amp; BOQ' in r.text

    # settings: expert + Tamil menu
    s = c.get('/settings').text
    assert 'Guided mode' in s and 'Expert mode' in s
    r = c.post('/settings', data={'csrf_token': tok(s), 'mode': 'expert', 'lang': 'ta'}, follow_redirects=False)
    assert r.status_code == 303
    h = c.get('/').text
    assert 'cv-mode-expert' in h and 'திட்டங்கள்' in h
    assert c.post('/settings', data={'csrf_token': tok(s), 'mode': 'x', 'lang': 'ta'}).status_code == 400

    # a customer sees the studio read-only
    cu = TestClient(app)
    cu.post('/register', data={'name': 'Kumar', 'username': 'v3_cust', 'password': 'cust-password-1', 'remember': '',
                               'csrf_token': tok(cu.get('/register').text)})
    t = c.get(P + '/team').text
    c.post(P + '/team/add', data={'csrf_token': tok(t), 'username': 'v3_cust', 'role': 'customer'})
    if png.is_file():
        sp = cu.get(P + '/studio', follow_redirects=True).text
        assert 'What Civora read' in sp and P + '/smart/' not in sp and 'Upload drawing' not in sp
    assert 'Customer' in cu.get(P).text

    # every GET page answers without a server error
    ids = {'pid': P.rsplit('/', 1)[1]}
    con = sqlite3.connect('data/buildquant.db')
    f = con.execute('SELECT id FROM uploads WHERE project_id=? AND original_name LIKE ? LIMIT 1', (ids['pid'], '%.png')).fetchone()
    b = con.execute('SELECT id, drawing_id FROM civora_boq_reports WHERE project_id=? LIMIT 1', (ids['pid'],)).fetchone()
    con.close()
    ids.update({'fid': (f or b)[0] if f else b[1], 'bid': b[0], 'raw': 'nope', 'mid': 'nope', 'tid': 'nope', 'rid': 'nope', 'item_id': 'nope', 'sid': 'nope'})
    bad = []
    for route in app.routes:
        if 'GET' not in (getattr(route, 'methods', None) or ()):
            continue
        url = route.path
        for k, v in ids.items():
            url = url.replace('{' + k + '}', v)
        if '{' in url:
            continue
        code = c.get(url, follow_redirects=False).status_code
        if code >= 500:
            bad.append((route.path, code))
    assert not bad, bad
    con = sqlite3.connect('data/buildquant.db')
    assert '3.0.0' in {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    print('V300 SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab')
           if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'v3.0 smoke test skipped; missing: ' + ', '.join(MISSING))
class RedesignSmokeTest(unittest.TestCase):
    def test_redesign_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            if (HERE / 'sample_drawings').is_dir():
                shutil.copytree(HERE / 'sample_drawings', tmp / 'sample_drawings')
            (tmp / '_v300_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_v300_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('V300 SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
