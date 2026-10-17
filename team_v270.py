"""Civora AI v2.7.0 - Team access: several people on one project, each with a role.

Roles (per project):
  owner      - created the project; everything, incl. team and deleting files
  engineer   - edit quantities + structural design inputs, review and sign-off
  colleague  - edit quantities, estimates, drawings, rates (no design sign-off)
  dealer     - view and download only
  customer   - view and download only

Access is enforced in ONE place (app.owned_project -> check_access) for every module,
so older pages get the same rules without being changed.
New tables (additive): civora_members_v270, civora_invites_v270, civora_activity_v270, civora_signoff_v270.
"""
import hashlib
import re
import secrets
import time
from collections import OrderedDict

ROLES = OrderedDict([
    ('owner', ('Creator', 'உருவாக்கியவர்', 'Created the project. Full control of this project, manages its team.', '#1467ef')),
    ('engineer', ('Engineer', 'பொறியாளர்', 'Edits quantities and structural design inputs, signs off the design review.', '#7c3aed')),
    ('colleague', ('Colleague', 'சக பணியாளர்', 'Edits drawings, estimates, quantities and rates.', '#16a34a')),
    ('dealer', ('Dealer', 'டீலர்', 'Views materials, cost and reports. Cannot change anything.', '#ea580c')),
    ('customer', ('Customer', 'வாடிக்கையாளர்', 'Views the estimate, cost and reports. Cannot change anything.', '#0ea5e9')),
])
INVITE_ROLES = [r for r in ROLES if r != 'owner']
PERMS = {
    'view': {'owner', 'engineer', 'colleague', 'dealer', 'customer'},
    'edit': {'owner', 'engineer', 'colleague'},
    'design': {'owner', 'engineer'},
    'manage': {'owner'},
}
NEED_LABEL = {'edit': 'Creator, Engineer or Colleague', 'design': 'Creator or Engineer', 'manage': 'the project Creator'}
ADMIN = ('Admin', 'நிர்வாகி', 'Site administrator – sees and manages every project and user.', '#b45309')
INVITE_DAYS = 7

_DESIGN_PATH = re.compile(r'^/projects/[^/]+/(structural/design|structural/review|signoff)(/|$)')
_UPLOAD_DELETE = re.compile(r'^/projects/[^/]+/uploads/[^/]+/delete$')
_MANAGE = re.compile(r'^/projects/[^/]+/team(/|$)')


def role_label(role):
    return ROLES.get(role, (str(role).title(),))[0]


def display(role, admin=False):
    """v3.9.2: (label, tamil, description, colour) shown to the user. The site owner is always 'Admin'."""
    return ADMIN if admin else ROLES.get(role, ROLES['customer'])


def required_permission(method, path):
    """What a request needs: view / edit / design / manage."""
    if method in ('GET', 'HEAD', 'OPTIONS'):
        return 'view'
    if _MANAGE.match(path) or _UPLOAD_DELETE.match(path):
        return 'manage'
    if _DESIGN_PATH.match(path):
        return 'design'
    return 'edit'


def allowed(role, need):
    return role in PERMS.get(need, set())


def init(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS civora_members_v270 (
            project_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL,
            added_by TEXT NOT NULL, added_at INTEGER NOT NULL, PRIMARY KEY(project_id, user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS civora_invites_v270 (
            token_hash TEXT PRIMARY KEY, project_id TEXT NOT NULL, role TEXT NOT NULL,
            created_by TEXT NOT NULL, created_at INTEGER NOT NULL, expires INTEGER NOT NULL,
            used_by TEXT, used_at INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS civora_activity_v270 (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, user_id TEXT NOT NULL,
            action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', at INTEGER NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS ix_activity_v270 ON civora_activity_v270(project_id, at)')
        c.execute('''CREATE TABLE IF NOT EXISTS civora_signoff_v270 (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, user_id TEXT NOT NULL,
            role TEXT NOT NULL, note TEXT NOT NULL, at INTEGER NOT NULL)''')


def _is_site_owner_id(c, uid):
    try:
        import admin_v380
        return uid is not None and admin_v380.site_owner_id(c) == uid
    except Exception:
        return False


def project_role(c, pid, uid):
    p = c.execute('SELECT owner_id FROM projects WHERE id=?', (pid,)).fetchone()
    if not p:
        return None
    if p[0] == uid or _is_site_owner_id(c, uid):     # v3.8.0: the site owner can open every project
        return 'owner'
    m = c.execute('SELECT role FROM civora_members_v270 WHERE project_id=? AND user_id=?', (pid, uid)).fetchone()
    return m[0] if m and m[0] in ROLES else None


def accessible_projects(c, uid, where='', args=(), limit=None):
    """Projects the user owns or is a member of, newest first, with the user's role as column 'my_role'."""
    if _is_site_owner_id(c, uid):                    # v3.8.0: site owner sees every project
        sql = ('SELECT p.*, \'owner\' AS my_role FROM projects p WHERE 1=1' + (f' AND ({where})' if where else '') + ' ORDER BY p.created DESC')
        if limit:
            sql += f' LIMIT {int(limit)}'
        return c.execute(sql, tuple(args)).fetchall()
    sql = ('SELECT p.*, CASE WHEN p.owner_id=? THEN \'owner\' ELSE m.role END AS my_role FROM projects p '
           'LEFT JOIN civora_members_v270 m ON m.project_id=p.id AND m.user_id=? '
           'WHERE (p.owner_id=? OR m.user_id=?)' + (f' AND ({where})' if where else '') + ' ORDER BY p.created DESC')
    if limit:
        sql += f' LIMIT {int(limit)}'
    return c.execute(sql, (uid, uid, uid, uid) + tuple(args)).fetchall()


def log(c, pid, uid, action, detail=''):
    c.execute('INSERT INTO civora_activity_v270(project_id,user_id,action,detail,at) VALUES(?,?,?,?,?)',
              (pid, uid, str(action)[:120], str(detail)[:300], int(time.time())))


_ACTIONS = [
    (re.compile(r'/smart/upload$'), 'Uploaded a drawing for Smart Estimate'),
    (re.compile(r'/smart/[^/]+$'), 'Ran Smart Estimate'),
    (re.compile(r'/rates/apply$'), 'Applied Rate Master prices'),
    (re.compile(r'/quick$'), 'Ran Quick Estimate'),
    (re.compile(r'/upload$'), 'Uploaded a file'),
    (re.compile(r'/boq/save$'), 'Saved a drawing BOQ'),
    (re.compile(r'/boq/[^/]+/rates$'), 'Edited BOQ line rates'),
    (re.compile(r'/boq/[^/]+/costs$'), 'Edited labour / transport / tax'),
    (re.compile(r'/structural/design'), 'Updated structural design inputs'),
    (re.compile(r'/structural'), 'Updated structural quantities'),
    (re.compile(r'/takeoff'), 'Updated material takeoff'),
    (re.compile(r'/materials'), 'Updated measurements'),
    (re.compile(r'/delete$'), 'Deleted an item'),
]


def action_for(path):
    for rx, text in _ACTIONS:
        if rx.search(path):
            return text
    return 'Updated project data'


class ActivityMiddleware:
    """Pure ASGI: after a successful (303) project POST, records who did what.
    The project and user are left in scope['state'] by app.owned_project."""

    def __init__(self, app, db=None):
        self.app = app
        self.db = db

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or scope.get('method') != 'POST':
            return await self.app(scope, receive, send)
        status = {}

        async def _send(msg):
            if msg.get('type') == 'http.response.start':
                status['code'] = msg.get('status')
            await send(msg)
        await self.app(scope, receive, _send)
        actor = (scope.get('state') or {}).get('cv_actor')
        path = scope.get('path', '')
        if actor and status.get('code') == 303 and not _MANAGE.match(path) and '/signoff' not in path and self.db:
            try:
                with self.db() as c:
                    log(c, actor[1], actor[0], action_for(path))
            except Exception:       # activity log must never break a save
                pass


def _ago(ts):
    d = max(int(time.time()) - int(ts), 0)
    if d < 60:
        return 'just now'
    if d < 3600:
        return f'{d // 60} min ago'
    if d < 86400:
        return f'{d // 3600} h ago'
    return time.strftime('%d %b %Y', time.localtime(ts))


def latest_signoff(c, pid):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_signoff_v270'").fetchone():
        return None
    return c.execute('SELECT s.*, u.name AS who FROM civora_signoff_v270 s JOIN users u ON u.id=s.user_id '
                     'WHERE s.project_id=? ORDER BY s.at DESC, s.id DESC LIMIT 1', (pid,)).fetchone()


def safe_next(url):
    url = str(url or '')
    return url if url.startswith('/') and not url.startswith('//') and '\\' not in url and len(url) < 300 else ''


# ------------------------------------------------------------------ pages
def register_team_v270(app, db, owned_project, require, csrf, check_csrf, layout, esc, current_user):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    from ui_shell import icon
    init(db)
    app.add_middleware(ActivityMiddleware, db=db)

    def chip(role):
        en, ta, _, colour = ROLES[role]
        return f'<span class="cv-chip" style="background:{colour}1a;color:{colour}">{esc(en)}</span>'

    def team_page(request, p, message='', error='', link=''):
        pid = p['id']
        u = require(request)
        with db() as c:
            role = project_role(c, pid, u['id'])
            owner = c.execute('SELECT id,name,username FROM users WHERE id=?', (p['owner_id'],)).fetchone()
            members = c.execute('SELECT m.role, m.added_at, u.id, u.name, u.username FROM civora_members_v270 m JOIN users u ON u.id=m.user_id '
                                'WHERE m.project_id=? ORDER BY m.added_at', (pid,)).fetchall()
            acts = c.execute('SELECT a.*, u.name FROM civora_activity_v270 a LEFT JOIN users u ON u.id=a.user_id '
                             'WHERE a.project_id=? ORDER BY a.at DESC, a.id DESC LIMIT 40', (pid,)).fetchall()
            invites = c.execute('SELECT role, created_at, expires FROM civora_invites_v270 WHERE project_id=? AND used_by IS NULL AND expires>? '
                                'ORDER BY created_at DESC', (pid, int(time.time()))).fetchall()
        token = csrf(request)
        is_owner = role == 'owner'
        P = f'/projects/{pid}'

        def person(name, uname, r, uid=None, removable=False):
            initials = ''.join(w[0] for w in str(name).split()[:2]).upper() or 'U'
            ctl = ''
            if removable and is_owner:
                opts = ''.join(f'<option value="{k}"{" selected" if k == r else ""}>{esc(ROLES[k][0])}</option>' for k in INVITE_ROLES)
                ctl = (f'<form method="post" action="{P}/team/role" class="cv-inline"><input type="hidden" name="csrf_token" value="{token}">'
                       f'<input type="hidden" name="user_id" value="{esc(uid)}"><select name="role" onchange="this.form.submit()" aria-label="Role">{opts}</select></form>'
                       f'<form method="post" action="{P}/team/remove" class="cv-inline" onsubmit="return confirm(&quot;Remove {esc(name)} from this project?&quot;)">'
                       f'<input type="hidden" name="csrf_token" value="{token}"><input type="hidden" name="user_id" value="{esc(uid)}">'
                       f'<button class="cv-btn sm ghost" style="color:#b91c1c">Remove</button></form>')
            return (f'<li class="cv-person"><span class="cv-avatar sm" style="background:{ROLES[r][3]}">{esc(initials)}</span>'
                    f'<span class="nm"><b>{esc(name)}</b><small>@{esc(uname)}</small></span>{chip(r)}{ctl}</li>')
        people = person(owner['name'], owner['username'], 'owner') + ''.join(
            person(m['name'], m['username'], m['role'], m['id'], True) for m in members)
        role_rows = ''.join(f'<tr><td>{chip(k)}<br><small style="color:#64798d">{esc(v[1])}</small></td><td>{esc(v[2])}</td>'
                            f'<td style="text-align:center">{"✓" if k in PERMS["edit"] else "–"}</td><td style="text-align:center">{"✓" if k in PERMS["design"] else "–"}</td>'
                            f'<td style="text-align:center">{"✓" if k in PERMS["manage"] else "–"}</td></tr>' for k, v in ROLES.items())
        act_html = ''.join(f'<li><span class="dot"></span><span><b>{esc(a["name"] or "Someone")}</b> {esc(a["action"])}'
                           f'{(" – " + esc(a["detail"])) if a["detail"] else ""}<small>{_ago(a["at"])}</small></span></li>' for a in acts)
        note = (f'<div class="cv-banner">{icon("check", 22)}<div><b>{esc(message)}</b></div></div>' if message else '') + \
               (f'<div class="cv-banner err">{icon("shield", 22)}<div><b>{esc(error)}</b></div></div>' if error else '')
        invite_box = ''
        if is_owner:
            ropts = ''.join(f'<option value="{k}">{esc(ROLES[k][0])} – {esc(ROLES[k][1])}</option>' for k in INVITE_ROLES)
            link_html = ''
            if link:
                wa = 'https://wa.me/?text=' + _urlq(f'You are invited to the Civora AI project "{p["name"]}": {link}')
                link_html = (f'<div class="cv-linkbox"><input readonly value="{esc(link)}" onclick="this.select()" aria-label="Invite link">'
                             f'<button type="button" class="cv-btn sm" onclick="navigator.clipboard&&navigator.clipboard.writeText(this.previousElementSibling.value);this.textContent=\'Copied ✓\'">Copy</button>'
                             f'<a class="cv-btn sm ghost" href="{esc(wa)}" target="_blank" rel="noopener">WhatsApp</a></div>'
                             f'<p class="hint">Single use · valid {INVITE_DAYS} days. The person must be able to open this Civora address (same computer / network now; anyone once Civora is online).</p>')
            pend = ''.join(f'<li>{chip(i["role"])} invite link · expires {time.strftime("%d %b", time.localtime(i["expires"]))}</li>' for i in invites)
            invite_box = f'''<section class="cv-card"><h3>{icon("plus", 18)} Invite people</h3>
<p class="sub">Create a link and send it on WhatsApp, or add someone who already has a Civora account.</p>
<form method="post" action="{P}/team/invite" class="cv-fin"><input type="hidden" name="csrf_token" value="{token}"><select name="role">{ropts}</select><button class="cv-btn sm">Create invite link</button></form>{link_html}
<form method="post" action="{P}/team/add" class="cv-fin" style="margin-top:12px"><input type="hidden" name="csrf_token" value="{token}">
<input name="username" required placeholder="Their Civora username" maxlength="30"><select name="role">{ropts}</select><button class="cv-btn sm ghost">Add</button></form>
{f'<ul class="cv-files" style="margin-top:10px">{pend}</ul>' if pend else ''}</section>'''
        return layout(request, f'{p["name"]} · Team', f'''<div class="cv-ph"><div><span class="eyebrow">TEAM · குழு</span><h1>{esc(p["name"])}</h1>
<div class="meta"><span>Your role: {chip(role)}</span><span>{1 + len(members)} people</span></div></div><a class="cv-btn ghost" href="{P}/workflow">Back to workflow</a></div>{note}
<div class="cv-row" style="margin-top:14px"><div><section class="cv-card"><h3>{icon("users", 18)} People on this project</h3><ul class="cv-people">{people}</ul></section>
{f'<section class="cv-card" style="margin-top:16px"><h3>{icon("layers", 18)} Recent activity</h3><ul class="cv-activity">{act_html or "<li class=sub>Nothing yet.</li>"}</ul></section>' if allowed(role, 'edit') else ''}</div>
<div>{invite_box}<section class="cv-card" style="margin-top:{16 if invite_box else 0}px"><h3>{icon("shield", 18)} Who can do what</h3>
<div class="scroll"><table class="cv-mt"><tr><th>Role</th><th>Meaning</th><th>Edit</th><th>Design sign-off</th><th>Team</th></tr>{role_rows}</table></div>
<p class="hint">Everyone on the project can view and download reports.</p></section></div></div>''')

    def owner_project(request, pid):
        p = owned_project(request, pid)      # GET -> any member; POST to /team -> owner only (enforced centrally)
        return p

    @app.get('/projects/{pid}/team')
    def team(request: Request, pid: str):
        p = owner_project(request, pid)
        q = request.query_params
        return team_page(request, p, message={'added': 'Member added.', 'removed': 'Member removed.', 'role': 'Role changed.'}.get(q.get('done', ''), ''))

    @app.post('/projects/{pid}/team/invite')
    async def create_invite(request: Request, pid: str):
        p = owner_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        role = form.get('role')
        if role not in INVITE_ROLES:
            raise HTTPException(400, 'Choose a role')
        raw = secrets.token_urlsafe(24)
        now = int(time.time())
        with db() as c:
            c.execute('INSERT INTO civora_invites_v270(token_hash,project_id,role,created_by,created_at,expires) VALUES(?,?,?,?,?,?)',
                      (hashlib.sha256(raw.encode()).hexdigest(), pid, role, require(request)['id'], now, now + INVITE_DAYS * 86400))
            log(c, pid, require(request)['id'], f'Created an invite link for a {role_label(role)}')
        link = str(request.base_url).rstrip('/') + '/invite/' + raw
        return team_page(request, p, message=f'Invite link for a {role_label(role)} is ready – copy it and send it.', link=link)

    @app.post('/projects/{pid}/team/add')
    async def add_member(request: Request, pid: str):
        p = owner_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        role = form.get('role')
        uname = str(form.get('username', '')).strip().lstrip('@').lower()
        if role not in INVITE_ROLES:
            raise HTTPException(400, 'Choose a role')
        with db() as c:
            who = c.execute('SELECT id,name FROM users WHERE username=?', (uname,)).fetchone()
            if not who:
                return team_page(request, p, error=f'No Civora user called "{uname}". Send them an invite link instead.')
            if who['id'] == p['owner_id']:
                return team_page(request, p, error='That is the project owner.')
            c.execute('INSERT INTO civora_members_v270(project_id,user_id,role,added_by,added_at) VALUES(?,?,?,?,?) '
                      'ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role', (pid, who['id'], role, require(request)['id'], int(time.time())))
            log(c, pid, require(request)['id'], f'Added {who["name"]} as {role_label(role)}')
        return RedirectResponse(f'/projects/{pid}/team?done=added', 303)

    @app.post('/projects/{pid}/team/role')
    async def change_role(request: Request, pid: str):
        owner_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        role = form.get('role')
        if role not in INVITE_ROLES:
            raise HTTPException(400, 'Choose a role')
        with db() as c:
            cur = c.execute('UPDATE civora_members_v270 SET role=? WHERE project_id=? AND user_id=?', (role, pid, str(form.get('user_id', ''))))
            if not cur.rowcount:
                raise HTTPException(404, 'Member not found')
            who = c.execute('SELECT name FROM users WHERE id=?', (str(form.get('user_id', '')),)).fetchone()
            log(c, pid, require(request)['id'], f'Changed {who["name"] if who else "a member"} to {role_label(role)}')
        return RedirectResponse(f'/projects/{pid}/team?done=role', 303)

    @app.post('/projects/{pid}/team/remove')
    async def remove_member(request: Request, pid: str):
        owner_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            who = c.execute('SELECT name FROM users WHERE id=?', (str(form.get('user_id', '')),)).fetchone()
            cur = c.execute('DELETE FROM civora_members_v270 WHERE project_id=? AND user_id=?', (pid, str(form.get('user_id', ''))))
            if not cur.rowcount:
                raise HTTPException(404, 'Member not found')
            log(c, pid, require(request)['id'], f'Removed {who["name"] if who else "a member"}')
        return RedirectResponse(f'/projects/{pid}/team?done=removed', 303)

    def _invite(raw):
        with db() as c:
            inv = c.execute('SELECT i.*, p.name AS project_name, p.owner_id, u.name AS inviter FROM civora_invites_v270 i '
                            'JOIN projects p ON p.id=i.project_id JOIN users u ON u.id=i.created_by WHERE i.token_hash=?',
                            (hashlib.sha256(str(raw).encode()).hexdigest(),)).fetchone()
        if not inv:
            raise HTTPException(404, 'This invite link is not valid.')
        if inv['used_by']:
            raise HTTPException(410, 'This invite link has already been used. Ask for a new one.')
        if inv['expires'] < time.time():
            raise HTTPException(410, 'This invite link has expired. Ask for a new one.')
        return inv

    @app.get('/invite/{raw}')
    def open_invite(request: Request, raw: str):
        inv = _invite(raw)
        u = current_user(request)
        en, ta, desc, colour = ROLES[inv['role']]
        head = (f'<div class="card form" style="max-width:560px"><span class="eyebrow">INVITATION · அழைப்பு</span><h1>Join “{esc(inv["project_name"])}”</h1>'
                f'<p>{esc(inv["inviter"])} invited you as <b style="color:{colour}">{esc(en)}</b> ({esc(ta)}).</p><p class="muted">{esc(desc)}</p>')
        if not u:
            nxt = _urlq(f'/invite/{raw}')
            return layout(request, 'Invitation', head + f'<div class="actions"><a class="cv-btn" href="/register?next={nxt}">Create free account</a>'
                                                         f'<a class="cv-btn ghost" href="/login?next={nxt}">I already have an account</a></div></div>')
        return layout(request, 'Invitation', head + f'<form method="post" action="/invite/{esc(raw)}"><input type="hidden" name="csrf_token" value="{csrf(request)}">'
                                                     f'<div class="actions"><button class="cv-btn">Join project as {esc(en)}</button></div></form></div>')

    @app.post('/invite/{raw}')
    async def accept_invite(request: Request, raw: str):
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        inv = _invite(raw)
        pid = inv['project_id']
        with db() as c:
            if u['id'] != inv['owner_id']:
                existing = c.execute('SELECT role FROM civora_members_v270 WHERE project_id=? AND user_id=?', (pid, u['id'])).fetchone()
                if not existing:
                    c.execute('INSERT INTO civora_members_v270(project_id,user_id,role,added_by,added_at) VALUES(?,?,?,?,?)',
                              (pid, u['id'], inv['role'], inv['created_by'], int(time.time())))
                    log(c, pid, u['id'], f'Joined as {role_label(inv["role"])} (invite link)')
            c.execute('UPDATE civora_invites_v270 SET used_by=?, used_at=? WHERE token_hash=? AND used_by IS NULL',
                      (u['id'], int(time.time()), hashlib.sha256(raw.encode()).hexdigest()))
        return RedirectResponse(f'/projects/{pid}/workflow', 303)

    @app.post('/projects/{pid}/signoff')
    async def signoff(request: Request, pid: str):
        owned_project(request, pid)                       # design permission enforced centrally
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        note = str(form.get('note', '')).strip()[:500]
        if len(note) < 5:
            raise HTTPException(400, 'Write a short review note (what you checked).')
        if form.get('confirm') != 'yes':
            raise HTTPException(400, 'Tick the confirmation box to sign off.')
        with db() as c:
            role = project_role(c, pid, u['id'])
            c.execute('INSERT INTO civora_signoff_v270(project_id,user_id,role,note,at) VALUES(?,?,?,?,?)', (pid, u['id'], role, note, int(time.time())))
            log(c, pid, u['id'], 'Signed off the design review', note[:120])
        return RedirectResponse(f'/projects/{pid}/workflow#structure', 303)


def _urlq(s):
    from urllib.parse import quote
    return quote(s, safe='')
