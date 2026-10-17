"""Civora AI v3.5 - Move my data between Civora installations (your PC -> the online app, or back).

  GET  /transfer                 page: export / import
  GET  /transfer/export.zip      download MY projects (the ones I own) + their drawings/files + my Rate Master
  POST /transfer/import          upload that zip into this installation, under my account (database backup first)

Rules
  * Only projects you OWN are exported. Shared projects stay with their owner.
  * Team members, invite links, activity and engineer sign-offs are NOT moved: user accounts differ between
    installations, so the team re-invites people and the engineer signs off again on the new site.
  * A project that already exists here (same id) is skipped, never overwritten.
  * The zip may only contain manifest.json and uploads/<file-id>.<ext>; anything else is refused.
"""
import io
import json
import re
import sqlite3
import time
import zipfile
from pathlib import Path

from ui_shell import esc, icon

FORMAT = 'civora-transfer'
VERSION = 1
SKIP_TABLES = {'civora_members_v270', 'civora_invites_v270', 'civora_activity_v270', 'civora_signoff_v270'}
MAX_ZIP = 300 * 1024 * 1024
MAX_FILES = 5000
FILE_RE = re.compile(r'^uploads/([0-9a-f-]{36})\.(png|jpg|jpeg|pdf|dxf|xlsx|csv)$')


def _cols(c, table):
    return [r[1] for r in c.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _project_tables(c):
    import data_v340
    return [t for t in data_v340.project_tables(c) if t not in SKIP_TABLES]


def export_zip(c, uid, files_dir):
    """Bytes of a zip with manifest.json + uploads/ for every project the user owns."""
    projects = [dict(r) for r in c.execute('SELECT * FROM projects WHERE owner_id=? ORDER BY created', (uid,)).fetchall()]
    ids = [p['id'] for p in projects]
    tables = {}
    if ids:
        q = ','.join('?' * len(ids))
        for t in _project_tables(c):
            rows = [dict(r) for r in c.execute(f'SELECT * FROM "{t}" WHERE project_id IN ({q})', ids).fetchall()]
            if rows:
                tables[t] = rows
    rates = []
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_rate_master_v260'").fetchone():
        rates = [{'key': r['key'], 'rate': r['rate']} for r in c.execute('SELECT key, rate FROM civora_rate_master_v260 WHERE user_id=?', (uid,)).fetchall()]
    manifest = {'format': FORMAT, 'version': VERSION, 'exported_at': int(time.time()), 'projects': projects, 'tables': tables, 'rates': rates}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
        for u in tables.get('uploads', []):
            stored = Path(str(u['stored_name'])).name
            src = Path(files_dir) / stored
            if stored == u['stored_name'] and FILE_RE.match('uploads/' + stored) and src.is_file():
                z.write(src, 'uploads/' + stored)
    return buf.getvalue(), len(projects)


def read_zip(data):
    """Validate and open an export. Returns (manifest, {stored_name: bytes}). Raises ValueError."""
    if len(data) > MAX_ZIP:
        raise ValueError('The file is larger than 300 MB.')
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError('This is not a Civora export (.zip).')
    names = z.namelist()
    if 'manifest.json' not in names or len(names) > MAX_FILES + 1:
        raise ValueError('This is not a Civora export: manifest.json is missing.')
    files = {}
    total = 0
    for n in names:
        if n == 'manifest.json' or n.endswith('/'):
            continue
        m = FILE_RE.match(n)
        if not m:
            raise ValueError(f'Unexpected file in the export: {n[:80]}')
        info = z.getinfo(n)
        total += info.file_size
        if total > 2 * MAX_ZIP:
            raise ValueError('The files inside are too large.')
        files[n.split('/', 1)[1]] = z.read(n)
    try:
        manifest = json.loads(z.read('manifest.json').decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        raise ValueError('manifest.json could not be read.')
    if manifest.get('format') != FORMAT or not isinstance(manifest.get('projects'), list) or not isinstance(manifest.get('tables', {}), dict):
        raise ValueError('This is not a Civora export.')
    return manifest, files


def import_data(c, uid, manifest, files, files_dir):
    """Insert the export under user `uid`. Returns a summary dict. Caller commits; files are written by the caller after commit."""
    have = {r[0] for r in c.execute('SELECT id FROM projects').fetchall()}
    proj_cols = set(_cols(c, 'projects'))
    added, skipped = [], []
    for p in manifest['projects']:
        pid = str(p.get('id', ''))
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', pid) or pid in have:
            skipped.append(str(p.get('name', pid))[:80]); continue
        row = {k: v for k, v in p.items() if k in proj_cols}
        row['owner_id'] = uid
        c.execute(f'INSERT INTO projects({",".join(row)}) VALUES({",".join("?" * len(row))})', list(row.values()))
        added.append(pid)
    keep = set(added)
    to_write = {}
    tables = manifest.get('tables', {})
    local = set(_project_tables(c))
    order = (['uploads'] if 'uploads' in tables else []) + [t for t in tables if t != 'uploads']
    pending = [t for t in order if t in local]
    counts = {}
    for _ in range(len(pending) + 1):          # retry order until foreign keys are satisfied
        left = []
        for t in pending:
            cols = set(_cols(c, t))
            try:
                c.execute('SAVEPOINT t')
                n = 0
                for r in tables[t]:
                    if r.get('project_id') not in keep:
                        continue
                    row = {k: v for k, v in r.items() if k in cols}
                    if t == 'uploads':
                        stored = Path(str(row.get('stored_name', ''))).name
                        if stored != row.get('stored_name') or not FILE_RE.match('uploads/' + stored) or not stored.startswith(str(row.get('id')) + '.'):
                            continue
                        if stored in files:
                            to_write[stored] = files[stored]
                    c.execute(f'INSERT OR IGNORE INTO "{t}"({",".join(row)}) VALUES({",".join("?" * len(row))})', list(row.values()))
                    n += 1
                c.execute('RELEASE t')
                counts[t] = n
            except sqlite3.IntegrityError:
                c.execute('ROLLBACK TO t'); c.execute('RELEASE t')
                left.append(t)
        pending = left
        if not pending:
            break
    if pending:
        raise ValueError('Some data could not be imported: ' + ', '.join(pending))
    rates = 0
    if manifest.get('rates') and c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_rate_master_v260'").fetchone():
        mine = {r[0] for r in c.execute('SELECT key FROM civora_rate_master_v260 WHERE user_id=? AND rate>0', (uid,)).fetchall()}
        for r in manifest['rates']:
            try:
                key, val = str(r['key'])[:40], float(r['rate'])
            except (KeyError, TypeError, ValueError):
                continue
            if key not in mine and val > 0:            # never overwrite rates already set here
                c.execute('INSERT INTO civora_rate_master_v260(user_id,key,rate,updated) VALUES(?,?,?,?) '
                          'ON CONFLICT(user_id,key) DO UPDATE SET rate=excluded.rate, updated=excluded.updated', (uid, key, val, int(time.time())))
                rates += 1
    return {'added': len(added), 'skipped': skipped, 'files': to_write, 'rows': counts, 'rates': rates}


def page_html(csrf_token, n_owned, message='', error=''):
    note = (f'<div class="cv-banner" style="margin-top:14px">{esc(message)}</div>' if message else '') + \
           (f'<div class="cv-banner" style="margin-top:14px;background:#fef2f2;border-color:#fecaca;color:#991b1b">{esc(error)}</div>' if error else '')
    return f'''<div class="cv-ph"><div><span class="eyebrow">MOVE MY DATA · தரவை மாற்று</span><h1>Move projects between Civora sites</h1>
<div class="meta">From your PC to the online Civora (or back): download here, upload there</div></div></div>{note}
<div class="rc-grid">
<section class="cv-card"><h3>{icon("download", 18)} 1. Download my data</h3>
<p>One .zip with the <b>{n_owned}</b> project(s) you own: drawings and files, estimates (BOQ revisions), structural elements, bars,
takeoffs, measurements and design inputs — plus your Rate Master.</p>
<p class="hint">Shared projects stay with their owner. Team members and engineer sign-offs are not included: invite the team again on the new site.</p>
<a class="cv-btn" href="/transfer/export.zip">{icon("download", 16)} Download my data (.zip)</a></section>
<section class="cv-card"><h3>{icon("upload", 18)} 2. Upload into this site</h3>
<p>Choose the .zip you downloaded from the other Civora. The projects are added to <b>your account here</b>.</p>
<form method="post" action="/transfer/import" enctype="multipart/form-data" class="dt-upf" onsubmit="return confirm('Add the projects from this file to your account here? A database backup is made first.')">
<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><input type="file" name="file" accept=".zip" required aria-label="Civora export file">
<button class="cv-btn">{icon("upload", 16)} Upload &amp; add</button></form>
<p class="hint">Projects that already exist here are skipped, never overwritten. Rates you already set here are kept.</p></section></div>'''


def register_transfer_v350(app, db, require, csrf, check_csrf, layout, files_dir):
    from fastapi import Request, HTTPException
    from fastapi.responses import Response

    def owned_count(uid):
        with db() as c:
            return c.execute('SELECT count(*) FROM projects WHERE owner_id=?', (uid,)).fetchone()[0]

    @app.get('/transfer')
    def transfer_page(request: Request):
        u = require(request)
        q = request.query_params
        msg = ''
        if q.get('added') is not None:
            msg = f'Added {q.get("added")} project(s)' + (f'; {q.get("skipped")} already here and skipped' if q.get('skipped', '0') != '0' else '') + '.'
        return layout(request, 'Move my data', page_html(csrf(request), owned_count(u['id']), msg))

    @app.get('/transfer/export.zip')
    def transfer_export(request: Request):
        u = require(request)
        with db() as c:
            data, n = export_zip(c, u['id'], files_dir)
        name = f'Civora_my_data_{time.strftime("%Y%m%d_%H%M")}.zip'
        return Response(data, media_type='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="{name}"', 'Cache-Control': 'private, no-store'})

    @app.post('/transfer/import')
    async def transfer_import(request: Request):
        from fastapi.responses import RedirectResponse
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        up = form.get('file')
        if up is None or not hasattr(up, 'read'):
            raise HTTPException(400, 'Choose the Civora export (.zip) file.')
        data = await up.read(MAX_ZIP + 1)
        try:
            manifest, files = read_zip(data)
        except ValueError as ex:
            return layout(request, 'Move my data', page_html(csrf(request), owned_count(u['id']), error=str(ex)))
        import data_safety
        try:
            data_safety.backup_database(reason='before-import')
        except Exception:
            raise HTTPException(500, 'Could not make a database backup, so nothing was imported.')
        try:
            with db() as c:
                res = import_data(c, u['id'], manifest, files, files_dir)
        except ValueError as ex:
            return layout(request, 'Move my data', page_html(csrf(request), owned_count(u['id']), error=str(ex) + ' Nothing was imported.'))
        Path(files_dir).mkdir(parents=True, exist_ok=True)
        for stored, blob in res['files'].items():
            dest = Path(files_dir) / stored
            if not dest.exists():
                import filestore; filestore.save(files_dir, stored, blob)
        return RedirectResponse(f'/transfer?added={res["added"]}&skipped={len(res["skipped"])}', 303)
