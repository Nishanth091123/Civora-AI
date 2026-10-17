"""Civora AI v3.6.0 - keep data safe on cloud hosting (Render free plan etc.).

WHY DATA DISAPPEARED
  Render's free plan has no permanent disk. Every restart, sleep or redeploy starts a
  fresh container, so data/buildquant.db (users, logins, projects, BOQs), data/uploads
  and data/session.key were all wiped.

WHAT THIS MODULE DOES (choose one, both can be on):
  1. Persistent disk  - set CIVORA_DATA_DIR to the mounted disk folder (Render paid disk,
                        Railway volume, VPS folder). Everything lives there.
  2. Cloud backup     - set CIVORA_BACKUP_REPO (e.g. "Nishanth091123/civora-data", a PRIVATE
                        GitHub repo) and CIVORA_BACKUP_TOKEN (fine-grained token with
                        Contents: Read and write on that repo only). Then:
                          * on start-up, if the database is missing/empty, the latest
                            snapshot is downloaded and restored (users, projects, files);
                          * every ~30 s, if anything changed, a consistent snapshot
                            (database + session key + uploads) is saved to the repo;
                          * a last snapshot is saved when the server shuts down.
                        Every save is a git commit, so older versions can be recovered.
  CIVORA_SECRET_KEY (optional) keeps sign-ins valid across restarts even without backup.

On a normal PC (no RENDER env var) nothing changes: data stays in C:\\Civora_AI\\data.
Only the Python standard library is used.
"""
import base64
import hashlib
import io
import json
import os
import secrets
import sqlite3
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_NAME = 'buildquant.db'
SNAPSHOT_PATH = 'civora_backup/latest.tar.gz'
API = 'https://api.github.com'

STATUS = {
    'mode': 'local', 'data_dir': '', 'backup_repo': '', 'restored': '', 'restore_error': '',
    'last_backup_at': 0, 'last_backup_size': 0, 'last_error': '', 'skipped_uploads': 0,
    'uploads_blocked': False, 'started_at': 0,
}
_lock = threading.Lock()
_state = {'fingerprint': None, 'sha': None, 'thread': None, 'stop': None}


# ------------------------------------------------------------------ configuration
def _env(name, default=''):
    return (os.environ.get(name) or default).strip()


def data_dir():
    d = _env('CIVORA_DATA_DIR')
    return Path(d).expanduser() if d else BASE / 'data'


def backup_config():
    try:
        import dbcompat
        if dbcompat.is_postgres():
            return None          # PostgreSQL keeps the data itself; no file backup needed
    except ImportError:
        pass
    repo, token = _env('CIVORA_BACKUP_REPO'), _env('CIVORA_BACKUP_TOKEN')
    if not repo or not token or repo.count('/') != 1:
        return None
    return {'repo': repo, 'token': token, 'branch': _env('CIVORA_BACKUP_BRANCH', 'main'),
            'interval': max(int(_env('CIVORA_BACKUP_INTERVAL', '30') or 30), 10),
            'uploads_mb': max(float(_env('CIVORA_BACKUP_UPLOADS_MB', '25') or 25), 0)}


def on_cloud_host():
    return any(os.environ.get(k) for k in ('RENDER', 'RENDER_SERVICE_ID', 'RAILWAY_ENVIRONMENT', 'SPACE_ID', 'DYNO'))


def storage_mode():
    try:
        import dbcompat
        if dbcompat.is_postgres():
            return 'postgres'
    except ImportError:
        pass
    if backup_config():
        return 'cloud-backup' if not _env('CIVORA_DATA_DIR') else 'disk+cloud-backup'
    if _env('CIVORA_DATA_DIR'):
        return 'disk'
    return 'temporary' if on_cloud_host() else 'local'


def is_safe():
    """False only when data will be lost on restart (cloud host, no disk, no working backup)."""
    m = STATUS.get('mode') or storage_mode()
    if m == 'temporary':
        return False
    if 'cloud-backup' in m and (STATUS.get('restore_error') or STATUS.get('uploads_blocked')):
        return False
    return True


def secret_key(key_file):
    """Stable session key: env CIVORA_SECRET_KEY, else data/session.key (restored with the backup)."""
    env = _env('CIVORA_SECRET_KEY')
    if env:
        return env
    import dbcompat
    if dbcompat.is_postgres():           # kept in the database so sign-ins survive restarts
        with dbcompat.pg_session() as c:
            key = dbcompat.kv_get(c, 'session_key')
            if not key:
                dbcompat.kv_set(c, 'session_key', secrets.token_urlsafe(48))
        with dbcompat.pg_session() as c:
            return dbcompat.kv_get(c, 'session_key')
    key_file = Path(key_file)
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(48), encoding='utf-8')
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    return key_file.read_text(encoding='utf-8').strip()


# ------------------------------------------------------------------ GitHub contents API
def _request(cfg, method, path, body=None, accept='application/vnd.github+json', timeout=60):
    api = (os.environ.get('CIVORA_BACKUP_API') or API).rstrip('/')      # override only for tests / GitHub Enterprise
    req = urllib.request.Request(f'{api}/repos/{cfg["repo"]}/contents/{path}' + (f'?ref={cfg["branch"]}' if method == 'GET' else ''),
                                 data=json.dumps(body).encode() if body is not None else None, method=method)
    req.add_header('Authorization', f'Bearer {cfg["token"]}')
    req.add_header('Accept', accept)
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    req.add_header('User-Agent', 'civora-ai-backup')
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def remote_sha(cfg):
    try:
        meta = json.loads(_request(cfg, 'GET', SNAPSHOT_PATH, accept='application/vnd.github.object+json'))
        return meta.get('sha')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def download_snapshot(cfg):
    """Latest snapshot bytes, or None when no backup exists yet."""
    try:
        return _request(cfg, 'GET', SNAPSHOT_PATH, accept='application/vnd.github.raw+json', timeout=180)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def upload_snapshot(cfg, blob, note=''):
    sha = _state['sha'] or remote_sha(cfg)
    body = {'message': f'Civora data backup {time.strftime("%Y-%m-%d %H:%M:%S")} {note}'.strip(),
            'content': base64.b64encode(blob).decode(), 'branch': cfg['branch']}
    if sha:
        body['sha'] = sha
    try:
        out = json.loads(_request(cfg, 'PUT', SNAPSHOT_PATH, body, timeout=300))
    except urllib.error.HTTPError as e:
        if e.code in (409, 422) and sha:          # sha moved (another instance) - refresh once
            body['sha'] = remote_sha(cfg)
            out = json.loads(_request(cfg, 'PUT', SNAPSHOT_PATH, body, timeout=300))
        else:
            raise
    _state['sha'] = (out.get('content') or {}).get('sha')


# ------------------------------------------------------------------ snapshot build / restore
def _count(db, table):
    if not Path(db).is_file():
        return 0
    try:
        conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        try:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                return 0
            return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def db_is_empty(db):
    return _count(db, 'users') == 0 and _count(db, 'projects') == 0


def build_snapshot(data, uploads_budget_mb=25):
    """tar.gz bytes: consistent DB copy + session.key + uploads (newest first, within budget)."""
    data = Path(data)
    db = data / DB_NAME
    buf = io.BytesIO()
    skipped = 0
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / DB_NAME
        src = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        out = sqlite3.connect(copy)
        try:
            src.backup(out)
        finally:
            out.close(); src.close()
        manifest = {'made': int(time.time()), 'users': _count(copy, 'users'), 'projects': _count(copy, 'projects'),
                    'files': [], 'skipped_files': []}
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            tar.add(copy, arcname=DB_NAME)
            key = data / 'session.key'
            if key.is_file():
                tar.add(key, arcname='session.key')
            budget = uploads_budget_mb * 1024 * 1024
            files = sorted((p for p in (data / 'uploads').glob('*') if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
            for p in files:
                size = p.stat().st_size
                if size <= budget:
                    tar.add(p, arcname=f'uploads/{p.name}')
                    budget -= size
                    manifest['files'].append(p.name)
                else:
                    skipped += 1
                    manifest['skipped_files'].append(p.name)
            raw = json.dumps(manifest).encode()
            info = tarfile.TarInfo('manifest.json'); info.size = len(raw); info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(raw))
    return buf.getvalue(), manifest, skipped


def restore_snapshot(blob, data):
    """Extract a snapshot into the data folder. Only known, safe names are written."""
    data = Path(data)
    (data / 'uploads').mkdir(parents=True, exist_ok=True)
    manifest = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as tar:
        members = tar.getmembers()
        names = {m.name for m in members}
        if DB_NAME not in names:
            raise ValueError('Backup has no database')
        for m in members:
            if not m.isfile():
                continue
            name = m.name
            if name in (DB_NAME, 'session.key', 'manifest.json'):
                dest = data / name
            elif name.startswith('uploads/') and name.count('/') == 1 and name[8:] and '..' not in name and '\\' not in name:
                dest = data / 'uploads' / Path(name[8:]).name
            else:
                continue
            content = tar.extractfile(m).read()
            if name == 'manifest.json':
                manifest = json.loads(content or b'{}')
                continue
            tmp = dest.with_suffix(dest.suffix + '.restoring')
            tmp.write_bytes(content)
            os.replace(tmp, dest)
    db = data / DB_NAME
    conn = sqlite3.connect(db)
    try:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Restored database failed the integrity check')
    finally:
        conn.close()
    return manifest


def fingerprint(data):
    data = Path(data)
    h = hashlib.sha256()
    for p in [data / DB_NAME, data / (DB_NAME + '-wal'), data / 'session.key']:
        if p.is_file():
            st = p.stat(); h.update(f'{p.name}:{st.st_size}:{st.st_mtime_ns};'.encode())
    up = data / 'uploads'
    if up.is_dir():
        for p in sorted(up.iterdir()):
            if p.is_file():
                st = p.stat(); h.update(f'u/{p.name}:{st.st_size};'.encode())
    return h.hexdigest()


# ------------------------------------------------------------------ lifecycle
def prepare():
    """Call FIRST in app.py, before the database is opened. Returns the data folder."""
    data = data_dir()
    data.mkdir(parents=True, exist_ok=True)
    (data / 'uploads').mkdir(exist_ok=True)
    STATUS.update(mode=storage_mode(), data_dir=str(data), started_at=int(time.time()))
    cfg = backup_config()
    if cfg:
        STATUS['backup_repo'] = cfg['repo']
        db = data / DB_NAME
        if not db.is_file() or db_is_empty(db):
            try:
                blob = download_snapshot(cfg)
                if blob:
                    m = restore_snapshot(blob, data)
                    STATUS['restored'] = (f'Restored {m.get("users", "?")} user(s), {m.get("projects", "?")} project(s) '
                                          f'and {len(m.get("files", []))} file(s) from the backup of '
                                          f'{time.strftime("%d %b %Y %H:%M", time.localtime(m.get("made", 0)))}')
                    print('[Civora] ' + STATUS['restored'], flush=True)
                else:
                    STATUS['restored'] = 'No backup yet - starting fresh. The first backup is made after the first change.'
            except Exception as ex:   # never start overwriting a good backup with an empty database
                STATUS['restore_error'] = f'Could not restore the backup ({type(ex).__name__}: {str(ex)[:160]}). Backups are paused so nothing is overwritten.'
                STATUS['uploads_blocked'] = True
                print('[Civora] ' + STATUS['restore_error'], flush=True)
        # restored state is already in the backup; an existing local database is uploaded on the first check
        _state['fingerprint'] = fingerprint(data) if STATUS['restored'].startswith('Restored') else None
    elif STATUS['mode'] == 'temporary':
        print('[Civora] WARNING: running on a cloud host WITHOUT a persistent disk or backup. '
              'All data will be lost on restart. Set CIVORA_BACKUP_REPO + CIVORA_BACKUP_TOKEN (see README).', flush=True)
    return data


def backup_now(data=None, force=False, note=''):
    """Save a snapshot if something changed (or force). Returns a short message."""
    cfg = backup_config()
    if not cfg:
        return 'Cloud backup is not set up.'
    data = Path(data or STATUS.get('data_dir') or data_dir())
    with _lock:
        if STATUS['uploads_blocked']:
            return STATUS['restore_error'] or 'Backups are paused.'
        if not (data / DB_NAME).is_file():
            return 'No database yet.'
        fp = fingerprint(data)
        if not force and fp == _state['fingerprint']:
            return 'No changes since the last backup.'
        try:
            blob, manifest, skipped = build_snapshot(data, cfg['uploads_mb'])
            if manifest['users'] == 0 and manifest['projects'] == 0 and (_state['sha'] or remote_sha(cfg)):
                _state['fingerprint'] = fp
                return 'Empty database - existing backup kept.'
            upload_snapshot(cfg, blob, note)
            _state['fingerprint'] = fp
            STATUS.update(last_backup_at=int(time.time()), last_backup_size=len(blob), last_error='', skipped_uploads=skipped)
            return f'Backed up ({len(blob) / 1024:,.0f} KB).'
        except Exception as ex:
            STATUS['last_error'] = f'{type(ex).__name__}: {str(ex)[:200]}'
            return 'Backup failed: ' + STATUS['last_error']


def _loop(data, stop, interval):
    while not stop.wait(interval):
        if STATUS['uploads_blocked']:
            _retry_restore(data)
            continue
        backup_now(data)


def _retry_restore(data):
    """After a failed restore at start-up, try again while the local database is still empty."""
    cfg = backup_config()
    db = Path(data) / DB_NAME
    if not cfg or not db_is_empty(db):
        return
    try:
        blob = download_snapshot(cfg)
        with _lock:
            if blob and db_is_empty(db):
                m = restore_snapshot(blob, data)
                STATUS['restored'] = f'Restored {m.get("users", "?")} user(s) and {m.get("projects", "?")} project(s) (retry).'
            STATUS.update(uploads_blocked=False, restore_error='')
            _state['fingerprint'] = fingerprint(data)
    except Exception:
        pass


class ShutdownBackup:
    """Pure ASGI middleware: final backup when the server receives lifespan.shutdown
    (Render sends SIGTERM on deploy, restart and sleep). Works with any FastAPI/Starlette version;
    atexit alone is not enough because recent uvicorn re-raises the signal after shutdown."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'lifespan':
            return await self.app(scope, receive, send)

        async def wrapped():
            msg = await receive()
            if msg.get('type') == 'lifespan.shutdown' and backup_config():
                import asyncio
                stop = _state.get('stop')
                if stop:
                    stop.set()
                res = await asyncio.get_running_loop().run_in_executor(None, lambda: backup_now(note='(shutdown)'))
                print('[Civora] Final backup at shutdown: ' + res, flush=True)
            return msg
        return await self.app(scope, wrapped, send)


def start(data=None, app=None):
    """Start the background backup thread (idempotent) and a final backup at shutdown."""
    cfg = backup_config()
    if not cfg or _state['thread']:
        return
    if app is not None:
        try:
            app.add_middleware(ShutdownBackup)
        except Exception as ex:
            print(f'[Civora] Shutdown backup hook not installed ({ex}); periodic backups still run.', flush=True)
    data = Path(data or STATUS.get('data_dir') or data_dir())
    stop = threading.Event()
    t = threading.Thread(target=_loop, args=(data, stop, cfg['interval']), name='civora-backup', daemon=True)
    _state.update(thread=t, stop=stop)
    t.start()
    import atexit

    atexit.register(lambda: (stop.set(), backup_now(data, note='(exit)')))


# ------------------------------------------------------------------ web page
def banner_html():
    if is_safe():
        return ''
    msg = STATUS.get('restore_error') or ('Data is stored temporarily on this server and will be deleted when it restarts. '
                                          'Ask the administrator to turn on cloud backup.')
    return (f'<div class="cv-review" style="margin:0 0 14px;background:#fef2f2;border-color:#fecaca;color:#991b1b">'
            f'<b>Storage warning:</b>&nbsp;{msg} <a href="/system/storage" style="font-weight:700;color:inherit">Details</a></div>')


def register_persistence_v360(app, require, csrf, check_csrf, layout, esc):
    from fastapi import Request, Form
    from fastapi.responses import RedirectResponse

    def _admin_only(u):
        """v3.9.2: server details (database host, folders, backup repo) are for the site Admin only."""
        import admin_v380
        from fastapi import HTTPException
        if not admin_v380.is_site_owner(u):
            raise HTTPException(403, 'Only the site Admin can open the server storage page.')

    def when(ts):
        return time.strftime('%d %b %Y, %I:%M:%S %p', time.localtime(ts)) if ts else 'not yet'

    @app.get('/system/storage')
    def storage_page(request: Request, msg: str = ''):
        _admin_only(require(request))
        mode = STATUS.get('mode') or storage_mode()
        labels = {'local': ('Saved on this computer', 'Your data is in the data folder of Civora on this PC.', '#15803d'),
                  'disk': ('Persistent disk', 'Data is on a permanent disk and survives restarts.', '#15803d'),
                  'postgres': ('PostgreSQL database', 'Data is stored in your online PostgreSQL database (Neon / Supabase). Restarts and redeploys do not lose anything; drawings are stored in the database too.', '#15803d'),
                  'cloud-backup': ('Cloud backup on', 'Data is backed up to a private GitHub repository and restored automatically after every restart.', '#15803d'),
                  'disk+cloud-backup': ('Persistent disk + cloud backup', 'Data is on a permanent disk and also backed up to GitHub.', '#15803d'),
                  'temporary': ('TEMPORARY – data will be lost', 'This server has no permanent disk and no backup. Users, logins and projects are deleted on every restart, sleep or redeploy.', '#b91c1c')}
        title, text, colour = labels.get(mode, labels['local'])
        if not is_safe():
            colour = '#b91c1c'
        import dbcompat
        rows = [('Storage', f'<b style="color:{colour}">{esc(title)}</b>'), ('Database', esc(dbcompat.backend_label())),
                ('Data folder', esc(STATUS.get('data_dir', '')))]
        if 'cloud-backup' in mode:
            rows += [('Backup repository', esc(STATUS.get('backup_repo', ''))),
                     ('Last backup', esc(when(STATUS.get('last_backup_at')))
                      + (f' · {STATUS["last_backup_size"] / 1024:,.0f} KB' if STATUS.get('last_backup_size') else '')),
                     ('At start-up', esc(STATUS.get('restored') or STATUS.get('restore_error') or '—'))]
            if STATUS.get('last_error'):
                rows.append(('Last error', f'<span style="color:#b91c1c">{esc(STATUS["last_error"])}</span>'))
            if STATUS.get('skipped_uploads'):
                rows.append(('Large files', f'{STATUS["skipped_uploads"]} drawing file(s) were too large for the backup – keep your own copy.'))
        table = ''.join(f'<tr><th style="width:190px">{k}</th><td>{v}</td></tr>' for k, v in rows)
        btn = (f'<form method="post" action="/system/storage/backup"><input type="hidden" name="csrf_token" value="{csrf(request)}">'
               f'<button class="cv-btn">Back up now</button></form>') if 'cloud-backup' in mode else ''
        howto = '' if is_safe() else '''<section class="cv-card" style="margin-top:16px"><h3>Best fix: PostgreSQL database (free)</h3><ol>
<li>Create a free database at <b>neon.tech</b> (or supabase.com), region Singapore. Copy the <b>connection string</b> (postgresql://…).</li>
<li>Render → civora-ai → Environment → add <code>DATABASE_URL</code> = that string → Save.</li>
<li>Open this page again: it should say “PostgreSQL database”.</li></ol></section>
<section class="cv-card" style="margin-top:16px"><h3>Or: cloud backup to GitHub (free)</h3><ol>
<li>On GitHub create a new <b>private</b> repository, e.g. <code>civora-data</code> (tick “Add a README”).</li>
<li>GitHub → Settings → Developer settings → Fine-grained tokens → Generate. Repository access: only <code>civora-data</code>. Permissions → Contents: <b>Read and write</b>. Copy the token.</li>
<li>Render → your civora-ai service → Environment → add <code>CIVORA_BACKUP_REPO</code> = <code>your-username/civora-data</code>, <code>CIVORA_BACKUP_TOKEN</code> = the token, and <code>CIVORA_SECRET_KEY</code> = any long random text. Save (Render redeploys).</li>
<li>Open this page again: it should say “Cloud backup on”.</li></ol>
<p class="hint">Data already lost before backup was switched on cannot be recovered. Register again once after the fix.</p></section>'''
        note = f'<p class="notice" style="margin:12px 0">{esc(msg)}</p>' if msg else ''
        return layout(request, 'Data storage', f'''<span class="eyebrow">SYSTEM</span><h1>Data storage &amp; backup</h1>
<p class="muted">{esc(text)}</p>{note}<section class="cv-card"><table>{table}</table><div class="actions">{btn}</div></section>{howto}''')

    @app.post('/system/storage/backup')
    def storage_backup(request: Request, csrf_token: str = Form(...)):
        _admin_only(require(request)); check_csrf(request, csrf_token)
        from urllib.parse import quote
        return RedirectResponse('/system/storage?msg=' + quote(backup_now(force=True, note='(manual)')), 303)
