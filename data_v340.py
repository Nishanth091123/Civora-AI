"""Civora AI v3.4 - Project data: see everything stored, upload more, delete what you don't need.

  GET  /projects/{pid}/data                       every stored item in the project, with Upload and Delete
  POST /projects/{pid}/data/files/{fid}/delete    delete a drawing / file + estimates and measurements made from it (owner)
  POST /projects/{pid}/data/estimates/{bid}/delete delete one saved estimate (BOQ revision) (owner / engineer / colleague)
  POST /projects/{pid}/data/delete-project        delete the WHOLE project (owner; type the name; database backup first)
  POST /rates/clear                               clear all my Rate Master rates

Other items (structural elements, bars, takeoffs, measurements, drawing measurements) are deleted through their
EXISTING routes with ?return= back to this page. Every delete is a POST with CSRF, the project role check, and a
confirm() prompt in the browser. Nothing is deleted on a GET.
"""
import json
import os
import time
from pathlib import Path

from ui_shell import esc, icon, inr_short
import workflow_v250 as wf

KB = 1024


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _size(n):
    n = float(n or 0)
    return f'{n / KB / KB:,.1f} MB' if n >= KB * KB else f'{n / KB:,.0f} KB' if n >= KB else f'{n:,.0f} B'


def _date(ts):
    try:
        return time.strftime('%d %b %Y, %H:%M', time.localtime(int(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return ''


def _has(c, table):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _rows(c, table, sql, args):
    return c.execute(sql, args).fetchall() if _has(c, table) else []


def project_tables(c):
    """Every table that stores rows per project (has a project_id column), except projects itself."""
    out = []
    for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        if name == 'projects':
            continue
        cols = {r[1] for r in c.execute(f'PRAGMA table_info("{name}")').fetchall()}
        if 'project_id' in cols:
            out.append(name)
    return out


def estimate_source(data):
    data = data or {}
    if data.get('source_detail') == 'quick_v280' or data.get('source') == 'quick_v280':
        return 'Quick Estimate'
    return {'smart_estimate_v260': 'Smart Estimate', 'multi_drawing_v360': 'Multi-drawing estimate'}.get(data.get('source'), 'Drawing BOQ')


def collect(c, pid, files_dir):
    """Everything stored for one project, for the data page."""
    d = {}
    ups = _rows(c, 'uploads', 'SELECT * FROM uploads WHERE project_id=? ORDER BY created DESC', (pid,))
    boqs = _rows(c, 'civora_boq_reports', 'SELECT id, drawing_id, payload, created FROM civora_boq_reports WHERE project_id=? ORDER BY created DESC, rowid DESC', (pid,))
    est = []
    for b in boqs:
        try:
            data = json.loads(b['payload'])
        except (TypeError, ValueError):
            data = {}
        cost = wf.boq_cost(data)
        est.append({'id': b['id'], 'drawing_id': b['drawing_id'], 'created': b['created'], 'source': estimate_source(data),
                    'lines': sum(len(r.get('items', [])) for r in data.get('rows', [])),
                    'total': cost['material'] + cost['labour'] + cost['transport'] + cost['other'] + cost['tax']})
    by_drawing = {}
    for e in est:
        by_drawing[e['drawing_id']] = by_drawing.get(e['drawing_id'], 0) + 1
    files = []
    for u in ups:
        try:
            size = (Path(files_dir) / Path(u['stored_name']).name).stat().st_size
        except OSError:
            size = 0
        files.append({'id': u['id'], 'name': u['original_name'], 'created': u['created'], 'size': size, 'estimates': by_drawing.get(u['id'], 0)})
    d['files'] = files
    d['estimates'] = est
    d['structural'] = _rows(c, 'civora_structural_v210', 'SELECT id, kind, reference, created FROM civora_structural_v210 WHERE project_id=? ORDER BY created', (pid,))
    d['bars'] = _rows(c, 'civora_bbs_v210', 'SELECT id, reference, payload, created FROM civora_bbs_v210 WHERE project_id=? ORDER BY created', (pid,))
    d['takeoffs'] = _rows(c, 'material_takeoffs', 'SELECT id, work_key, created FROM material_takeoffs WHERE project_id=? ORDER BY created DESC', (pid,))
    d['measurements'] = _rows(c, 'material_estimates', 'SELECT * FROM material_estimates WHERE project_id=?', (pid,))
    d['drawing_measurements'] = _rows(c, 'drawing_measurements', 'SELECT id, upload_id, work FROM drawing_measurements WHERE project_id=?', (pid,))
    d['members'] = len(_rows(c, 'civora_members_v270', 'SELECT user_id FROM civora_members_v270 WHERE project_id=?', (pid,)))
    return d


# ------------------------------------------------------------------ small ✕ delete button used next to saved items on every screen
def x_form(action, csrf_token, confirm_text, label):
    return (f'<form method="post" action="{esc(action)}" class="dt-x-f" onsubmit="return confirm({esc(json.dumps(confirm_text))})">'
            f'<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><button class="dt-x" title="{esc(label)}" aria-label="{esc(label)}">&#10005;</button></form>')


# ------------------------------------------------------------------ page
def _del_form(action, csrf_token, confirm_text, label='Delete', small=True):
    return (f'<form method="post" action="{esc(action)}" class="dt-del" onsubmit="return confirm({esc(json.dumps(confirm_text))})">'
            f'<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><button class="cv-btn {"sm " if small else ""}dt-danger" '
            f'aria-label="{esc(label)}">{esc(label)}</button></form>')


def _backup_note():
    import dbcompat
    if dbcompat.is_postgres():
        return 'There is no undo here – your PostgreSQL provider (Neon / Supabase) keeps a short restore history if this was a mistake.'
    return 'A database backup is made first (in <code>backups\\db</code>), so it can be restored with <code>restore.bat</code> if this was a mistake.'


def data_page_html(project, d, csrf_token, role):
    BACKUP_NOTE = _backup_note()
    import team_v270
    pid = project['id']
    P = f'/projects/{pid}'
    back = P + '/data'
    can_edit = team_v270.allowed(role, 'edit')
    can_manage = team_v270.allowed(role, 'manage')
    can_design = team_v270.allowed(role, 'design')
    r = lambda url: url + ('&' if '?' in url else '?') + 'return=' + back
    total_size = sum(f['size'] for f in d['files'])
    counts = [('Drawings & files', len(d['files']), _size(total_size)), ('Saved estimates', len(d['estimates']), 'BOQ revisions'),
              ('Structural elements', len(d['structural']), f'{len(d["bars"])} bar marks'),
              ('Takeoffs & measurements', len(d['takeoffs']) + len(d['measurements']) + len(d['drawing_measurements']), 'manual calculations')]
    head = (f'<div class="cv-ph"><div><span class="eyebrow">PROJECT DATA · திட்டத் தரவு</span><h1>Stored data</h1>'
            f'<div class="meta">{esc(project["name"])} · everything saved in this project — upload more or delete what you don’t need</div></div></div>'
            '<div class="cc-kpis rc-k4">' + ''.join(f'<div class="cc-kpi"><small>{esc(a)}</small><b>{b}</b><em>{esc(c)}</em></div>' for a, b, c in counts) + '</div>')
    out = [head]
    if not can_edit:
        out.append('<div class="cv-banner" style="margin-top:14px">You can view this project. Only the project team can upload or delete.</div>')
    # upload stays available
    if can_edit:
        out.append(f'''<section class="cv-card dt-up"><h3>{icon("upload", 18)} Upload a drawing or file</h3>
<form method="post" action="{esc(P + '/upload?return=' + back)}" enctype="multipart/form-data" class="dt-upf">
<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><input type="hidden" name="next" value="data">
<input type="file" name="file" required accept=".pdf,.dxf,.png,.jpg,.jpeg,.xlsx,.csv" aria-label="Choose file">
<button class="cv-btn sm">{icon("upload", 15)}Upload</button></form>
<p class="hint">PDF, DXF (CAD), PNG, JPG, Excel or CSV · up to 30 MB. To get an estimate from a drawing, use Smart Estimate.</p></section>''')

    def section(title, ta, body, n):
        return (f'<section class="cv-card dt-sec"><div class="dt-sh"><h3>{esc(title)} <span class="ta">{esc(ta)}</span></h3><span class="sub">{n} saved</span></div>'
                + (body if n else '<p class="sub">Nothing saved.</p>') + '</section>')

    # 1. files
    rows = ''
    for f in d['files']:
        extra = f' and its {f["estimates"]} estimate(s)' if f['estimates'] else ''
        act = _del_form(f'{P}/data/files/{f["id"]}/delete', csrf_token,
                        f'Delete "{f["name"]}"{extra}? This cannot be undone.') if can_manage else ''
        rows += (f'<tr><td><b>{esc(f["name"])}</b><small class="rc-s">{_date(f["created"])}</small></td><td class="r">{_size(f["size"])}</td>'
                 f'<td>{(str(f["estimates"]) + " estimate(s) made from it") if f["estimates"] else "—"}</td><td class="r">{act}</td></tr>')
    body = (f'<table class="cv-mt"><tr><th>File</th><th class="r">Size</th><th>Used by</th><th></th></tr>{rows}</table>'
            + ('<p class="hint">Deleting a drawing also deletes the estimates and measurements made from it. Only the project owner can delete files.</p>'))
    out.append(section('Drawings & files', 'வரைபடங்கள் & கோப்புகள்', body, len(d['files'])))
    # 2. estimates
    rows = ''
    for i, e in enumerate(d['estimates']):
        act = _del_form(f'{P}/data/estimates/{e["id"]}/delete', csrf_token, f'Delete this {e["source"]} saved on {_date(e["created"])}? This cannot be undone.') if can_edit else ''
        rows += (f'<tr><td><b>{esc(e["source"])}</b>{" <span class=\'cv-status st-checked\'>Latest</span>" if i == 0 else ""}<small class="rc-s">{_date(e["created"])}</small></td>'
                 f'<td class="r">{e["lines"]}</td><td class="r">{inr_short(e["total"]) if e["total"] else "not priced"}</td><td class="r">{act}</td></tr>')
    body = (f'<table class="cv-mt"><tr><th>Estimate</th><th class="r">Lines</th><th class="r">Total</th><th></th></tr>{rows}</table>'
            '<p class="hint">The newest estimate is the one used in Cost &amp; BOQ and Reports. Delete it and the previous one becomes current.</p>')
    out.append(section('Saved estimates (Quick, Smart, Drawing BOQ)', 'சேமித்த மதிப்பீடுகள்', body, len(d['estimates'])))
    # 3. structural + bars (existing delete routes)
    import structural_v210 as sv
    rows = ''
    for s in d['structural']:
        act = _del_form(r(f'{P}/structural/advanced/{s["id"]}/delete'), csrf_token, f'Delete element {s["reference"]}?') if can_edit else ''
        rows += f'<tr><td><b>{esc(s["reference"])}</b></td><td>{esc(sv.ELEMENTS.get(s["kind"], (s["kind"],))[0])}</td><td class="r">{act}</td></tr>'
    out.append(section('Structural elements', 'கட்டமைப்பு உறுப்புகள்', f'<table class="cv-mt"><tr><th>Mark</th><th>Element</th><th></th></tr>{rows}</table>', len(d['structural'])))
    rows = ''
    for b in d['bars']:
        try:
            dia = json.loads(b['payload']).get('diameter_mm', '')
        except (TypeError, ValueError):
            dia = ''
        act = _del_form(r(f'{P}/structural/advanced/bbs/{b["id"]}/delete'), csrf_token, f'Delete bar {b["reference"]}?') if can_edit else ''
        rows += f'<tr><td><b>{esc(b["reference"])}</b></td><td>{esc(str(dia))} mm</td><td class="r">{act}</td></tr>'
    out.append(section('Bar bending schedule (BBS)', 'கம்பி அட்டவணை', f'<table class="cv-mt"><tr><th>Bar mark</th><th>Diameter</th><th></th></tr>{rows}</table>', len(d['bars'])))
    # 4. manual calculations
    rows = ''
    for t in d['takeoffs']:
        act = _del_form(r(f'{P}/takeoff/{t["id"]}/delete'), csrf_token, 'Delete this saved material takeoff?') if can_edit else ''
        rows += f'<tr><td>Material takeoff · <b>{esc(t["work_key"])}</b><small class="rc-s">{_date(t["created"])}</small></td><td class="r">{act}</td></tr>'
    for m in d['measurements']:
        act = _del_form(r(f'{P}/materials/{m["id"]}/delete'), csrf_token, 'Delete this saved measurement?') if can_edit else ''
        rows += f'<tr><td>Measurement · <b>{esc(m["work_type"])}</b> {_f(m["length_m"]):g} × {_f(m["height_m"]):g} × {_f(m["thickness_m"]):g} m</td><td class="r">{act}</td></tr>'
    for m in d['drawing_measurements']:
        act = _del_form(r(f'{P}/drawings/saved/{m["id"]}/delete'), csrf_token, 'Delete this drawing measurement?') if can_edit else ''
        rows += f'<tr><td>Drawing measurement · <b>{esc(m["work"])}</b></td><td class="r">{act}</td></tr>'
    n = len(d['takeoffs']) + len(d['measurements']) + len(d['drawing_measurements'])
    out.append(section('Takeoffs & measurements', 'கணக்கீடுகள் & அளவுகள்', f'<table class="cv-mt"><tr><th>Item</th><th></th></tr>{rows}</table>', n))
    # 5. danger zone
    if can_manage:
        out.append(f'''<section class="cv-card dt-zone" id="delete"><h3>{icon("shield", 18)} Delete this whole project</h3>
<p>Deletes <b>{esc(project["name"])}</b> with all its drawings, estimates, structural data, bars, takeoffs, team members ({d["members"]}) and activity.
{BACKUP_NOTE}</p>
<form method="post" action="{esc(P + '/data/delete-project')}" class="dt-upf" onsubmit="return confirm('Delete the whole project? A backup is made first.')">
<input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
<label class="dt-lab">Type the project name to confirm<input name="confirm_name" autocomplete="off" required placeholder="{esc(project["name"])}"></label>
<button class="cv-btn dt-danger">Delete project</button></form></section>''')
    return ''.join(out)


# ------------------------------------------------------------------ deletes
def delete_estimates(c, pid, ids):
    n = 0
    for bid in ids:
        n += c.execute('DELETE FROM civora_boq_reports WHERE id=? AND project_id=?', (bid, pid)).rowcount
    return n


def delete_file(c, pid, fid, files_dir):
    """Delete one upload and everything made from it. Returns the stored path to unlink after commit (or None)."""
    row = c.execute('SELECT stored_name FROM uploads WHERE id=? AND project_id=?', (fid, pid)).fetchone()
    if not row:
        return None
    stored = Path(row['stored_name']).name
    if stored != row['stored_name'] or not stored.startswith(fid + '.'):
        raise ValueError('Unsafe stored filename; deletion refused')
    if _has(c, 'civora_boq_reports'):
        c.execute('DELETE FROM civora_boq_reports WHERE project_id=? AND drawing_id=?', (pid, fid))
    if _has(c, 'drawing_measurements'):
        c.execute('DELETE FROM drawing_measurements WHERE project_id=? AND upload_id=?', (pid, fid))
    c.execute('DELETE FROM uploads WHERE id=? AND project_id=?', (fid, pid))
    return Path(files_dir) / stored


def delete_project(c, pid, files_dir):
    """Delete every row of the project in every table, children first. Returns file paths to unlink after commit."""
    paths = []
    for u in _rows(c, 'uploads', 'SELECT id, stored_name FROM uploads WHERE project_id=?', (pid,)):
        stored = Path(u['stored_name']).name
        if stored == u['stored_name'] and stored.startswith(u['id'] + '.'):
            paths.append(Path(files_dir) / stored)
    tables = [t for t in project_tables(c) if t != 'uploads'] + (['uploads'] if _has(c, 'uploads') else [])
    import sqlite3
    pending = list(tables)
    for _ in range(len(tables) + 1):          # retry order until foreign keys are satisfied
        left = []
        for t in pending:
            try:
                c.execute(f'DELETE FROM "{t}" WHERE project_id=?', (pid,))
            except sqlite3.IntegrityError:
                left.append(t)
        pending = left
        if not pending:
            break
    if pending:
        raise RuntimeError('Could not delete rows in: ' + ', '.join(pending))
    c.execute('DELETE FROM projects WHERE id=?', (pid,))
    return paths


# ------------------------------------------------------------------ routes
def register_data_v340(app, db, owned_project, require, csrf, check_csrf, layout, files_dir):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    import team_v270

    def need(request, perm):
        role = getattr(request.state, 'cv_role', 'owner')
        if not team_v270.allowed(role, perm):
            raise HTTPException(403, f'Only {team_v270.NEED_LABEL.get(perm, "the project team")} can do this.')

    @app.get('/projects/{pid}/data')
    def project_data(request: Request, pid: str):
        p = owned_project(request, pid)
        with db() as c:
            d = collect(c, pid, files_dir)
        return layout(request, f'{p["name"]} · Data', data_page_html(p, d, csrf(request), getattr(request.state, 'cv_role', 'owner')))

    @app.post('/projects/{pid}/data/estimates/{bid}/delete')
    async def delete_estimate(request: Request, pid: str, bid: str):
        owned_project(request, pid)
        need(request, 'edit')
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            if not _has(c, 'civora_boq_reports') or not delete_estimates(c, pid, [bid]):
                raise HTTPException(404, 'Saved estimate not found')
        nxt = str(form.get('next') or '')
        return RedirectResponse(nxt if nxt.startswith(f'/projects/{pid}/') else f'/projects/{pid}/data', 303)

    @app.post('/projects/{pid}/data/files/{fid}/delete')
    async def delete_upload(request: Request, pid: str, fid: str):
        owned_project(request, pid)
        need(request, 'manage')
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            try:
                path = delete_file(c, pid, fid, files_dir)
            except ValueError as ex:
                raise HTTPException(400, str(ex))
            if path is None:
                raise HTTPException(404, 'File not found')
        import filestore; filestore.delete(files_dir, path.name)   # the file goes only after the database change is committed
        return RedirectResponse(f'/projects/{pid}/data', 303)

    @app.post('/projects/{pid}/data/delete-project')
    async def remove_project(request: Request, pid: str):
        p = owned_project(request, pid)
        need(request, 'manage')
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        if ' '.join(str(form.get('confirm_name', '')).split()).casefold() != ' '.join(str(p['name']).split()).casefold():
            raise HTTPException(400, 'The project name you typed does not match. Nothing was deleted.')
        import data_safety
        try:
            data_safety.backup_database(reason='before-project-delete')
        except Exception:
            raise HTTPException(500, 'Could not make a database backup, so nothing was deleted.')
        with db() as c:
            paths = delete_project(c, pid, files_dir)
        import filestore
        for path in paths:
            filestore.delete(files_dir, path.name)
        request.state.cv_actor = None            # nothing left to log against
        return RedirectResponse('/projects?deleted=1', 303)

    @app.post('/rates/clear')
    async def clear_rates(request: Request):
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            if _has(c, 'civora_rate_master_v260'):
                c.execute('DELETE FROM civora_rate_master_v260 WHERE user_id=?', (u['id'],))
        return RedirectResponse('/rates?cleared=1', 303)
