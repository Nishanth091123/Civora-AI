"""v3.5.0 tests: move my data between two Civora installations; delete buttons next to saved items.

Both apps run on THROW-AWAY COPIES in temp folders; the real database is never used.
"""
import importlib.util, io, json, shutil, subprocess, sys, tempfile, textwrap, unittest, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


class ZipRules(unittest.TestCase):
    def make(self, names, manifest=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            if manifest is not False:
                z.writestr('manifest.json', json.dumps(manifest or {'format': 'civora-transfer', 'version': 1, 'projects': [], 'tables': {}}))
            for n in names:
                z.writestr(n, b'x')
        return buf.getvalue()

    def test_refuses_unexpected_paths_and_non_exports(self):
        import transfer_v350 as tv
        for bad in (['../app.py'], ['uploads/../../x.png'], ['app.py'], ['uploads/not-a-uuid.png']):
            with self.assertRaises(ValueError):
                tv.read_zip(self.make(bad))
        with self.assertRaises(ValueError):
            tv.read_zip(b'not a zip')
        with self.assertRaises(ValueError):
            tv.read_zip(self.make([], manifest=False))
        with self.assertRaises(ValueError):
            tv.read_zip(self.make([], manifest={'format': 'other', 'projects': []}))

    def test_accepts_clean_export(self):
        import transfer_v350 as tv
        m, files = tv.read_zip(self.make(['uploads/0f0e0d0c-0b0a-4908-8706-050403020100.png']))
        self.assertEqual(list(files), ['0f0e0d0c-0b0a-4908-8706-050403020100.png'])


COMMON = r'''
import re, sqlite3, html as H, os
from pathlib import Path
from fastapi.testclient import TestClient
from app import app
def tok(h):
    return re.search(r'name="csrf_token" value="([^"]+)"', h).group(1)
def forms(h):
    return [H.unescape(a) for a in re.findall(r'<form method="post" action="([^"]+)"', h)]
def action(h, contains):
    for a in forms(h):
        if contains in a:
            return a
    raise AssertionError('no form posting to ' + contains)
def reg(c, u):
    c.post('/register', data={'name': u.title(), 'username': u, 'password': 'move-password-1', 'remember': '', 'csrf_token': tok(c.get('/register').text)})
con = lambda: sqlite3.connect('data/buildquant.db')
'''

SMOKE_PC = textwrap.dedent(COMMON + r'''
c = TestClient(app); reg(c, 'pc_owner')
c.post('/rates', data={'csrf_token': tok(c.get('/rates').text), 'cement_bag': '420', 'steel': '68'})
r = c.post('/quick', data={'confirm': '1', 'csrf_token': tok(c.get('/').text), 'area': '1000', 'floors': '2'}, follow_redirects=False)
P = '/projects/' + re.search(r'/projects/([0-9a-f-]{36})', r.headers['location']).group(1)
s = c.get(P + '/structure').text
c.post(action(s, '/structural/advanced/add'), data={'confirm': '1', 'csrf_token': tok(s), 'kind': 'column', 'reference': 'C1', 'count': 4, 'length': .23, 'width': .3, 'depth': 3})
b = c.get(P + '/bbs').text
c.post(action(b, '/bbs/add'), data={'confirm': '1', 'csrf_token': tok(b), 'reference': 'C1-MAIN', 'diameter': 12, 'count': 16, 'length': 3.4})
png = Path('sample_drawings/Civora_Complete_Test_Plan.png').read_bytes()
c.post(P + '/upload', data={'csrf_token': tok(c.get(P).text), 'next': 'studio'}, files={'file': ('plan.png', png, 'image/png')})

# delete buttons next to saved items
st = c.get(P + '/structure').text
assert any('/structural/advanced/' in a and '/delete?return=' in a for a in forms(st)) and 'class="dt-x"' in st
bb = c.get(P + '/bbs').text
assert any('/structural/advanced/bbs/' in a for a in forms(bb))
fid = con().execute("SELECT id FROM uploads WHERE original_name='plan.png'").fetchone()[0]
ds = c.get(P + '/studio/' + fid).text
assert any('/data/files/' in a and a.endswith('return=' + P + '/studio') for a in forms(ds)), forms(ds)
assert P + '/data#delete' in c.get('/projects').text
# a viewer sees no delete buttons
v = TestClient(app); reg(v, 'pc_viewer')
t = c.get(P + '/team').text
c.post(action(t, '/team/add'), data={'csrf_token': tok(t), 'username': 'pc_viewer', 'role': 'customer'})
for page in ('/structure', '/bbs', '/studio/' + fid):
    assert 'class="dt-x"' not in v.get(P + page).text, page
assert P + '/data#delete' not in v.get('/projects').text

tp = c.get('/settings').text
assert '/transfer' in tp and 'Move my data' in c.get('/transfer').text
z = c.get('/transfer/export.zip')
assert z.status_code == 200 and z.headers['content-type'] == 'application/zip'
Path(os.environ['CIVORA_EXPORT']).write_bytes(z.content)
v_zip = v.get('/transfer/export.zip').content           # the viewer owns nothing: shared project not exported
import zipfile, io, json
assert json.loads(zipfile.ZipFile(io.BytesIO(v_zip)).read('manifest.json'))['projects'] == []
print('PC SMOKE OK', P)
''')

SMOKE_ONLINE = textwrap.dedent(COMMON + r'''
c = TestClient(app); reg(c, 'online_owner')
c.post('/rates', data={'csrf_token': tok(c.get('/rates').text), 'cement_bag': '450'})      # set here first: must be kept
data = Path(os.environ['CIVORA_EXPORT']).read_bytes()
page = c.get('/transfer').text
r = c.post(action(page, '/transfer/import'), data={'csrf_token': tok(page)}, files={'file': ('Civora_my_data.zip', data, 'application/zip')},
           follow_redirects=False)
assert r.status_code == 303 and 'added=1' in r.headers['location'], (r.status_code, r.text[-1500:])
db = con()
uid = db.execute("SELECT id FROM users WHERE username='online_owner'").fetchone()[0]
pid = db.execute('SELECT id FROM projects WHERE owner_id=?', (uid,)).fetchone()[0]
P = '/projects/' + pid
assert db.execute('SELECT count(*) FROM civora_boq_reports WHERE project_id=?', (pid,)).fetchone()[0] == 1
assert db.execute('SELECT count(*) FROM civora_structural_v210 WHERE project_id=?', (pid,)).fetchone()[0] == 1
assert db.execute('SELECT count(*) FROM civora_bbs_v210 WHERE project_id=?', (pid,)).fetchone()[0] == 1
assert db.execute('SELECT count(*) FROM civora_members_v270 WHERE project_id=?', (pid,)).fetchone()[0] == 0   # team not moved
rates = dict(db.execute('SELECT key, rate FROM civora_rate_master_v260 WHERE user_id=?', (uid,)).fetchall())
assert rates['cement_bag'] == 450 and rates['steel'] == 68, rates
fid = db.execute("SELECT id FROM uploads WHERE project_id=? AND original_name='plan.png'", (pid,)).fetchone()[0]
assert c.get('/files/' + fid).status_code == 200 and c.get(P + '/studio/' + fid).status_code == 200
assert 'Quick Estimate' in c.get(P + '/boq').text and c.get(P + '/reports').status_code == 200
assert any(rp.endswith('.xlsx') for rp in re.findall(r'href="([^"]+)"', c.get(P + '/reports').text))
# importing again: skipped, never duplicated
r = c.post('/transfer/import', data={'csrf_token': tok(page)}, files={'file': ('x.zip', data, 'application/zip')}, follow_redirects=False)
assert 'added=0&skipped=1' in r.headers['location']
assert con().execute('SELECT count(*) FROM projects').fetchone()[0] == 1
assert any('before-import' in p.name for p in Path('backups/db').glob('*.db'))
# a bad file is refused with a message
assert 'not a Civora export' in c.post('/transfer/import', data={'csrf_token': tok(page)}, files={'file': ('x.zip', b'hello', 'application/zip')}).text
assert '3.5.0' in {r[0] for r in con().execute('SELECT version FROM schema_migrations')}
print('ONLINE SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab') if importlib.util.find_spec(m) is None]


def _copy(tmp):
    for f in HERE.glob('*.py'):
        if not f.name.startswith('test_') and f.name != 'run_tests.py':
            shutil.copy2(f, tmp / f.name)
    if (HERE / 'sample_drawings').is_dir():
        shutil.copytree(HERE / 'sample_drawings', tmp / 'sample_drawings')


@unittest.skipIf(MISSING, 'v3.5 smoke test skipped; missing: ' + ', '.join(MISSING))
class TransferSmokeTest(unittest.TestCase):
    def test_pc_to_online(self):
        import os
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            a, b = Path(a), Path(b)
            _copy(a); _copy(b)
            env = dict(os.environ, CIVORA_EXPORT=str(a / 'export.zip'))
            for folder, code, ok in ((a, SMOKE_PC, 'PC SMOKE OK'), (b, SMOKE_ONLINE, 'ONLINE SMOKE OK')):
                (folder / '_smoke.py').write_text(code, encoding='utf-8')
                r = subprocess.run([sys.executable, '_smoke.py'], cwd=folder, capture_output=True, text=True, timeout=600, env=env)
                self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
                self.assertIn(ok, r.stdout)


if __name__ == '__main__':
    unittest.main()
