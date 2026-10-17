"""v3.9.2: only the site owner is 'Admin'; everyone else is a 'User'. Server storage details are Admin-only."""
import importlib.util, shutil, subprocess, sys, tempfile, textwrap, unittest, os
from pathlib import Path

import team_v270

HERE = Path(__file__).resolve().parent


class LabelTest(unittest.TestCase):
    def test_display_roles(self):
        self.assertEqual(team_v270.display('owner', admin=True)[0], 'Admin')
        self.assertEqual(team_v270.display('owner')[0], 'Creator')
        self.assertEqual(team_v270.display('engineer')[0], 'Engineer')
        self.assertNotIn('admin', team_v270.INVITE_ROLES)        # nobody can be invited as Admin


SMOKE = textwrap.dedent(r'''
    import re
    from fastapi.testclient import TestClient
    from app import app

    def tok(h):
        return re.search(r'name="csrf_token" value="([^"]+)"', h).group(1)
    def reg(name, user):
        c = TestClient(app)
        c.post('/register', data={'name': name, 'username': user, 'password': 'admin-password-1', 'remember': '', 'csrf_token': tok(c.get('/register').text)})
        return c
    adm = reg('Nishanth S', 'nishanth_s')
    usr = reg('Ravi', 'ravi_user')
    # header badge
    assert '@nishanth_s · <b style="color:#b45309">Admin</b>' in adm.get('/').text
    h = usr.get('/').text
    assert '@ravi_user · User' in h and '>Admin</b>' not in h
    # storage page: Admin only, not listed for users
    assert adm.get('/system/storage').status_code == 200
    assert usr.get('/system/storage').status_code == 403
    assert '/system/storage' in adm.get('/more').text and '/system/storage' not in usr.get('/more').text
    # a user's own project says Creator, the Admin sees Admin on it
    r = usr.post('/quick', data={'confirm': '1', 'csrf_token': tok(usr.get('/').text), 'area': '1000', 'floors': '1'}, follow_redirects=False)
    P = '/projects/' + re.search(r'/projects/([0-9a-f-]{36})', r.headers['location']).group(1)
    w = usr.get(P + '/workflow').text
    assert 'You: Creator' in w and 'You: Admin' not in w
    w = adm.get(P + '/workflow').text
    assert 'You: Admin' in w and '>Admin</span>' in w
    # nobody else can take the Admin username
    x = TestClient(app)
    x.post('/register', data={'name': 'Fake', 'username': 'nishanth_s', 'password': 'other-password-1', 'remember': '', 'csrf_token': tok(x.get('/register').text)})
    assert 'Admin' not in x.get('/').text
    print('V392 SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous') if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'v3.9.2 smoke test skipped; missing: ' + ', '.join(MISSING))
class AdminSmokeTest(unittest.TestCase):
    def test_admin_and_users_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            (tmp / '_v392_smoke.py').write_text(SMOKE, encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'CIVORA_OWNER')}
            r = subprocess.run([sys.executable, '_v392_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600, env=env)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('V392 SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
