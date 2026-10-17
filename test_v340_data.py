"""v3.4.0 tests: project data page, deletes (item, estimate, file, whole project), clear rates.

The app smoke test runs on a THROW-AWAY COPY in a temp folder; the real database is never used.
"""
import importlib.util, shutil, sqlite3, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def mem_db():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''
        CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE uploads(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), original_name TEXT, stored_name TEXT, content_type TEXT, created INTEGER);
        CREATE TABLE drawing_measurements(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), upload_id TEXT NOT NULL REFERENCES uploads(id), work TEXT);
        CREATE TABLE civora_boq_reports(id TEXT PRIMARY KEY, project_id TEXT, drawing_id TEXT, payload TEXT, created INTEGER);
        CREATE TABLE civora_activity_v270(id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, user_id TEXT, action TEXT, detail TEXT, at INTEGER);
        CREATE TABLE users(id TEXT PRIMARY KEY);
    ''')
    for pid in ('p1', 'p2'):
        c.execute('INSERT INTO projects VALUES(?,?)', (pid, pid))
        c.execute('INSERT INTO uploads VALUES(?,?,?,?,?,1)', (pid + 'f', pid, 'plan.png', pid + 'f.png', 'image/png'))
        c.execute("INSERT INTO drawing_measurements VALUES(?,?,?,'wall')", (pid + 'm', pid, pid + 'f'))
        c.execute("INSERT INTO civora_boq_reports VALUES(?,?,?,'{}',1)", (pid + 'b', pid, pid + 'f'))
        c.execute("INSERT INTO civora_activity_v270(project_id,user_id,action,detail,at) VALUES(?,'u','x','',1)", (pid,))
    return c


class DeleteTests(unittest.TestCase):
    def test_delete_project_only_that_project_children_first(self):
        import data_v340 as dv
        c = mem_db()
        paths = dv.delete_project(c, 'p1', '/tmp/x')
        self.assertEqual([p.name for p in paths], ['p1f.png'])
        for t in ('projects', 'uploads', 'drawing_measurements', 'civora_boq_reports', 'civora_activity_v270'):
            col = 'id' if t == 'projects' else 'project_id'
            self.assertEqual(c.execute(f'SELECT count(*) FROM {t} WHERE {col}=?', ('p1',)).fetchone()[0], 0, t)
            self.assertEqual(c.execute(f'SELECT count(*) FROM {t} WHERE {col}=?', ('p2',)).fetchone()[0], 1, t)

    def test_delete_file_takes_its_estimates_and_measurements(self):
        import data_v340 as dv
        c = mem_db()
        path = dv.delete_file(c, 'p1', 'p1f', '/tmp/x')
        self.assertEqual(path.name, 'p1f.png')
        self.assertEqual(c.execute("SELECT count(*) FROM civora_boq_reports WHERE project_id='p1'").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT count(*) FROM civora_boq_reports WHERE project_id='p2'").fetchone()[0], 1)
        self.assertIsNone(dv.delete_file(c, 'p1', 'p2f', '/tmp/x'))       # another project's file: not found

    def test_estimate_source_names(self):
        import data_v340 as dv
        self.assertEqual(dv.estimate_source({'source': 'smart_estimate_v260', 'source_detail': 'quick_v280'}), 'Quick Estimate')
        self.assertEqual(dv.estimate_source({'source': 'smart_estimate_v260'}), 'Smart Estimate')
        self.assertEqual(dv.estimate_source({}), 'Drawing BOQ')

    def test_unsafe_stored_name_refused(self):
        import data_v340 as dv
        c = mem_db()
        c.execute("UPDATE uploads SET stored_name='../../app.py' WHERE id='p1f'")
        with self.assertRaises(ValueError):
            dv.delete_file(c, 'p1', 'p1f', '/tmp/x')


SMOKE = textwrap.dedent(r'''
    import re, sqlite3, html as H
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
        c.post('/register', data={'name': u.title(), 'username': u, 'password': 'data-password-1', 'remember': '', 'csrf_token': tok(c.get('/register').text)})
    c = TestClient(app); reg(c, 'data_owner')
    con = lambda: sqlite3.connect('data/buildquant.db')
    r = c.post('/quick', data={'confirm': '1', 'csrf_token': tok(c.get('/').text), 'area': '1000', 'floors': '1'}, follow_redirects=False)
    P = '/projects/' + re.search(r'/projects/([0-9a-f-]{36})', r.headers['location']).group(1)
    pid = P.rsplit('/', 1)[1]
    c.post(P + '/quick', data={'confirm': '1', 'csrf_token': tok(c.get(P + '/smart').text), 'area': '1200', 'floors': '2'})   # second estimate
    s = c.get(P + '/structure').text
    c.post(action(s, '/structural/advanced/add'), data={'confirm': '1', 'csrf_token': tok(s), 'kind': 'column', 'reference': 'C1', 'count': 4, 'length': .23, 'width': .3, 'depth': 3})
    b = c.get(P + '/bbs').text
    c.post(action(b, '/bbs/add'), data={'confirm': '1', 'csrf_token': tok(b), 'reference': 'C1-MAIN', 'diameter': 12, 'count': 16, 'length': 3.4})

    page = c.get(P + '/data').text
    assert 'Stored data' in page and 'Delete this whole project' in page and 'Upload a drawing or file' in page, page[-2000:]
    assert 'class="cv-cb-tab on" href="' + P + '/more"' in page          # v3.8: Data is inside More
    n_boq = lambda: con().execute('SELECT count(*) FROM civora_boq_reports WHERE project_id=?', (pid,)).fetchone()[0]
    assert n_boq() == 2

    # upload stays available, comes back to the data page
    png = Path('sample_drawings/Civora_Complete_Test_Plan.png').read_bytes() if Path('sample_drawings/Civora_Complete_Test_Plan.png').exists() else b'\x89PNG\r\n\x1a\n' + b'0' * 64
    r = c.post(action(page, '/upload?return='), data={'csrf_token': tok(page), 'next': 'data'}, files={'file': ('plan.png', png, 'image/png')}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == P + '/data', r.headers.get('location')
    page = c.get(P + '/data').text
    assert 'plan.png' in page

    # delete one estimate (from Cost & BOQ revisions, returns there)
    boq = c.get(P + '/boq').text
    r = c.post(action(boq, '/data/estimates/'), data={'csrf_token': tok(boq)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == P + '/boq', r.headers.get('location')
    assert n_boq() == 1
    # delete a structural element and a bar through the existing routes, back to the data page
    page = c.get(P + '/data').text
    for part in ('/structural/advanced/bbs/', '/structural/advanced/'):
        a = [x for x in forms(page) if part in x and x.endswith('return=' + P + '/data') and (part != '/structural/advanced/' or '/bbs/' not in x)][0]
        r = c.post(a, data={'csrf_token': tok(page)}, follow_redirects=False)
        assert r.status_code == 303 and r.headers['location'] == P + '/data', (a, r.status_code, r.headers.get('location'))
        page = c.get(P + '/data').text
    assert 'C1-MAIN' not in page

    # colleague: can see and delete estimates, cannot delete files or the project
    k = TestClient(app); reg(k, 'data_colleague')
    t = c.get(P + '/team').text
    c.post(action(t, '/team/add'), data={'csrf_token': tok(t), 'username': 'data_colleague', 'role': 'colleague'})
    kp = k.get(P + '/data').text
    assert 'Delete this whole project' not in kp and '/data/files/' not in kp
    fid = con().execute("SELECT id FROM uploads WHERE project_id=? AND original_name='plan.png'", (pid,)).fetchone()[0]
    assert k.post(P + f'/data/files/{fid}/delete', data={'csrf_token': tok(kp)}).status_code == 403
    assert k.post(P + '/data/delete-project', data={'csrf_token': tok(kp), 'confirm_name': 'x'}).status_code == 403
    o = TestClient(app); reg(o, 'data_outsider')
    assert o.get(P + '/data').status_code == 404

    # owner deletes a file: its estimate goes too; v3.8: the file stays until the Recycle Bin is emptied
    stored = con().execute('SELECT stored_name FROM uploads WHERE id=?', (fid,)).fetchone()[0]
    assert Path('data/uploads/' + stored).exists()
    page = c.get(P + '/data').text
    r = c.post(P + f'/data/files/{fid}/delete', data={'csrf_token': tok(page)}, follow_redirects=False)
    assert r.status_code == 303 and Path('data/uploads/' + stored).exists()
    assert con().execute('SELECT COUNT(*) FROM civora_bin_v380 WHERE tbl=?', ('uploads',)).fetchone()[0] == 1   # restorable
    qfid = con().execute("SELECT drawing_id FROM civora_boq_reports WHERE project_id=?", (pid,)).fetchone()[0]
    c.post(P + f'/data/files/{qfid}/delete', data={'csrf_token': tok(page)})
    assert n_boq() == 0

    # rates: clear all
    c.post('/rates', data={'csrf_token': tok(c.get('/rates').text), 'cement_bag': '420', 'steel': '68'})
    assert con().execute('SELECT count(*) FROM civora_rate_master_v260 WHERE rate>0').fetchone()[0] >= 2
    rp = c.get('/rates').text
    assert 'Reset all to market rates' in rp and 'cv-rclr' in rp
    r = c.post('/rates/clear', data={'csrf_token': tok(rp)}, follow_redirects=False)
    assert r.status_code == 303 and 'market rates are used again' in c.get('/rates?cleared=1').text
    uid = con().execute("SELECT id FROM users WHERE username='data_owner'").fetchone()[0]
    assert con().execute('SELECT count(*) FROM civora_rate_master_v260 WHERE user_id=?', (uid,)).fetchone()[0] == 0

    # delete the whole project: wrong name refused, right name -> backup, everything gone
    page = c.get(P + '/data').text
    assert c.post(P + '/data/delete-project', data={'csrf_token': tok(page), 'confirm_name': 'wrong'}).status_code == 400
    assert con().execute('SELECT count(*) FROM projects WHERE id=?', (pid,)).fetchone()[0] == 1
    name = con().execute('SELECT name FROM projects WHERE id=?', (pid,)).fetchone()[0]
    before = set(Path('backups/db').glob('*.db')) if Path('backups/db').exists() else set()
    r = c.post(P + '/data/delete-project', data={'csrf_token': tok(page), 'confirm_name': '  ' + name.upper() + ' '}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/projects?deleted=1'
    assert any('before-project-delete' in p.name for p in set(Path('backups/db').glob('*.db')) - before)
    db = con()
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = {x[1] for x in db.execute(f'PRAGMA table_info("{t}")')}
        if 'project_id' in cols and t != 'civora_bin_v380':       # v3.8: the Recycle Bin keeps a restorable copy
            assert db.execute(f'SELECT count(*) FROM "{t}" WHERE project_id=?', (pid,)).fetchone()[0] == 0, t
    assert db.execute("SELECT count(*) FROM civora_bin_v380 WHERE tbl='projects' AND project_id=?", (pid,)).fetchone()[0] == 1
    assert db.execute('SELECT count(*) FROM projects WHERE id=?', (pid,)).fetchone()[0] == 0
    assert 'Project deleted' in c.get('/projects?deleted=1').text and c.get(P).status_code == 404
    assert '3.4.0' in {r[0] for r in db.execute('SELECT version FROM schema_migrations')}
    print('V340 SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab') if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'v3.4 smoke test skipped; missing: ' + ', '.join(MISSING))
class DataSmokeTest(unittest.TestCase):
    def test_data_page_and_deletes_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            if (HERE / 'sample_drawings').is_dir():
                shutil.copytree(HERE / 'sample_drawings', tmp / 'sample_drawings')
            (tmp / '_v340_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_v340_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('V340 SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
