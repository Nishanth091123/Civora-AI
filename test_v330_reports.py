"""v3.3.0 tests: Reports Center and Tamil interface.

The app smoke test runs on a THROW-AWAY COPY in a temp folder; the real database is never used.
"""
import importlib.util, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

import i18n_v330 as i18n

HERE = Path(__file__).resolve().parent


class TamilTests(unittest.TestCase):
    def test_exact_text_nodes_only(self):
        doc = '<nav><a href="/projects">Projects</a></nav><h3> Cost Summary </h3><p>Projects and more</p><b>1,250 kg</b>'
        out = i18n.translate_html(doc)
        self.assertIn('>திட்டங்கள்</a>', out)
        self.assertIn('> செலவு சுருக்கம் </h3>', out)          # surrounding spaces kept
        self.assertIn('<p>Projects and more</p>', out)         # partial match never translated
        self.assertIn('<b>1,250 kg</b>', out)                  # numbers untouched
        self.assertIn('href="/projects"', out)

    def test_skips_script_style_svg_title_textarea(self):
        doc = ('<title>Projects</title><style>.x:after{content:">Projects<"}</style><script>var a="<b>Projects</b>"</script>'
               '<svg><text>Projects</text></svg><textarea>Projects</textarea><i>Projects</i>')
        out = i18n.translate_html(doc)
        self.assertEqual(out.count('Projects'), 5)
        self.assertIn('<i>திட்டங்கள்</i>', out)
        self.assertIn('</svg>புதிய திட்டம்</a>', i18n.translate_html('<a><svg><path/></svg>New Project</a>'))

    def test_placeholder_patterns_and_escaping(self):
        out = i18n.translate_html('<input placeholder="City, District" value="Projects"><span>6 work item(s)</span><span>Next: Cost &amp; budget</span>')
        self.assertIn('placeholder="நகரம், மாவட்டம்"', out)
        self.assertIn('value="Projects"', out)                 # form values never change
        self.assertIn('6 வேலைகள்', out)
        self.assertIn('அடுத்து: செலவு &amp; பட்ஜெட்', out)

    def test_engineering_warning_stays_english(self):
        self.assertIn('DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED', i18n.word('DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.'))
        self.assertIsNone(i18n.word('Some new label'))


class DocumentTests(unittest.TestCase):
    def st(self, **kw):
        base = {'cost': {'total': 0, 'segments': [], 'unrated': 0}, 'structural_items': [], 'takeoffs': [], 'boq': None, 'bar_count': 0,
                'structural_totals': {'rcc_m3': 0, 'formwork_m2': 0, 'steel_kg': 0}, 'boq_count': 0}
        base.update(kw)
        return base

    def test_empty_project_nothing_ready(self):
        import reports_v330 as rp
        docs = rp.documents('p1', self.st())
        self.assertEqual(rp.ready_count(docs), (0, 5))
        self.assertTrue(all(not d['files'] for d in docs if d['key'] != 'summary'))

    def test_links_point_to_existing_routes(self):
        import reports_v330 as rp
        st = self.st(cost={'total': 100, 'segments': [], 'unrated': 0}, boq={'id': 'b1', 'drawing_id': 'f1', 'data': {}, 'created': 1},
                     structural_items=[{'kind': 'column', 'reference': 'C1', 'net_m3': 1}], bar_count=1)
        urls = {u for d in rp.documents('p1', st) for _, u in d['files']}
        for u in ('/projects/p1/drawings/f1/boq/b1/excel', '/projects/p1/drawings/f1/boq/b1/pdf', '/projects/p1/structural/advanced/export.xlsx',
                  '/projects/p1/structure/details', '/projects/p1/structural/review/report.html', '/projects/p1/workflow/download-all',
                  '/projects/p1/reports/summary'):
            self.assertIn(u, urls)


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
    c.post('/register', data={'name': 'Report Owner', 'username': 'report_owner', 'password': 'report-password-1', 'remember': '',
                              'csrf_token': tok(c.get('/register').text)})
    assert 'No projects yet' in c.get('/reports').text
    c.post('/rates', data={'csrf_token': tok(c.get('/rates').text), 'rmc': '5600', 'steel': '68', 'cement_bag': '420'})
    r = c.post('/quick', data={'confirm': '1', 'csrf_token': tok(c.get('/').text), 'area': '1200', 'floors': '1'}, follow_redirects=False)
    P = '/projects/' + re.search(r'/projects/([0-9a-f-]{36})', r.headers['location']).group(1)
    s = c.get(P + '/structure').text
    c.post(action(s, '/structural/advanced/add'), data={'confirm': '1', 'csrf_token': tok(s), 'kind': 'column', 'reference': 'C1', 'count': 4, 'length': .23, 'width': .3, 'depth': 3})
    b = c.get(P + '/bbs').text
    c.post(action(b, '/bbs/add'), data={'confirm': '1', 'csrf_token': tok(b), 'reference': 'C1-MAIN', 'diameter': 12, 'count': 16, 'length': 3.4, 'lap': .6})

    center = c.get('/reports').text
    assert 'Reports' in center and P + '/reports' in center and 'Needs engineer review' in center, center[-3000:]
    assert 'Quick estimate' in c.get('/reports?q=quick').text and 'No projects match' in c.get('/reports?q=zzzz').text
    rep = c.get(P + '/reports').text
    assert 'Project reports' in rep and 'Site detail sheet' in rep and '5 of 5' in rep, rep[-3000:]
    links = sorted(set(H.unescape(u) for u in re.findall(r'href="(' + re.escape(P) + r'/[^"#]+)"', rep)))
    for u in links:                       # every report link opens (existing export routes)
        rr = c.get(u)
        assert rr.status_code == 200, (u, rr.status_code)
    summ = c.get(P + '/reports/summary').text
    assert 'Project summary report' in summ and 'DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.' in summ and '12 mm' in summ and 'Total estimate' in summ
    assert 'class="cv-cb-tab on" href="' + P + '/more"' in rep          # v3.8: Reports is inside More

    # outsider: no access, not listed
    o = TestClient(app)
    o.post('/register', data={'name': 'Out', 'username': 'report_out', 'password': 'report-password-1', 'remember': '', 'csrf_token': tok(o.get('/register').text)})
    assert o.get(P + '/reports').status_code == 404 and o.get(P + '/reports/summary').status_code == 404
    assert P not in o.get('/reports').text
    assert TestClient(app).get('/reports', follow_redirects=False).status_code in (303, 307, 401)

    # Tamil interface
    st = c.get('/settings').text
    assert c.post('/settings', data={'csrf_token': tok(st), 'mode': 'guided', 'lang': 'ta'}, follow_redirects=False).status_code == 303
    home = c.get('/').text
    assert '<html lang="ta">' in home and 'முகப்பு' in home and 'உங்கள் கட்டிடம் எவ்வளவு பெரியது?' in home
    assert tok(home)                      # forms still carry their CSRF token
    boq = c.get(P + '/boq').text
    assert 'மொத்தத் தொகை' in boq and 'சிமெண்ட் (Cement)' in boq, boq[-2000:]
    rep_ta = c.get(P + '/reports').text
    assert 'திட்ட அறிக்கைகள்' in rep_ta and '5-ல் 5' in rep_ta
    assert 'DESIGN INCOMPLETE' in c.get(P + '/reports/summary').text
    # saving still works in Tamil mode (form fields are untouched)
    b = c.get(P + '/bbs').text
    assert c.post(action(b, '/bbs/add'), data={'confirm': '1', 'csrf_token': tok(b), 'reference': 'C1-TIES', 'diameter': 8, 'count': 60, 'length': .9},
                  follow_redirects=False).status_code == 303
    c.post('/settings', data={'csrf_token': tok(c.get('/settings').text), 'mode': 'guided', 'lang': 'en'})
    assert '<html lang="en">' in c.get('/').text

    con = sqlite3.connect('data/buildquant.db')
    assert '3.3.0' in {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    con.close()
    print('V330 SMOKE OK')
''')

MISSING = [m for m in ('fastapi', 'httpx', 'passlib', 'itsdangerous', 'openpyxl', 'reportlab') if importlib.util.find_spec(m) is None]


@unittest.skipIf(MISSING, 'v3.3 smoke test skipped; missing: ' + ', '.join(MISSING))
class ReportsSmokeTest(unittest.TestCase):
    def test_reports_and_tamil_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in HERE.glob('*.py'):
                if not f.name.startswith('test_') and f.name != 'run_tests.py':
                    shutil.copy2(f, tmp / f.name)
            (tmp / '_v330_smoke.py').write_text(SMOKE, encoding='utf-8')
            r = subprocess.run([sys.executable, '_v330_smoke.py'], cwd=tmp, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
            self.assertIn('V330 SMOKE OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
