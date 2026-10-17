"""v2.7.0 tests: team access (roles, invite links, activity log, engineer sign-off).

The app smoke test runs on a THROW-AWAY COPY in a temp folder; the real database is never used.
"""
import importlib.util, shutil, sqlite3, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

import team_v270 as tm

HERE = Path(__file__).resolve().parent


class PermissionTests(unittest.TestCase):
    def test_required_permission(self):
        P = '/projects/abc'
        self.assertEqual(tm.required_permission('GET', P + '/workflow'), 'view')
        self.assertEqual(tm.required_permission('GET', P + '/team'), 'view')
        self.assertEqual(tm.required_permission('POST', P + '/smart/manual'), 'edit')
        self.assertEqual(tm.required_permission('POST', P + '/rates/apply'), 'edit')
        self.assertEqual(tm.required_permission('POST', P + '/takeoff/x/delete'), 'edit')
        self.assertEqual(tm.required_permission('POST', P + '/structural/design'), 'design')
        self.assertEqual(tm.required_permission('POST', P + '/structural/review/x'), 'design')
        self.assertEqual(tm.required_permission('POST', P + '/signoff'), 'design')
        self.assertEqual(tm.required_permission('POST', P + '/structural/advanced/add'), 'edit')
        self.assertEqual(tm.required_permission('POST', P + '/uploads/f1/delete'), 'manage')
        self.assertEqual(tm.required_permission('POST', P + '/team/invite'), 'manage')

    def test_role_matrix(self):
        for role in ('dealer', 'customer'):
            self.assertTrue(tm.allowed(role, 'view'))
            self.assertFalse(tm.allowed(role, 'edit'))
        self.assertTrue(tm.allowed('colleague', 'edit'))
        self.assertFalse(tm.allowed('colleague', 'design'))
        self.assertTrue(tm.allowed('engineer', 'design'))
        self.assertFalse(tm.allowed('engineer', 'manage'))
        self.assertTrue(tm.allowed('owner', 'manage'))
        self.assertFalse(tm.allowed(None, 'view'))

    def test_safe_next(self):
        self.assertEqual(tm.safe_next('/invite/abc'), '/invite/abc')
        for bad in ('https://evil.example', '//evil.example', '/\\evil', ''):
            self.assertEqual(tm.safe_next(bad), '')

    def test_project_role_and_listing(self):
        c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
        c.execute('CREATE TABLE projects(id TEXT, owner_id TEXT, name TEXT, created INTEGER)')
        db = lambda: _Ctx(c)
        tm.init(db)
        c.executemany('INSERT INTO projects VALUES(?,?,?,?)', [('p1', 'u1', 'A', 1), ('p2', 'u2', 'B', 2), ('p3', 'u2', 'C', 3)])
        c.execute("INSERT INTO civora_members_v270 VALUES('p2','u1','customer','u2',5)")
        self.assertEqual(tm.project_role(c, 'p1', 'u1'), 'owner')
        self.assertEqual(tm.project_role(c, 'p2', 'u1'), 'customer')
        self.assertIsNone(tm.project_role(c, 'p3', 'u1'))
        self.assertIsNone(tm.project_role(c, 'nope', 'u1'))
        rows = tm.accessible_projects(c, 'u1')
        self.assertEqual([(r['id'], r['my_role']) for r in rows], [('p2', 'customer'), ('p1', 'owner')])
        self.assertEqual(len(tm.accessible_projects(c, 'u1', 'p.name LIKE ?', ('B',))), 1)

    def test_activity_labels(self):
        self.assertEqual(tm.action_for('/projects/x/smart/manual'), 'Ran Smart Estimate')
        self.assertEqual(tm.action_for('/projects/x/smart/upload'), 'Uploaded a drawing for Smart Estimate')
        self.assertEqual(tm.action_for('/projects/x/rates/apply'), 'Applied Rate Master prices')


class _Ctx:
    def __init__(self, c): self.c = c
    def __enter__(self): return self.c
    def __exit__(self, *a): self.c.commit()


SMOKE = textwrap.dedent(r'''
    import re, sqlite3
    from collections import Counter
    from fastapi.testclient import TestClient
    from app import app

    keys = [(m, r.path) for r in app.routes for m in (getattr(r, 'methods', None) or ())]
    dup = sorted(k for k, n in Counter(keys).items() if n > 1)
    assert not dup, 'Duplicate routes: %s' % dup

    def tok(html):
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    def user(username):
        c = TestClient(app)
        r = c.post('/register', data={'name': username.title().replace('_', ' '), 'username': username, 'password': 'team-password-1',
                                      'remember': '', 'csrf_token': tok(c.get('/register').text)}, follow_redirects=False)
        assert r.status_code == 303, r.text[:200]
        return c

    owner, eng, col, cust, outsider = user('owner_o'), user('eng_e'), user('col_c'), user('cust_k'), user('out_x')
    r = owner.post('/projects/new', data={'name': 'Team House', 'type': 'Residential', 'location': 'Trichy', 'area': '1200',
                                          'csrf_token': tok(owner.get('/projects/new').text)}, follow_redirects=False)
    P = r.headers['location']
    team = owner.get(P + '/team').text
    assert 'People on this project' in team and 'Invite people' in team

    # add by username, and by invite link
    r = owner.post(P + '/team/add', data={'csrf_token': tok(team), 'username': 'eng_e', 'role': 'engineer'}, follow_redirects=False)
    assert r.status_code == 303
    r = owner.post(P + '/team/add', data={'csrf_token': tok(team), 'username': 'nobody_here', 'role': 'customer'})
    assert 'No Civora user called' in r.text
    page = owner.post(P + '/team/invite', data={'csrf_token': tok(team), 'role': 'colleague'}).text
    link = re.search(r'value="(http[^"]+/invite/[^"]+)"', page).group(1)
    path = '/invite/' + link.rsplit('/invite/', 1)[1]
    assert 'wa.me' in page
    inv = col.get(path).text
    assert 'Join project as Colleague' in inv
    r = col.post(path, data={'csrf_token': tok(inv)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].endswith('/workflow')
    # link is single-use
    again = cust.get(path)
    assert again.status_code == 410 and 'already been used' in again.text
    # customer invite link opened while logged out -> sign-in page that returns to the invite
    page = owner.post(P + '/team/invite', data={'csrf_token': tok(team), 'role': 'customer'}).text
    path2 = '/invite/' + re.search(r'value="http[^"]+/invite/([^"]+)"', page).group(1)
    anon = TestClient(app)
    first = anon.get(path2).text
    assert 'Create free account' in first and 'next=%2Finvite%2F' in first
    r = cust.post(path2, data={'csrf_token': tok(cust.get(path2).text)}, follow_redirects=False)
    assert r.status_code == 303

    # login with next= goes back to the invite page
    r = anon.post('/login', data={'identifier': 'out_x', 'password': 'team-password-1', 'remember': '', 'next': '/rates',
                                  'csrf_token': tok(anon.get('/login?next=/rates').text)}, follow_redirects=False)
    assert r.headers['location'] == '/rates'
    r = anon.post('/login', data={'identifier': 'out_x', 'password': 'team-password-1', 'remember': '', 'next': 'https://evil.example',
                                  'csrf_token': tok(anon.get('/login').text)}, follow_redirects=False)
    assert r.headers['location'] == '/projects'

    # who sees what
    for c in (owner, eng, col, cust):
        assert c.get(P + '/workflow').status_code == 200
        assert 'Team House' in c.get('/projects').text
    assert 'Shared · Customer' in cust.get('/projects').text
    assert outsider.get(P + '/workflow').status_code == 404
    assert 'Team House' not in outsider.get('/projects').text
    w = cust.get(P + '/workflow').text
    assert 'You are viewing as Customer' in w and 'Apply my rates' not in w and 'Engineer sign-off' not in w

    # customer cannot change anything (friendly 403 page)
    form = col.get(P + '/smart/manual').text
    r = cust.post(P + '/smart/manual', data={'confirm': '1', 'csrf_token': tok(cust.get(P + '/workflow').text), 'length': '10'})
    assert r.status_code == 403 and 'Your role in this project is Customer' in r.text and 'cv-side' in r.text
    # colleague can run Smart Estimate; owner's rates price it
    owner.post('/rates', data={'csrf_token': tok(owner.get('/rates').text), 'cement_bag': '410', 'steel': '66'})
    r = col.post(P + '/smart/manual', data={'confirm': '1', 'csrf_token': tok(form), 'length': '12', 'width': '9'}, follow_redirects=False)
    assert r.status_code == 303 and 'estimate=' in r.headers['location'], (r.status_code, r.text[:300])
    assert 'per sq.ft' in col.get(r.headers['location']).text, "owner's rates not used for colleague's estimate"
    # colleague cannot sign off or manage the team; engineer can sign off
    wt = tok(col.get(P + '/workflow').text)
    assert col.post(P + '/signoff', data={'csrf_token': wt, 'note': 'checked all', 'confirm': 'yes'}).status_code == 403
    assert col.post(P + '/team/invite', data={'csrf_token': wt, 'role': 'customer'}).status_code == 403
    ew = eng.get(P + '/workflow').text
    assert 'Engineer sign-off' in ew
    assert eng.post(P + '/signoff', data={'csrf_token': tok(ew), 'note': 'ok', 'confirm': 'yes'}).status_code == 400
    r = eng.post(P + '/signoff', data={'csrf_token': tok(ew), 'note': 'Footings checked against S-02', 'confirm': 'yes'}, follow_redirects=False)
    assert r.status_code == 303
    w = cust.get(P + '/workflow').text
    assert 'Reviewed by Eng E (Engineer)' in w and 'Footings checked against S-02' in w
    # only the owner deletes uploaded files
    fid = re.search(r'/files/([0-9a-f-]{36})', owner.get(P).text).group(1)
    assert cust.get('/files/' + fid).status_code == 200            # members can download
    assert outsider.get('/files/' + fid).status_code == 404
    assert eng.post(P + '/uploads/' + fid + '/delete', data={'csrf_token': tok(ew)}).status_code == 403

    # activity log
    t = owner.get(P + '/team').text
    for text in ('Added Eng E as Engineer', 'Joined as Colleague', 'Ran Smart Estimate', 'Signed off the design review'):
        assert text in t, text
    # role change + removal
    con = sqlite3.connect('data/buildquant.db')
    cid = con.execute("SELECT id FROM users WHERE username='cust_k'").fetchone()[0]
    con.close()
    r = owner.post(P + '/team/role', data={'csrf_token': tok(t), 'user_id': cid, 'role': 'dealer'}, follow_redirects=False)
    assert r.status_code == 303 and 'Shared · Dealer' in cust.get('/projects').text
    r = owner.post(P + '/team/remove', data={'csrf_token': tok(t), 'user_id': cid}, follow_redirects=False)
    assert r.status_code == 303 and cust.get(P + '/workflow').status_code == 404

    # not signed in -> sent to login, then back
    r = TestClient(app).get(P + '/workflow', follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].startswith('/login?next=')

    con = sqlite3.connect('data/buildquant.db')
    assert '2.7.0' in {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    print('TEAM SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab')
           if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'Team smoke test skipped; missing: ' + ', '.join(MISSING))
class TeamSmokeTest(unittest.TestCase):
    def test_team_access_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            (tmp / '_team_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_team_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('TEAM SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
