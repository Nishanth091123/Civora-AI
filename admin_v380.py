"""Civora AI v3.8.0 - site owner, users & activity, audit log, Recycle Bin.

SITE OWNER  username in CIVORA_OWNER (default: nishanth_s)
  * sees and opens every project of every user (as Owner)
  * nobody else can delete anything in the site owner's projects
  * Users & activity: every user, what they use, when, how much; delete a user
    (to the Recycle Bin, or permanently)
  * Audit log: every page and action of every user
  * Recycle Bin: restore anything anybody deleted; only the site owner deletes permanently
Everybody else registers directly and works as an engineer on their own projects.

RECYCLE BIN  Every DELETE statement in the app goes through bin_execute(): the rows are copied
into civora_bin_v380 first (one "batch" per click), then deleted. Uploaded drawing files are
kept on disk / in PostgreSQL until the batch is purged. Nothing is ever deleted automatically.
"""
import contextvars
import json
import os
import re
import sqlite3
import time
import uuid
from collections import Counter, OrderedDict

CTX = contextvars.ContextVar('civora_request', default=None)
NOT_BINNED = {'remember_tokens', 'civora_kv', 'schema_migrations', 'civora_bin_v380', 'civora_audit_v380',
              'civora_files', 'sqlite_sequence', 'civora_invites_v270'}
RESTORE_ORDER = ['users', 'projects', 'uploads']
_DELETE_RX = re.compile(r'^\s*DELETE\s+FROM\s+"?([A-Za-z0-9_]+)"?\s*(?:WHERE\s+(.*))?$', re.I | re.S)
_DB = {'db': None}


def owner_username():
    return (os.environ.get('CIVORA_OWNER') or 'nishanth_s').strip().lower()


def is_site_owner(u):
    try:
        return bool(u) and str(u['username'] or '').lower() == owner_username()
    except (KeyError, IndexError, TypeError):
        return False


def site_owner_id(c):
    r = c.execute('SELECT id FROM users WHERE username=?', (owner_username(),)).fetchone()
    return r[0] if r else None


def init(db):
    _DB['db'] = db
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS civora_bin_v380 (id TEXT PRIMARY KEY, batch TEXT NOT NULL, tbl TEXT NOT NULL,
            row_json TEXT NOT NULL, project_id TEXT, deleted_by TEXT, deleted_at INTEGER NOT NULL, label TEXT NOT NULL DEFAULT '')''')
        c.execute('CREATE INDEX IF NOT EXISTS ix_bin_v380 ON civora_bin_v380(batch)')
        c.execute('''CREATE TABLE IF NOT EXISTS civora_audit_v380 (id INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL,
            user_id TEXT NOT NULL, method TEXT NOT NULL, path TEXT NOT NULL, status INTEGER NOT NULL, ms INTEGER NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS ix_audit_v380 ON civora_audit_v380(user_id, at)')


# ------------------------------------------------------------------ recycle bin core
def _rowdict(row, cur=None):
    if hasattr(row, 'keys'):
        return {k: row[k] for k in row.keys()}
    names = [d[0] for d in (cur.description or [])] if cur is not None else []
    return dict(zip(names, row))


def bin_execute(conn, sql, params=()):
    """Run a DELETE, keeping a copy of every deleted row in the Recycle Bin."""
    m = _DELETE_RX.match(sql or '')
    if not m or m.group(1).lower() in NOT_BINNED:
        return conn.execute(sql, params)
    table, where = m.group(1), m.group(2)
    cur = conn.execute(f'SELECT * FROM "{table}"' + (f' WHERE {where}' if where else ''), params)
    rows = [_rowdict(r, cur) for r in cur.fetchall()]
    res = conn.execute(sql, params)
    if rows:
        ctx = CTX.get() or {}
        batch = ctx.setdefault('batch', str(uuid.uuid4())) if ctx else str(uuid.uuid4())
        now = int(time.time())
        label = ctx.get('label') or ctx.get('path', '')
        for r in rows:
            pid = r.get('project_id') or (r.get('id') if table == 'projects' else None)
            conn.execute('INSERT INTO civora_bin_v380(id,batch,tbl,row_json,project_id,deleted_by,deleted_at,label) VALUES(?,?,?,?,?,?,?,?)',
                         (str(uuid.uuid4()), batch, table, json.dumps(r, default=str), pid, ctx.get('uid') or '', now, str(label)[:200]))
    return res


class BinConnection:
    """Wraps a sqlite3 / dbcompat connection: DELETE goes through the Recycle Bin, everything else unchanged."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        if isinstance(sql, str) and sql.lstrip()[:6].upper() == 'DELETE':
            return bin_execute(self._raw, sql, params)
        return self._raw.execute(sql, params)

    def executemany(self, sql, seq):
        cur = None
        for p in seq:
            cur = self.execute(sql, p)
        return cur

    def __getattr__(self, name):
        return getattr(self._raw, name)


def batches(c, uid=None, limit=200):
    sql = ('SELECT batch, MIN(deleted_at) AS at, MAX(deleted_by) AS who, MAX(label) AS label, COUNT(*) AS n, '
           'MAX(project_id) AS pid FROM civora_bin_v380' + (' WHERE deleted_by=?' if uid else '') +
           ' GROUP BY batch ORDER BY MIN(deleted_at) DESC LIMIT ' + str(int(limit)))
    return c.execute(sql, (uid,) if uid else ()).fetchall()


def batch_rows(c, batch):
    return [(r['tbl'], json.loads(r['row_json'])) for r in
            c.execute('SELECT tbl,row_json FROM civora_bin_v380 WHERE batch=? ORDER BY deleted_at', (batch,)).fetchall()]


def describe(rows):
    cnt = Counter(t for t, _ in rows)
    names = {'projects': 'project', 'uploads': 'drawing/file', 'civora_boq_reports': 'estimate', 'users': 'user',
             'civora_structural_v210': 'structural element', 'civora_bbs_v210': 'bar', 'civora_vastu_v360': 'Vastu check',
             'material_takeoffs': 'takeoff', 'civora_rate_master_v260': 'rate', 'civora_members_v270': 'team member',
             'civora_activity_v270': 'activity line'}
    parts = [f'{n} {names.get(t, t)}{"s" if n > 1 else ""}' for t, n in cnt.most_common() if t != 'civora_activity_v270']
    title = next((r.get('name') for t, r in rows if t in ('projects', 'users')), None) or \
        next((r.get('original_name') for t, r in rows if t == 'uploads'), None) or \
        next((r.get('reference') for t, r in rows if r.get('reference')), None)
    return title, ', '.join(parts) or f'{len(rows)} row(s)'


def restore(c, batch):
    rows = batch_rows(c, batch)
    order = sorted(rows, key=lambda tr: (RESTORE_ORDER.index(tr[0]) if tr[0] in RESTORE_ORDER else len(RESTORE_ORDER)))
    pending, restored = order, 0
    for _ in range(4):                       # foreign keys: retry rows whose parent came later
        left = []
        for t, r in pending:
            cols = list(r.keys())
            try:
                cur = c.execute(f'INSERT OR IGNORE INTO "{t}"({",".join(chr(34) + k + chr(34) for k in cols)}) '
                                f'VALUES({",".join("?" * len(cols))})', [r[k] for k in cols])
                restored += 1 if (cur.rowcount or 0) > 0 else 0
            except sqlite3.Error:
                left.append((t, r))
        pending = left
        if not pending:
            break
    if pending:
        raise ValueError(f'{len(pending)} row(s) could not be restored (their project or user no longer exists).')
    c.execute('DELETE FROM civora_bin_v380 WHERE batch=?', (batch,))
    return restored


def purge(c, batch, files_dir):
    import filestore
    rows = batch_rows(c, batch)
    names = [r.get('stored_name') for t, r in rows if t == 'uploads' and r.get('stored_name')]
    c.execute('DELETE FROM civora_bin_v380 WHERE batch=?', (batch,))
    return names


# ------------------------------------------------------------------ audit + request context
_SKIP = re.compile(r'(/media$|/favicon|\.svg$|\.png$|\.ico$|/static/)')


class AuditMiddleware:
    """Pure ASGI: one context per request (who, which click) and one audit row per page / action."""

    def __init__(self, app, db=None):
        self.app = app
        self.db = db

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http':
            return await self.app(scope, receive, send)
        ctx = {'path': scope.get('path', ''), 'method': scope.get('method', 'GET'), 'uid': None}
        token = CTX.set(ctx)
        status, t0 = {'code': 500}, time.time()

        async def _send(msg):
            if msg.get('type') == 'http.response.start':
                status['code'] = msg.get('status', 500)
            await send(msg)
        try:
            await self.app(scope, receive, _send)
        finally:
            CTX.reset(token)
            uid = ctx.get('uid')
            path = ctx['path']
            if uid and self.db and not _SKIP.search(path):
                try:
                    with self.db() as c:
                        c.execute('INSERT INTO civora_audit_v380(at,user_id,method,path,status,ms) VALUES(?,?,?,?,?,?)',
                                  (int(time.time()), uid, ctx['method'], path[:300], int(status['code']), int((time.time() - t0) * 1000)))
                except Exception:
                    pass                      # the audit log must never break the app


def note_user(u):
    """Called by app.current_user: remembers who is making this request."""
    ctx = CTX.get()
    if ctx is not None and u:
        try:
            ctx['uid'] = u['id']
        except (KeyError, IndexError, TypeError):
            pass


def set_label(text):
    ctx = CTX.get()
    if ctx is not None:
        ctx['label'] = text


# ------------------------------------------------------------------ owner protection
_DESTRUCTIVE = re.compile(r'/(delete|remove|clear|purge)(/|$|-)|/delete-project$|/data/(estimates|files)/')


def guard(c, request, project, uid):
    """Raise PermissionError when someone else tries to delete the site owner's data."""
    if request.method != 'POST' or not _DESTRUCTIVE.search(request.url.path):
        return
    oid = site_owner_id(c)
    if oid and project['owner_id'] == oid and uid != oid:
        raise PermissionError("This project belongs to the site Admin. Only the Admin can delete anything in it.")


# ------------------------------------------------------------------ analysis
FEATURES = [('Estimate', re.compile(r'/(smart|multi|quick|takeoff|materials|estimate|drawings|studio)')),
            ('Structure', re.compile(r'/(structure|structural|bbs)')), ('BOQ & cost', re.compile(r'/(boq|rates|sqft-rate)')),
            ('Vastu', re.compile(r'/vastu')), ('Reports', re.compile(r'/(reports|download|export|\.xlsx|\.pdf)')),
            ('Team', re.compile(r'/(team|invite|signoff)')), ('Projects', re.compile(r'/projects(/new)?$|/projects/[^/]+$')),
            ('Guide', re.compile(r'/guide')), ('Delete', re.compile(r'delete|remove|clear'))]


def feature_of(path):
    for name, rx in FEATURES:
        if rx.search(path):
            return name
    return 'Other'


def user_stats(c, uid, days=30):
    now = int(time.time())
    since = now - days * 86400
    rows = c.execute('SELECT at, method, path, status, ms FROM civora_audit_v380 WHERE user_id=? AND at>=? ORDER BY at',
                     (uid, since)).fetchall()
    pids = [r[0] for r in c.execute('SELECT id FROM projects WHERE owner_id=?', (uid,)).fetchall()]
    def count(table):
        if not pids:
            return 0
        try:
            return sum(c.execute(f'SELECT COUNT(*) FROM "{table}" WHERE project_id=?', (p,)).fetchone()[0] for p in pids)
        except sqlite3.Error:
            return 0
    last = c.execute('SELECT MAX(at) FROM civora_audit_v380 WHERE user_id=?', (uid,)).fetchone()[0]
    first = c.execute('SELECT MIN(at) FROM civora_audit_v380 WHERE user_id=?', (uid,)).fetchone()[0]
    actions = [r for r in rows if r['method'] == 'POST']
    days_active = len({time.strftime('%Y-%m-%d', time.localtime(r['at'])) for r in rows})
    per_day = Counter(time.strftime('%Y-%m-%d', time.localtime(r['at'])) for r in rows)
    hours = Counter(int(time.strftime('%H', time.localtime(r['at']))) for r in rows)
    feats = Counter(feature_of(r['path']) for r in rows)
    errors = sum(1 for r in rows if r['status'] >= 400)
    return {'projects': len(pids), 'estimates': count('civora_boq_reports'), 'uploads': count('uploads'),
            'structural': count('civora_structural_v210'), 'bars': count('civora_bbs_v210'),
            'views': len(rows) - len(actions), 'actions': len(actions), 'days_active': days_active, 'errors': errors,
            'last': last, 'first': first, 'per_day': per_day, 'hours': hours, 'features': feats,
            'recent': list(reversed(rows[-60:])), 'avg_ms': int(sum(r['ms'] for r in rows) / len(rows)) if rows else 0}


def _ago(ts):
    if not ts:
        return 'never'
    d = max(int(time.time()) - int(ts), 0)
    return 'just now' if d < 60 else f'{d // 60} min ago' if d < 3600 else f'{d // 3600} h ago' if d < 86400 else time.strftime('%d %b %Y', time.localtime(ts))


# ------------------------------------------------------------------ pages
def register_admin_v380(app, db, require, csrf, check_csrf, layout, esc, FILES):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    from ui_shell import icon
    import filestore
    init(db)
    app.add_middleware(AuditMiddleware, db=db)

    def need_owner(request):
        u = require(request)
        if not is_site_owner(u):
            raise HTTPException(403, 'Only the site Admin can open this page.')
        return u

    @app.get('/admin/users')
    def admin_users(request: Request, msg: str = ''):
        need_owner(request)
        since = int(time.time()) - 30 * 86400
        with db() as c:
            users = c.execute('SELECT id,name,username FROM users ORDER BY name').fetchall()
            act = {r[0]: (r[1], r[2]) for r in c.execute('SELECT user_id, COUNT(*), MAX(at) FROM civora_audit_v380 WHERE at>=? GROUP BY user_id', (since,)).fetchall()}
            last = {r[0]: r[1] for r in c.execute('SELECT user_id, MAX(at) FROM civora_audit_v380 GROUP BY user_id').fetchall()}
            projs = Counter(r[0] for r in c.execute('SELECT owner_id FROM projects').fetchall())
        trs = ''
        for u in users:
            own = str(u['username']).lower() == owner_username()
            role = '<span class="cv-chip" style="background:#1467ef1a;color:#1467ef">Owner</span>' if own else '<span class="cv-chip" style="background:#7c3aed1a;color:#7c3aed">Engineer</span>'
            trs += (f'<tr><td><b>{esc(u["name"])}</b><br><small class="muted">@{esc(u["username"])}</small></td><td>{role}</td>'
                    f'<td style="text-align:right">{projs.get(u["id"], 0)}</td><td style="text-align:right">{act.get(u["id"], (0,))[0]}</td>'
                    f'<td>{esc(_ago(last.get(u["id"])))}</td><td><a class="cv-btn sm ghost" href="/admin/users/{esc(u["id"])}">Activity &amp; analysis</a></td></tr>')
        note = f'<p class="notice">{esc(msg)}</p>' if msg else ''
        return layout(request, 'Users & activity', f'''<span class="eyebrow">OWNER · USERS</span><h1>Users &amp; activity</h1>
<p class="muted">{len(users)} user(s). Everyone except you works as an Engineer on their own projects. You can open every project.</p>{note}
<section class="cv-card"><div class="scroll"><table class="cv-mt"><tr><th>User</th><th>Role</th><th style="text-align:right">Projects</th>
<th style="text-align:right">Clicks (30 days)</th><th>Last active</th><th></th></tr>{trs}</table></div></section>
<div class="actions"><a class="cv-btn ghost" href="/admin/audit">Full audit log</a><a class="cv-btn ghost" href="/bin">Recycle Bin</a></div>''')

    @app.get('/admin/users/{uid}')
    def admin_user(request: Request, uid: str):
        me = need_owner(request)
        with db() as c:
            u = c.execute('SELECT id,name,username FROM users WHERE id=?', (uid,)).fetchone()
            if not u:
                raise HTTPException(404, 'User not found')
            st = user_stats(c, uid)
            projects = c.execute('SELECT id,name,location,area,created FROM projects WHERE owner_id=? ORDER BY created DESC', (uid,)).fetchall()
        days = [time.strftime('%Y-%m-%d', time.localtime(time.time() - i * 86400)) for i in range(29, -1, -1)]
        mx = max([st['per_day'].get(d, 0) for d in days] + [1])
        bars = ''.join(f'<div title="{d}: {st["per_day"].get(d, 0)}" style="flex:1;background:#2563eb;opacity:{.25 + .75 * (st["per_day"].get(d, 0) > 0)};'
                       f'height:{max(2, 90 * st["per_day"].get(d, 0) / mx):.0f}px;border-radius:3px 3px 0 0"></div>' for d in days)
        hmx = max(list(st['hours'].values()) + [1])
        hours = ''.join(f'<div title="{h}:00 – {st["hours"].get(h, 0)}" style="flex:1;background:#0d9488;height:{max(2, 60 * st["hours"].get(h, 0) / hmx):.0f}px;border-radius:3px 3px 0 0"></div>' for h in range(24))
        tot = sum(st['features'].values()) or 1
        feats = ''.join(f'<tr><td>{esc(n)}</td><td style="width:60%"><div style="background:#e2e8f0;border-radius:6px"><div style="width:{100 * k / tot:.0f}%;background:#7c3aed;height:10px;border-radius:6px"></div></div></td>'
                        f'<td style="text-align:right">{k} · {100 * k / tot:.0f}%</td></tr>' for n, k in st['features'].most_common())
        recent = ''.join(f'<tr><td><small>{time.strftime("%d %b %H:%M", time.localtime(r["at"]))}</small></td><td>{esc(r["method"])}</td><td><small>{esc(r["path"])}</small></td>'
                         f'<td>{"<b style=color:#b91c1c>" + str(r["status"]) + "</b>" if r["status"] >= 400 else r["status"]}</td></tr>' for r in st['recent'])
        plist = ''.join(f'<li><a href="/projects/{esc(p["id"])}">{esc(p["name"])}</a> <small class="muted">{esc(p["location"])} · {float(p["area"] or 0):,.0f} sq.ft</small></li>' for p in projects) or '<li class="muted">No projects</li>'
        kpi = [('Projects', st['projects']), ('Estimates', st['estimates']), ('Drawings', st['uploads']), ('Structural items', st['structural']),
               ('Actions (30 d)', st['actions']), ('Pages (30 d)', st['views']), ('Days active (30 d)', st['days_active']), ('Errors seen', st['errors'])]
        kpis = ''.join(f'<div class="cv-card" style="padding:12px 14px"><small class="muted">{esc(a)}</small><div style="font-size:24px;font-weight:800">{b}</div></div>' for a, b in kpi)
        busiest = max(st['hours'], key=st['hours'].get) if st['hours'] else None
        top = st['features'].most_common(1)[0][0] if st['features'] else '—'
        summary = (f'Mostly uses <b>{esc(top)}</b>' + (f', usually around <b>{busiest}:00</b>' if busiest is not None else '') +
                   f'; {st["actions"]} saves/changes in 30 days on {st["days_active"]} day(s). Last active {esc(_ago(st["last"]))}.')
        own = str(u['username']).lower() == owner_username()
        danger = '' if own else f'''<section class="cv-card" style="margin-top:16px;border-color:#fecaca"><h3 style="color:#b91c1c">Delete this user</h3>
<p class="sub">Removes the account, all {st["projects"]} of their project(s) with drawings, estimates and structure, and their team memberships.</p>
<form method="post" action="/admin/users/{esc(uid)}/delete" onsubmit="return confirm('Delete this user?')"><input type="hidden" name="csrf_token" value="{csrf(request)}">
<label>Type the username <b>{esc(u["username"])}</b> to confirm<input name="confirm_name" required autocomplete="off"></label>
<label class="checkline"><input type="checkbox" name="permanent" value="yes"> Delete permanently (skip the Recycle Bin – cannot be undone)</label>
<button class="cv-btn" style="background:#b91c1c;border-color:#b91c1c">Delete user</button></form></section>'''
        return layout(request, 'User activity', f'''<span class="eyebrow">OWNER · USER ANALYSIS</span><h1>{esc(u["name"])} <small class="muted">@{esc(u["username"])}</small></h1>
<p class="muted">{summary}</p>
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:12px 0">{kpis}</div>
<div class="cv-row"><section class="cv-card"><h3>Activity – last 30 days</h3><div style="display:flex;align-items:flex-end;gap:3px;height:96px">{bars}</div>
<p class="sub">{esc(days[0])} → today</p><h3 style="margin-top:14px">Time of day</h3><div style="display:flex;align-items:flex-end;gap:3px;height:64px">{hours}</div><p class="sub">00:00 → 23:00</p></section>
<section class="cv-card"><h3>What they use</h3><table class="cv-mt">{feats or '<tr><td class="muted">No activity yet</td></tr>'}</table>
<h3 style="margin-top:14px">Projects</h3><ul>{plist}</ul></section></div>
<section class="cv-card" style="margin-top:16px"><h3>Recent actions</h3><div class="scroll" style="max-height:420px"><table class="cv-mt"><tr><th>When</th><th></th><th>Page / action</th><th>Result</th></tr>{recent}</table></div></section>
{danger}''')

    @app.post('/admin/users/{uid}/delete')
    async def admin_delete_user(request: Request, uid: str):
        need_owner(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            u = c.execute('SELECT id,name,username FROM users WHERE id=?', (uid,)).fetchone()
            if not u:
                raise HTTPException(404, 'User not found')
            if str(u['username']).lower() == owner_username():
                raise HTTPException(400, 'The Admin account cannot be deleted.')
            if str(form.get('confirm_name', '')).strip().lower() != str(u['username']).lower():
                raise HTTPException(400, 'The username you typed does not match. Nothing was deleted.')
            set_label(f'User {u["name"]} (@{u["username"]}) deleted')
            delete_user_rows(c, uid)
            batch = (CTX.get() or {}).get('batch')
            names = purge(c, batch, FILES) if (form.get('permanent') == 'yes' and batch) else []
        for n in names:
            filestore.purge(FILES, n)
        from urllib.parse import quote
        how = 'permanently' if form.get('permanent') == 'yes' else 'to the Recycle Bin'
        return RedirectResponse('/admin/users?msg=' + quote(f'{u["name"]} was deleted {how}.'), 303)

    @app.get('/admin/audit')
    def admin_audit(request: Request, user: str = '', page: int = 0):
        need_owner(request)
        page = max(int(page), 0)
        with db() as c:
            names = {r[0]: (r[1], r[2]) for r in c.execute('SELECT id,name,username FROM users').fetchall()}
            q = 'SELECT * FROM civora_audit_v380' + (' WHERE user_id=?' if user else '') + ' ORDER BY at DESC, id DESC LIMIT 200 OFFSET ' + str(page * 200)
            rows = c.execute(q, (user,) if user else ()).fetchall()
            total = c.execute('SELECT COUNT(*) FROM civora_audit_v380' + (' WHERE user_id=?' if user else ''), (user,) if user else ()).fetchone()[0]
        opts = '<option value="">All users</option>' + ''.join(f'<option value="{esc(k)}"{" selected" if k == user else ""}>{esc(v[0])} (@{esc(v[1])})</option>' for k, v in names.items())
        trs = ''.join(f'<tr><td><small>{time.strftime("%d %b %Y %H:%M:%S", time.localtime(r["at"]))}</small></td><td>{esc(names.get(r["user_id"], ("deleted user",))[0])}</td>'
                      f'<td>{esc(r["method"])}</td><td><small>{esc(r["path"])}</small></td><td>{esc(feature_of(r["path"]))}</td><td>{r["status"]}</td><td style="text-align:right"><small>{r["ms"]} ms</small></td></tr>' for r in rows)
        nav = (f'<a class="cv-btn sm ghost" href="/admin/audit?user={esc(user)}&page={page - 1}">← Newer</a>' if page else '') + \
              (f'<a class="cv-btn sm ghost" href="/admin/audit?user={esc(user)}&page={page + 1}">Older →</a>' if (page + 1) * 200 < total else '')
        return layout(request, 'Audit log', f'''<span class="eyebrow">OWNER · AUDIT LOG</span><h1>Audit log</h1><p class="muted">{total:,} entries. Every page opened and every action, by every user. Never deleted.</p>
<form method="get" class="cv-card" style="display:flex;gap:10px;align-items:center;padding:12px 16px;margin:0 0 14px"><b>User</b><select name="user" onchange="this.form.submit()">{opts}</select></form>
<section class="cv-card"><div class="scroll"><table class="cv-mt"><tr><th>When</th><th>User</th><th></th><th>Page / action</th><th>Feature</th><th>Result</th><th>Time</th></tr>{trs}</table></div>
<div class="actions">{nav}</div></section>''')

    # ---------------- Recycle Bin
    @app.get('/bin')
    def recycle_bin(request: Request, msg: str = ''):
        u = require(request)
        owner = is_site_owner(u)
        with db() as c:
            bs = batches(c, None if owner else u['id'])
            names = {r[0]: r[1] for r in c.execute('SELECT id,name FROM users').fetchall()}
            info = {b['batch']: describe(batch_rows(c, b['batch'])) for b in bs}
        token = csrf(request)
        trs = ''
        for b in bs:
            title, what = info[b['batch']]
            btns = (f'<form method="post" action="/bin/{esc(b["batch"])}/restore" style="display:inline"><input type="hidden" name="csrf_token" value="{token}">'
                    f'<button class="cv-btn sm">Restore</button></form>')
            if owner:
                btns += (f' <form method="post" action="/bin/{esc(b["batch"])}/purge" style="display:inline" onsubmit="return confirm(&quot;Delete permanently? This cannot be undone.&quot;)">'
                         f'<input type="hidden" name="csrf_token" value="{token}"><button class="cv-btn sm" style="background:#b91c1c;border-color:#b91c1c">Delete permanently</button></form>')
            trs += (f'<tr><td><small>{time.strftime("%d %b %Y %H:%M", time.localtime(b["at"]))}</small></td><td><b>{esc(title or "—")}</b><br><small class="muted">{esc(what)}</small></td>'
                    f'<td>{esc(names.get(b["who"], "—"))}</td><td style="white-space:nowrap">{btns}</td></tr>')
        note = f'<p class="notice">{esc(msg)}</p>' if msg else ''
        return layout(request, 'Recycle Bin', f'''<span class="eyebrow">RECYCLE BIN · மறுசுழற்சி தொட்டி</span><h1>Recycle Bin</h1>
<p class="muted">Everything deleted in Civora comes here first and stays until {'you delete it permanently' if owner else 'the Admin deletes it permanently'}. Nothing is removed automatically.</p>{note}
<section class="cv-card"><div class="scroll"><table class="cv-mt"><tr><th>Deleted</th><th>What</th><th>By</th><th></th></tr>{trs or '<tr><td colspan="4" class="muted">The Recycle Bin is empty.</td></tr>'}</table></div></section>''')

    @app.post('/bin/{batch}/restore')
    async def bin_restore(request: Request, batch: str):
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        from urllib.parse import quote
        with db() as c:
            r = c.execute('SELECT deleted_by FROM civora_bin_v380 WHERE batch=? LIMIT 1', (batch,)).fetchone()
            if not r or not (is_site_owner(u) or r[0] == u['id']):
                raise HTTPException(404, 'Not found in the Recycle Bin')
            try:
                n = restore(c, batch)
            except ValueError as ex:
                return RedirectResponse('/bin?msg=' + quote(str(ex)), 303)
        return RedirectResponse('/bin?msg=' + quote(f'Restored ({n} item(s)).'), 303)

    @app.post('/bin/{batch}/purge')
    async def bin_purge(request: Request, batch: str):
        need_owner(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            names = purge(c, batch, FILES)
        for n in names:
            filestore.purge(FILES, n)
        return RedirectResponse('/bin?msg=Deleted+permanently.', 303)


def delete_user_rows(c, uid):
    """Every row of a user: their projects (all tables), memberships, rates, settings, then the user."""
    pids = [r[0] for r in c.execute('SELECT id FROM projects WHERE owner_id=?', (uid,)).fetchall()]
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
              if r[0] not in NOT_BINNED and r[0] not in ('users', 'projects') and not r[0].startswith('sqlite_')]
    cols = {t: {r[1] for r in c.execute(f'PRAGMA table_info("{t}")').fetchall()} for t in tables}
    ordered = [t for t in tables if t != 'uploads'] + (['uploads'] if 'uploads' in tables else [])
    for pid in pids:
        for t in ordered:
            if 'project_id' in cols[t]:
                c.execute(f'DELETE FROM "{t}" WHERE project_id=?', (pid,))
    for t in ordered:
        if 'user_id' in cols[t]:
            c.execute(f'DELETE FROM "{t}" WHERE user_id=?', (uid,))
    c.execute('DELETE FROM remember_tokens WHERE user_id=?', (uid,))
    for pid in pids:
        c.execute('DELETE FROM projects WHERE id=?', (pid,))
    c.execute('DELETE FROM users WHERE id=?', (uid,))
