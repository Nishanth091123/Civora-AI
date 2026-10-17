import os, sqlite3, secrets, hashlib, hmac, time, json, uuid, re, math
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext
from fastapi.responses import Response

BASE=Path(__file__).resolve().parent
# v3.6.0: data folder from CIVORA_DATA_DIR (persistent disk) and automatic restore of the
# cloud backup BEFORE the database is opened. On a normal PC this is still BASE/'data'.
import persistence_v360
DATA=persistence_v360.prepare()
FILES=DATA/'uploads'; FILES.mkdir(exist_ok=True)
DB=DATA/'buildquant.db'
KEY_FILE=DATA/'session.key'
SECRET=persistence_v360.secret_key(KEY_FILE)
app=FastAPI(title='Civora AI',docs_url=None,redoc_url=None)
app.add_middleware(SessionMiddleware,secret_key=SECRET,same_site='lax',https_only=False,max_age=86400)
pwd=CryptContext(schemes=['bcrypt'],deprecated='auto')

import dbcompat, filestore
@contextmanager
def db():
    # v3.7.0: PostgreSQL when DATABASE_URL is set (Neon / Supabase), else the SQLite file as before
    # v3.8.0: every DELETE goes through the Recycle Bin (admin_v380.BinConnection)
    import admin_v380
    if dbcompat.is_postgres():
        with dbcompat.pg_session() as conn:
            yield admin_v380.BinConnection(conn)
        return
    conn=sqlite3.connect(DB,timeout=30)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=30000')
    try:
        yield admin_v380.BinConnection(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally: conn.close()

# v3.8.0: many users at once on SQLite - WAL lets readers and one writer work together
if not dbcompat.is_postgres():
    try:
        _w=sqlite3.connect(DB,timeout=30);_w.execute('PRAGMA journal_mode=WAL');_w.execute('PRAGMA synchronous=NORMAL');_w.close()
    except sqlite3.Error as _ex:
        print(f'[Civora] WAL mode not enabled: {_ex}')

# v2.4.2 data safety: one consistent database backup per day, taken BEFORE any
# table is created or altered below. A backup problem is reported, never fatal.
import data_safety
if not dbcompat.is_postgres():data_safety.daily_startup_backup(DB, DATA / 'backups' / 'db' if os.environ.get('CIVORA_DATA_DIR') else BASE / 'backups' / 'db')

with db() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,type TEXT NOT NULL,location TEXT NOT NULL,area REAL NOT NULL,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),original_name TEXT NOT NULL,stored_name TEXT NOT NULL,content_type TEXT,created INTEGER NOT NULL);''')

# Safe, additive migration: existing users/projects/uploads remain intact.
with db() as c:
    columns={r['name'] for r in c.execute('PRAGMA table_info(users)')}
    if 'username' not in columns:
        c.execute('ALTER TABLE users ADD COLUMN username TEXT')
    existing={r['username'].lower() for r in c.execute('SELECT username FROM users WHERE username IS NOT NULL')}
    for old in c.execute('SELECT id,email FROM users WHERE username IS NULL').fetchall():
        base=re.sub(r'[^a-z0-9_]', '_', (old['email'].split('@')[0]).lower())[:22].strip('_') or 'member'
        candidate=base; i=2
        while candidate in existing:
            candidate=f'{base}_{i}'; i+=1
        c.execute('UPDATE users SET username=? WHERE id=?',(candidate,old['id']))
        existing.add(candidate)
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users(username)')
    c.execute("""CREATE TABLE IF NOT EXISTS remember_tokens (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires INTEGER NOT NULL)""")

USERNAME_PATTERN=re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{2,29}$')
REMEMBER_SECONDS=30*24*3600

def login_response(request, uid, remember, next_url=''):
    import team_v270
    request.session.clear()
    request.session['uid']=uid
    response=RedirectResponse(team_v270.safe_next(next_url) or '/projects',303)
    if remember:
        token=secrets.token_urlsafe(40)
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        with db() as c:
            c.execute('DELETE FROM remember_tokens WHERE expires<?',(int(time.time()),))
            c.execute('INSERT INTO remember_tokens VALUES(?,?,?)',(token_hash,uid,int(time.time())+REMEMBER_SECONDS))
        response.set_cookie('bq_remember',token, max_age=REMEMBER_SECONDS,httponly=True,samesite='lax',secure=False,path='/')
    return response

def esc(s):
    import html
    return html.escape(str(s),quote=True)

def current_user(request):
    uid=request.session.get('uid')
    if not uid:
        token=request.cookies.get('bq_remember','')
        if token and len(token)<256:
            token_hash=hashlib.sha256(token.encode()).hexdigest()
            with db() as c:
                row=c.execute('SELECT user_id FROM remember_tokens WHERE token_hash=? AND expires>?',(token_hash,int(time.time()))).fetchone()
            uid=row['user_id'] if row else None
    if not uid:return None
    with db() as c:
        u=c.execute('SELECT id,name,email,username FROM users WHERE id=?',(uid,)).fetchone()
    import admin_v380
    admin_v380.note_user(u)
    return u

def csrf(request):
    if 'csrf' not in request.session:request.session['csrf']=secrets.token_urlsafe(24)
    return request.session['csrf']

def check_csrf(request,token):
    if not hmac.compare_digest(str(request.session.get('csrf','')),str(token)):
        raise HTTPException(403,'Invalid form token')

def layout(request,title,body):
    # v3.0: every page renders in the Civora 3.0 shell, with the project context bar on project pages
    # and the user's Guided/Expert + language preferences.
    import ui_shell, team_v270, settings_v300
    u=current_user(request)
    path=request.url.path
    m=re.match(r'^/projects/([0-9a-fA-F-]{36})(?:/|$)',path)
    pid=m.group(1) if m else None
    ctx=None;prefs={'mode':'guided','lang':'en'}
    with db() as c:
        if u:
            prefs=settings_v300.get_prefs(c,u['id'])
            role=team_v270.project_role(c,pid,u['id']) if pid else None
            if pid and not role:pid=None
            if pid:
                import workflow_v250
                p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
                st=workflow_v250.project_status(c,pid)
                nxt=next((k for k in ui_shell.STEP_KEYS if k not in st['done']),None)
                ctx={'id':pid,'name':p['name'],'type':p['type'],'location':p['location'],'stage':nxt,'revisions':st['boq_count'],'role':role,'path':path,'admin':__import__('admin_v380').is_site_owner(u)}
            else:
                r=team_v270.accessible_projects(c,u['id'],limit=1)
                pid=r[0]['id'] if r else None
    auth_page=title in ('Sign in','Login','Create Account')
    if u and not auth_page:body=persistence_v360.banner_html()+body   # v3.6.0: warn when data is not safe
    return HTMLResponse(ui_shell.page(title,body,user=u,pid=pid,path=path,csrf_token=csrf(request),auth_page=auth_page,query=request.query_params.get('q',''),context=ctx,prefs=prefs))

@app.get('/')
def home(request:Request):
    # v3.0 dashboard: the big "How big is your building?" question + command-center tiles.
    import studio_v300, settings_v300
    u=current_user(request)
    data={};prefs={}
    if u:
        with db() as c:
            data=studio_v300.dashboard_data(c,u)
            prefs=settings_v300.get_prefs(c,u['id'])
    return layout(request,'Home',studio_v300.dashboard_html(u,data,csrf(request),prefs))

@app.get('/register')
def register_form(request:Request):
    import team_v270
    nxt=esc(team_v270.safe_next(request.query_params.get('next','')))
    return layout(request,'Create Account',f'''<div class="card form"><h2>Create your free account</h2><p class="muted">Just your name, username and password. No email required.</p><form method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><input type="hidden" name="next" value="{nxt}"><label>Your name</label><input name="name" required maxlength="100" autocomplete="name" placeholder="Your name"><label>Choose username</label><input name="username" required minlength="3" maxlength="30" pattern="[A-Za-z][A-Za-z0-9_]{{2,29}}" autocomplete="username" placeholder="Example: nishanth_s"><p class="hint">3–30 characters; start with a letter, then letters, numbers or underscore.</p><label>Create password</label><input type="password" name="password" minlength="10" maxlength="128" autocomplete="new-password" required><p class="hint">At least 10 characters. Use a unique password.</p><label class="checkline"><input type="checkbox" name="remember" value="yes" checked> Keep me signed in on this device (30 days)</label><div class="actions"><button>Create Account</button><a href="/login">Already have an account?</a></div></form><div class="guest"><b>Just exploring?</b><p>No account needed for a sample wall volume estimate.</p><a href="/guest">Continue as Guest →</a></div></div>''')

@app.post('/register')
def register(request:Request,name:str=Form(...),username:str=Form(...),password:str=Form(...),remember:str=Form(''),csrf_token:str=Form(...),next:str=Form('')):
    check_csrf(request,csrf_token)
    username=username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username) or len(password)<10 or len(password)>128 or len(name.strip())<2:
        raise HTTPException(400,'Invalid name, username or password')
    uid=str(uuid.uuid4())
    # Legacy email column is retained for backward-compatible migration, not collected from users.
    internal_email=f'{uid}@internal.buildquant.invalid'
    try:
        with db() as c:
            c.execute('INSERT INTO users(id,name,email,password,username) VALUES(?,?,?,?,?)',(uid,name.strip()[:100],internal_email,pwd.hash(password),username))
    except sqlite3.IntegrityError:
        return layout(request,'Username Taken','<div class="card form"><h2>Username already taken</h2><p>Please choose another username.</p><a class="primary" href="/register">Try Again</a></div>')
    return login_response(request,uid,remember=='yes',next)

@app.get('/login')
def login_form(request:Request):
    import team_v270
    nxt=esc(team_v270.safe_next(request.query_params.get('next','')))
    return layout(request,'Login',f'''<div class="card form"><h2>Welcome back</h2><p class="muted">Sign in with your username. Existing v0.1 users can also use their original email.</p><form method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><input type="hidden" name="next" value="{nxt}"><label>Username</label><input name="identifier" required autocomplete="username" placeholder="Your username"><label>Password</label><input type="password" name="password" required autocomplete="current-password"><label class="checkline"><input type="checkbox" name="remember" value="yes" checked> Remember me for 30 days</label><div class="actions"><button>Continue →</button><a href="/register">Create free account</a></div></form><div class="guest"><b>Try without signing in</b><p>Guest mode is for temporary estimates; saving projects needs an account.</p><a href="/guest">Explore as Guest →</a></div></div>''')

@app.post('/login')
def login(request:Request,identifier:str=Form(...),password:str=Form(...),remember:str=Form(''),csrf_token:str=Form(...),next:str=Form('')):
    check_csrf(request,csrf_token)
    identifier=identifier.strip().lower()
    with db() as c:
        u=c.execute('SELECT * FROM users WHERE username=? OR email=?',(identifier,identifier)).fetchone()
    if not u or not pwd.verify(password,u['password']):
        return layout(request,'Sign in failed','<div class="card form"><h2>Could not sign in</h2><p>Check your username and password.</p><a class="primary" href="/login">Try Again</a></div>')
    return login_response(request,u['id'],remember=='yes',next)

@app.post('/logout')
def logout(request:Request,csrf_token:str=Form(...)):
    check_csrf(request,csrf_token)
    token=request.cookies.get('bq_remember','')
    if token:
        with db() as c:c.execute('DELETE FROM remember_tokens WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
    request.session.clear()
    response=RedirectResponse('/',303)
    response.delete_cookie('bq_remember',path='/')
    return response

@app.get('/guest')
def guest(request:Request):
    return layout(request,'Guest Preview',f'''<span class="eyebrow">PUBLIC PREVIEW</span><h1>Explore Civora AI</h1><p class="muted">Try one basic measurement calculation. Project files, saved estimates, material studio and reports require a free account.</p><div class="grid"><div class="card form"><h2>Simple Wall Volume</h2><form action="/guest/estimate" method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><label>Length (ft)</label><input name="length" type="number" min="0.01" max="100000" step="any" required><label>Height (ft)</label><input name="height" type="number" min="0.01" max="100000" step="any" required><label>Thickness (ft)</label><input name="thickness" type="number" min="0.01" max="100" step="any" required><div class="actions"><button>Calculate Volume →</button></div></form></div><div class="preview-lock"><h2>Unlock your project workspace</h2><p>✓ Save your projects<br>✓ Upload drawings and photos<br>✓ Work-wise material estimation<br>✓ Project history and reports</p><a class="primary" href="/register">Create Free Account →</a><p class="hint">Guest preview does not save data or allow private project access.</p></div></div>''')

@app.post('/guest/estimate')
def guest_estimate(request:Request,length:float=Form(...),height:float=Form(...),thickness:float=Form(...),csrf_token:str=Form(...)):
    import math
    check_csrf(request,csrf_token)
    if not all(math.isfinite(v) for v in (length,height,thickness)) or not (0<length<=1e5 and 0<height<=1e5 and 0<thickness<=100):
        raise HTTPException(400,'Invalid dimensions')
    cft=length*height*thickness; cum=cft/35.3146667
    return layout(request,'Guest Result',f'''<div class="card form"><span class="eyebrow">GUEST PREVIEW RESULT</span><h1>Wall Volume</h1><h2>{cum:,.3f} m³</h2><p>{cft:,.2f} cubic feet</p><p class="muted">Gross geometric volume only. Openings, mortar and material quantities are not included. This result is not saved.</p><div class="actions"><a class="primary" href="/guest">Try Again</a><a href="/register">Create Free Account →</a></div></div>''')

def require(request):
    u=current_user(request)
    if not u:raise HTTPException(401,'Please log in first')
    return u

@app.get('/projects')
def projects(request:Request):
    # v3.0 portfolio: table / card view, search, type and status filters.
    import studio_v300
    u=require(request)
    qp=request.query_params
    q=qp.get('q','').strip()[:100];ftype=qp.get('type','');fstatus=qp.get('status','');view='cards' if qp.get('view')=='cards' else 'table'
    if ftype not in studio_v300.TYPES:ftype=''
    if fstatus not in studio_v300.STATUS:fstatus=''
    with db() as c:
        if q:
            like='%'+q.replace('%','').replace('_','')+'%'
            rows=studio_v300.project_rows(c,u['id'],'p.name LIKE ? OR p.type LIKE ? OR p.location LIKE ?',(like,like,like))
        else:
            rows=studio_v300.project_rows(c,u['id'])
    title=f'Search results for “{esc(q)}”' if q else 'Projects'
    gone='<div class="cv-banner" style="margin-bottom:12px">Project deleted. A database backup was made first (backups\\db).</div>' if qp.get('deleted')=='1' else ''
    return layout(request,'My Projects',gone+f'<div class="cv-ph"><div><span class="eyebrow">PROJECTS · திட்டங்கள்</span><h1>{title}</h1><div class="meta">{len(rows)} project(s) · owned and shared with you</div></div><a class="cv-btn" href="/projects/new">＋ New Project</a></div>'+studio_v300.portfolio_html(rows,q,ftype,fstatus,view))

PROJECT_TYPES=['Residential','Commercial','Industrial','Infrastructure','Custom']

@app.get('/projects/new')
def new_project_form(request:Request):
    # v3.0 guided wizard (same POST fields as before, plus optional floors / how to start)
    import studio_v300
    require(request)
    chosen=request.query_params.get('type','Residential')
    if chosen not in PROJECT_TYPES:chosen='Residential'
    return layout(request,'New Project',studio_v300.wizard_html(csrf(request),chosen,request.query_params.get('q','')[:120],request.query_params.get('next','')))

@app.post('/projects/new')
def new_project(request:Request,name:str=Form(...),type:str=Form(...),location:str=Form(...),area:float=Form(...),csrf_token:str=Form(...),next:str=Form(''),floors:int=Form(1)):
    u=require(request);check_csrf(request,csrf_token)
    if not 0<area<=1e8 or type not in PROJECT_TYPES:raise HTTPException(400,'Invalid project details')
    pid=str(uuid.uuid4())
    with db() as c:c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?)',(pid,u['id'],name.strip()[:120],type,location.strip()[:120],area,int(time.time())))
    if next=='quick':
        # v3.0 wizard "Area only": run Quick Estimate straight away (same engine as /quick)
        import quick_v280
        try:
            a,fl=quick_v280.parse_quick({'area':area,'floors':floors})
            inp,opts,result=quick_v280.quick_estimate(a,fl,takeoff)
        except ValueError:
            return RedirectResponse(f'/projects/{pid}/smart',303)
        with db() as c:p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
        bid=quick_v280.save_quick(db,store_upload,p,u,inp,opts,result)
        return RedirectResponse(f'/projects/{pid}/workflow?estimate={bid}',303)
    return RedirectResponse(f'/projects/{pid}/smart' if next=='smart' else '/projects/'+pid,303)

def owned_project(request,pid):
    # v2.7.0: owner OR team member. One central check for every module:
    # GET = any member; changes need Owner/Engineer/Colleague; design sign-off needs Owner/Engineer;
    # team management and deleting uploaded files need the Owner.
    import team_v270
    u=require(request)
    with db() as c:
        p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
        role=team_v270.project_role(c,pid,u['id']) if p else None
    if not p or not role:raise HTTPException(404,'Project not found')
    import admin_v380
    try:
        with db() as c:admin_v380.guard(c,request,p,u['id'])
    except PermissionError as ex:raise HTTPException(403,str(ex))
    need=team_v270.required_permission(request.method,request.url.path)
    if not team_v270.allowed(role,need):
        raise HTTPException(403,f'Your role in this project is {team_v270.role_label(role)}. Only {team_v270.NEED_LABEL[need]} can do this.')
    try:
        request.state.cv_actor=(u['id'],pid)
        request.state.cv_role=role
        request.state.cv_admin=admin_v380.is_site_owner(u)
    except Exception:pass
    return p

@app.get('/projects/{pid}')
def project_detail(request:Request,pid:str):
    # v3.0 project workspace: next step, 6 workflow cards, files and tools (context bar comes from layout)
    import studio_v300, workflow_v250
    p=owned_project(request,pid)
    role=getattr(request.state,'cv_role','owner')
    with db() as c:
        files=c.execute('SELECT * FROM uploads WHERE project_id=? ORDER BY created DESC',(pid,)).fetchall()
        st=workflow_v250.project_status(c,pid)
    return layout(request,p['name'],studio_v300.workspace_html(p,st,csrf(request),role,files))

def store_upload(pid,filename,content,content_type):
    """Validate and save one uploaded file for a project (shared by upload and Smart Estimate). Returns file id."""
    suffix=Path(filename or '').suffix.lower()
    if suffix not in {'.png','.jpg','.jpeg','.pdf','.dxf','.xlsx','.csv'}:raise HTTPException(400,'Unsupported file type')
    if len(content)>30*1024*1024:raise HTTPException(413,'Max upload size 30MB')
    if suffix=='.pdf' and not content.startswith(b'%PDF-'):raise HTTPException(400,'Invalid PDF')
    if suffix=='.png' and not content.startswith(b'\x89PNG\r\n\x1a\n'):raise HTTPException(400,'Invalid PNG')
    if suffix in {'.jpg','.jpeg'} and not content.startswith(b'\xff\xd8\xff'):raise HTTPException(400,'Invalid JPEG')
    if suffix=='.dxf' and content.startswith(b'AutoCAD Binary DXF'):
        raise HTTPException(400,'Binary DXF unsupported. Export as ASCII DXF (R2010 or earlier) from CAD software.')
    fid=str(uuid.uuid4()); stored=fid+suffix
    filestore.save(FILES,stored,content)        # v3.7.0: also kept in PostgreSQL when online
    with db() as c:c.execute('INSERT INTO uploads VALUES(?,?,?,?,?,?)',(fid,pid,Path(filename or 'upload').name[:180],stored,content_type,int(time.time())))
    return fid

@app.post('/projects/{pid}/upload')
async def upload(request:Request,pid:str,file:UploadFile=File(...),csrf_token:str=Form(...),next:str=Form('')):
    owned_project(request,pid);check_csrf(request,csrf_token)
    content=await file.read(30*1024*1024+1)
    fid=store_upload(pid,file.filename,content,file.content_type)
    if next=='studio' and Path(file.filename or '').suffix.lower() in {'.pdf','.png','.jpg','.jpeg','.dxf'}:
        return RedirectResponse(f'/projects/{pid}/studio/{fid}',303)
    if next=='studio':
        return RedirectResponse(f'/projects/{pid}',303)
    if Path(file.filename or '').suffix.lower() in {'.pdf','.png','.jpg','.jpeg','.dxf'}:
        return RedirectResponse(f'/projects/{pid}/drawings/{fid}',303)
    return RedirectResponse('/projects/'+pid,303)

@app.get('/files/{fid}')
def download(request:Request,fid:str):
    u=require(request)
    import team_v270
    with db() as c:
        f=c.execute('SELECT * FROM uploads WHERE id=?',(fid,)).fetchone()
        if f and not team_v270.project_role(c,f['project_id'],u['id']):f=None
    if not f:raise HTTPException(404,'File not found')
    return FileResponse(filestore.ensure(FILES,f['stored_name']),filename=f['original_name'],media_type='application/octet-stream')

@app.get('/projects/{pid}/estimate')
def estimate_form(request:Request,pid:str):
    p=owned_project(request,pid)
    return layout(request,'Wall Estimator',f'<div class="card form"><h1>Wall Volume Estimator</h1><p class="muted">Geometric quantity only; excludes openings. This is not a full material BOQ.</p><form method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><label>Length (ft)</label><input name="length" type="number" min="0.01" max="100000" step="any" required><label>Height (ft)</label><input name="height" type="number" min="0.01" max="100000" step="any" required><label>Thickness (ft)</label><input name="thickness" type="number" min="0.01" max="100" step="any" required><div class="actions"><button>Calculate</button><a href="/projects/{pid}">Back to Project</a></div></form></div>')

@app.post('/projects/{pid}/estimate')
def estimate(request:Request,pid:str,length:float=Form(...),height:float=Form(...),thickness:float=Form(...),csrf_token:str=Form(...)):
    p=owned_project(request,pid);check_csrf(request,csrf_token)
    if not all(__import__('math').isfinite(v) for v in (length,height,thickness)) or not (0<length<=1e5 and 0<height<=1e5 and 0<thickness<=100):raise HTTPException(400,'Invalid dimensions')
    cft=length*height*thickness;cum=cft/35.3146667
    return layout(request,'Wall Estimate',f'<div class="card form"><h1>Calculated Wall Volume</h1><h2>{cum:,.3f} m³</h2><p>{cft:,.2f} cubic feet</p><p class="muted">Gross wall volume only. Deduct openings and use approved specifications for brick, mortar and cost quantities.</p><a class="primary" href="/projects/{pid}/estimate">Calculate Again</a></div>')

# Version 0.3: additive, owner-scoped material measurement records.
with db() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS material_estimates (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        work_type TEXT NOT NULL, length_m REAL NOT NULL, height_m REAL NOT NULL,
        thickness_m REAL NOT NULL, openings_m2 REAL NOT NULL,
        net_volume_m3 REAL NOT NULL, created INTEGER NOT NULL)""")

@app.get('/materials')
def material_studio(request:Request):
    u=require(request)
    with db() as c:
        import team_v270
        rows=team_v270.accessible_projects(c,u['id'])
    projects_html=''.join(f'<a class="stagecard" href="/projects/{p["id"]}/materials"><h3>{esc(p["name"])} →</h3><p>{esc(p["type"])} · Open material workspace</p></a>' for p in rows)
    return layout(request,'Material Studio',f'''<span class="eyebrow">QUANTITY WORKSPACE</span><h1>Material Studio</h1><p class="muted">Select a saved project. Version 0.6 adds consistent measurement entry and project material takeoffs.</p><div class="grid">{projects_html or '<div class="card">Create a project first to begin measurements.</div>'}</div><div class="actions"><a class="primary" href="/projects/new">＋ New Project</a></div>''')

@app.get('/projects/{pid}/materials')
def project_materials(request:Request,pid:str):
    p=owned_project(request,pid)
    with db() as c:
        rows=c.execute('SELECT * FROM material_estimates WHERE project_id=? ORDER BY created DESC',(pid,)).fetchall()
    tr=''.join(f'<tr><td>{esc(r["work_type"])}</td><td>{r["length_m"]:,.2f} × {r["height_m"]:,.2f} × {r["thickness_m"]:,.3f}</td><td>{r["openings_m2"]:,.2f}</td><td>{r["net_volume_m3"]:,.3f} m³</td><td><form method="post" action="/projects/{pid}/materials/{r["id"]}/delete" onsubmit="return confirm(&quot;Permanently delete this measurement?&quot;)"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button type="submit" class="small" style="background:#a33333">Delete</button></form></td></tr>' for r in rows)
    total=sum(r['net_volume_m3'] for r in rows)
    return layout(request,'Project Materials',f'''<span class="eyebrow">{esc(p['type'])} / MATERIAL STUDIO</span><h1>{esc(p['name'])} · Measurements</h1><p class="muted">Record all work categories using a consistent length × width × depth format. Measurements are converted to metres before saving. For surface-only works, the calculated volume is geometric reference only; use Material Takeoff for area-based quantities.</p><div class="grid"><div class="card"><h2>Add a Measurement</h2><form method="post" action="/projects/{pid}/materials/preview"><input type="hidden" name="csrf_token" value="{csrf(request)}"><label>Work type</label><select id="measurement-work" name="work_type"><option value="Masonry">Brick Masonry</option><option value="AAC Masonry">AAC Masonry</option><option value="Concrete">Concrete</option><option value="PCC">PCC</option><option value="RCC">RCC</option><option value="Plastering">Plastering</option><option value="Flooring">Flooring</option><option value="Painting">Painting</option><option value="Excavation">Excavation</option><option value="Backfill">Backfill</option><option value="Shuttering">Shuttering</option><option value="Waterproofing">Waterproofing</option><option value="Screed">Screed</option><option value="Reinforcement Steel">Reinforcement Steel</option><option value="Other">Other</option></select><label>Measurement unit</label><select id="measurement-unit" name="unit"><option value="m">Metres (m)</option><option value="ft">Feet (ft)</option><option value="in">Inches (in)</option><option value="mm">Millimetres (mm)</option></select><p class="hint">All dimension fields below use the selected unit. Opening deductions use its square unit.</p><label>Length</label><input type="number" name="length_m" min="0.001" max="100000" step="any" required><label>Height / Width</label><input type="number" name="height_m" min="0.001" max="100000" step="any" required><label>Thickness / Depth</label><input id="measurement-depth" type="number" name="thickness_m" min="0.001" max="1000" step="any" required><label>Openings / deductions (selected unit²)</label><input type="number" name="openings_m2" min="0" max="100000000" step="any" value="0" required><div class="actions"><button>Calculate &amp; Preview →</button></div></form></div><div class="card"><span class="eyebrow">SAVED MEASUREMENTS</span><h1>{len(rows)}</h1><p>Total combined geometric volume: <b>{total:,.3f} m³</b></p><div class="notice">Concrete and masonry volumes are different work items. Do not use their combined total as a material order quantity.</div><p class="muted">Next: create material takeoffs from your saved project.</p></div></div><div class="card" style="margin-top:18px"><h2>Measurement Register</h2><div class="scroll"><table class="reporttable"><thead><tr><th>Work</th><th>Dimensions (m)</th><th>Deduction (m²)</th><th>Net quantity (m³)</th><th>Action</th></tr></thead><tbody>{tr or '<tr><td colspan="5">No measurements saved yet.</td></tr>'}</tbody></table></div></div><div class="actions"><a class="primary" href="/projects/{pid}/takeoff">Open Material Takeoff →</a><a href="/projects/{pid}">← Back to Project</a></div><script>(function(){{const w=document.getElementById('measurement-work'),u=document.getElementById('measurement-unit'),d=document.getElementById('measurement-depth');const defaults={{'Masonry':.23,'AAC Masonry':.2,'Concrete':.15,'PCC':.1,'RCC':.15,'Plastering':.012,'Flooring':.01,'Painting':.001,'Excavation':.5,'Backfill':.3,'Shuttering':.018,'Waterproofing':.002,'Screed':.04,'Reinforcement Steel':.1,'Other':.1}};function update(){{d.value=Number((defaults[w.value]/{{m:1,ft:.3048,in:.0254,mm:.001}}[u.value]).toPrecision(7))}}w.addEventListener('change',update);u.addEventListener('change',update);update()}})();</script>''')

def validated_measurement(work_type,length_m,height_m,thickness_m,openings_m2,unit):
    from engineering import UNIT_TO_M
    if unit not in UNIT_TO_M: raise HTTPException(400,'Unsupported measurement unit')
    factor=UNIT_TO_M[unit]
    a,b,d,o=length_m*factor,height_m*factor,thickness_m*factor,openings_m2*factor*factor
    values=(a,b,d,o)
    if work_type not in {'Masonry','AAC Masonry','Concrete','PCC','RCC','Plastering','Flooring','Painting','Excavation','Backfill','Shuttering','Waterproofing','Screed','Reinforcement Steel','Other'} or not all(math.isfinite(x) for x in values) or not (0<a<=1e5 and 0<b<=1e5 and 0<d<=1000 and 0<=o<a*b):
        raise HTTPException(400,'Invalid dimensions or opening area')
    volume=(a*b-o)*d
    if volume>1e12: raise HTTPException(400,'Quantity exceeds allowed limit')
    return a,b,d,o,volume

@app.post('/projects/{pid}/materials/preview')
def preview_material(request:Request,pid:str,work_type:str=Form(...),length_m:float=Form(...),height_m:float=Form(...),thickness_m:float=Form(...),openings_m2:float=Form(0),unit:str=Form('m'),csrf_token:str=Form(...)):
    p=owned_project(request,pid);check_csrf(request,csrf_token)
    a,b,d,o,v=validated_measurement(work_type,length_m,height_m,thickness_m,openings_m2,unit)
    hidden=''.join(f'<input type="hidden" name="{k}" value="{esc(str(val))}">' for k,val in dict(work_type=work_type,length_m=length_m,height_m=height_m,thickness_m=thickness_m,openings_m2=openings_m2,unit=unit).items())
    return layout(request,'Measurement Preview',f'''<div class="card form"><span class="eyebrow">PREVIEW ONLY · NOT SAVED</span><h1>Measurement Result</h1><p>{esc(work_type)} · {esc(p['name'])}</p><p>Dimensions: {a:,.3f} × {b:,.3f} × {d:,.3f} m</p><p>Deduction: {o:,.3f} m²</p><h2>Net volume: {v:,.4f} m³</h2><p class="hint">This is a geometric quantity preview. No database record has been created.</p><form method="post" action="/projects/{pid}/materials/commit"><input type="hidden" name="csrf_token" value="{csrf(request)}">{hidden}<div class="actions"><button type="submit">Save Measurement →</button><a href="/projects/{pid}/materials">Discard / New Calculation</a></div></form></div>''')

@app.post('/projects/{pid}/materials/commit')
@app.post('/projects/{pid}/materials')
def save_material(request:Request,pid:str,work_type:str=Form(...),length_m:float=Form(...),height_m:float=Form(...),thickness_m:float=Form(...),openings_m2:float=Form(0),unit:str=Form('m'),csrf_token:str=Form(...)):
    owned_project(request,pid);check_csrf(request,csrf_token)
    a,b,d,o,v=validated_measurement(work_type,length_m,height_m,thickness_m,openings_m2,unit)
    with db() as c:
        c.execute('INSERT INTO material_estimates VALUES(?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),pid,work_type,a,b,d,o,v,int(time.time())))
    return RedirectResponse('/projects/'+pid+'/materials',303)


# Civora AI v0.4: additive, separate takeoff records; existing data unchanged.
from engineering import WORKS, takeoff, MORTAR_RATIOS, PCC_RATIOS, RCC_GRADES
import csv, io
from fastapi.responses import StreamingResponse

with db() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS material_takeoffs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        work_key TEXT NOT NULL, input_json TEXT NOT NULL, result_json TEXT NOT NULL, created INTEGER NOT NULL)""")

@app.get('/favicon.svg')
def favicon():
    svg='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="15" fill="#0b2541"/><path d="M12 31 32 13l20 18v21H12Z" fill="none" stroke="#36b8ff" stroke-width="5" stroke-linejoin="round"/><path d="M25 52V34h14v18" fill="none" stroke="#fff" stroke-width="5"/><circle cx="49" cy="15" r="7" fill="#27d4a6"/></svg>'''
    return Response(svg,media_type='image/svg+xml',headers={'Cache-Control':'no-cache'})

@app.get('/projects/{pid}/takeoff')
def takeoff_page(request:Request,pid:str):
    p=owned_project(request,pid)
    with db() as c: rows=c.execute('SELECT * FROM material_takeoffs WHERE project_id=? ORDER BY created DESC',(pid,)).fetchall()
    opts=''.join(f'<option value="{k}">{esc(v)}</option>' for k,v in WORKS.items())
    ratio_opts=''.join(f'<option value="{r}" {"selected" if r=="1:6" else ""}>{r}</option>' for r in MORTAR_RATIOS)
    plaster_opts=''.join(f'<option value="{r}" {"selected" if r=="1:4" else ""}>{r}</option>' for r in MORTAR_RATIOS)
    pcc_opts=''.join(f'<option value="{r}" {"selected" if r=="1:4:8" else ""}>{r}</option>' for r in PCC_RATIOS)
    rcc_opts=''.join(f'<option value="{r}" {"selected" if r=="M20" else ""}>{r}</option>' for r in RCC_GRADES)
    history=''.join(f'<tr><td>{esc(json.loads(r["result_json"]).get("work", "Work"))}</td><td>{len(json.loads(r["result_json"]).get("items", []))}</td><td><a href="/projects/{pid}/takeoff/{r["id"]}">View details →</a> <form method="post" action="/projects/{pid}/takeoff/{r["id"]}/delete" style="display:inline" onsubmit="return confirm(&quot;Permanently delete this saved material calculation?&quot;)"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button type="submit" class="small" style="background:#a33333">Delete</button></form></td></tr>' for r in rows)
    return layout(request,'Material Takeoff',f'''<span class="eyebrow">CIVORA AI / MATERIAL INTELLIGENCE</span><h1>{esc(p['name'])} · Material Takeoff</h1><p class="muted">Choose a work category to see only relevant specifications. Dimensions use your selected unit. AAC thin-bed adhesive is not ordinary cement:sand mortar.</p><div class="grid"><div class="card"><h2>New material estimate</h2><form id="civora-takeoff-form" method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><label>Work category</label><select id="work-select" name="work">{opts}</select><label>Measurement unit</label><select name="unit"><option value="m">Metres (m)</option><option value="ft">Feet (ft)</option><option value="in">Inches (in)</option><option value="mm">Millimetres (mm)</option></select><p class="hint">Main dimensions use the selected unit; opening deductions use its square unit.</p><label>Length</label><input type="number" step="any" min="0.001" name="length" required><label>Height / Width</label><input type="number" step="any" min="0.001" name="width" required><label>Thickness / Depth</label><input type="number" step="any" min="0.001" id="takeoff-depth" name="depth" value="0.23" required><label>Openings / Deductions (selected unit²)</label><input type="number" step="any" min="0" name="openings" value="0" required><label>Wastage (%)</label><input type="number" step="any" min="0" max="30" name="waste" value="5" required>
<div hidden style="display:none" data-work="brickwork"><label>Brick masonry mortar ratio</label><select name="mortar_ratio">{ratio_opts}</select></div>
<div hidden style="display:none" data-work="plaster"><label>Plaster mortar ratio</label><select name="plaster_ratio">{plaster_opts}</select></div>
<div hidden style="display:none" data-work="pcc"><label>PCC nominal ratio</label><select name="pcc_ratio">{pcc_opts}</select></div>
<div hidden style="display:none" data-work="rcc"><label>RCC grade</label><select name="rcc_grade">{rcc_opts}</select>
<label>Supply method</label><select id="rcc-mode" name="rcc_mode"><option value="rmc">RMC – Concrete quantity only</option><option value="site">Site Mix – Separate materials</option></select>
<div data-rcc-site style="display:none"><label>Site mix calculation</label><select id="rcc-site-method" name="rcc_site_method"><option value="nominal">Illustrative nominal ratio (M20 only)</option><option value="design">Approved design mix (kg/m³)</option></select>
<div data-rcc-nominal><label>Nominal ratio (cement : sand : aggregate)</label><select name="rcc_nominal_ratio"><option value="1:1.5:3">1:1.5:3 – M20 illustrative only</option></select><p class="hint">For other grades use approved design mix. Nominal mix is not a structural approval.</p></div>
<div data-rcc-design style="display:none"><label>Approved cement (kg/m³)</label><input name="rcc_cement_kg" type="number" min="0" step="any" value="0"><label>Approved M-sand (kg/m³)</label><input name="rcc_msand_kg" type="number" min="0" step="any" value="0"><label>Approved aggregate (kg/m³)</label><input name="rcc_aggregate_kg" type="number" min="0" step="any" value="0"><label>Approved water (L/m³)</label><input name="rcc_water_l" type="number" min="0" step="any" value="0"><label>Admixture (kg/m³, optional)</label><input name="rcc_admixture_kg" type="number" min="0" step="any" value="0"></div>
<label>Optional steel planning allowance (kg/m³)</label><input name="steel_kg_m3" type="number" min="0" max="500" step="any" value="0"></div></div>
<div hidden style="display:none" data-work="brickwork"><h3>Brick dimensions</h3><p class="hint">Brick sizes and mortar joint are in metres.</p><label>Brick length (m)</label><input name="brick_length" type="number" step="any" min="0.001" value="0.19"><label>Brick height (m)</label><input name="brick_height" type="number" step="any" min="0.001" value="0.09"><label>Brick width (m)</label><input name="brick_width" type="number" step="any" min="0.001" value="0.09"><label>Mortar joint (m)</label><input name="joint" type="number" step="any" min="0" value="0.01"></div>
<div hidden style="display:none" data-work="blockwork"><h3>AAC block specifications</h3><p class="hint">Enter AAC block dimensions in mm. Thin-bed adhesive joint is 3–5 mm. No 1:5 or 1:6 cement mortar ratio.</p><label>AAC block length (mm)</label><input id="aac-l" name="aac_length_mm" type="number" min="1" step="any" value="600"><label>AAC block height (mm)</label><input id="aac-h" name="aac_height_mm" type="number" min="1" step="any" value="200"><label>AAC block width (mm)</label><input id="aac-w" name="aac_width_mm" type="number" min="1" step="any" value="200"><label>AAC adhesive joint thickness (mm)</label><select id="aac-j" name="aac_joint_mm"><option value="3">3 mm</option><option value="4" selected>4 mm</option><option value="5">5 mm</option></select><label>Dry adhesive powder coverage (kg/m²)</label><input name="adhesive_coverage" type="number" min="1" max="20" step="any" value="5" required><p class="hint">Illustrative starting coverage 5 kg/m². Check manufacturer datasheet and adjust. Bag size: 40 kg.</p></div>
<div hidden style="display:none" data-work="flooring"><label>Tile length (m)</label><input name="tile_length" type="number" step="any" value="0.6"><label>Tile width (m)</label><input name="tile_width" type="number" step="any" value="0.6"></div>
<div hidden style="display:none" data-work="painting"><label>Paint coats</label><input name="coats" type="number" step="1" value="2"><label>Paint coverage (m²/L/coat)</label><input name="paint_coverage" type="number" step="any" value="10"></div>
<div hidden style="display:none" data-work="waterproofing"><label>Manufacturer material coverage (kg/m²)</label><input name="material_coverage" type="number" min="0.01" max="30" step="any" value="1"></div>
<div hidden style="display:none" data-work="screed"><p class="hint">Screed uses the plaster ratio 1:4 by default; verify project specification.</p></div>
<div hidden style="display:none" data-work="steel"><label>Rebar diameter (mm)</label><input name="steel_diameter_mm" type="number" min="6" max="50" step="any" value="12"><label>Total cut length from approved BBS (m) – used if bar count is zero</label><input name="steel_total_length_m" type="number" min="0.001" step="any" value="100"><label>Number of bars (optional)</label><input name="steel_bar_count" type="number" min="0" step="1" value="0"><label>Cut length per bar (m, including laps/hooks)</label><input name="steel_cut_length_m" type="number" min="0" step="any" value="0"><p class="hint">When bar count is entered, weight = count × cut length × D²/162. Otherwise total BBS length is used. Geometric length/width fields are reference only.</p></div>
<div class="actions"><button>Calculate & Preview →</button></div></form></div><div class="card"><span class="eyebrow">PROJECT TAKEOFF HISTORY</span><h2>{len(rows)} saved calculations</h2><p>Only estimates explicitly saved after preview appear here.</p><div class="scroll"><table><thead><tr><th>Work</th><th>Materials</th><th>Result</th></tr></thead><tbody>{history or '<tr><td colspan="3">No takeoffs yet</td></tr>'}</tbody></table></div><div class="actions"><a class="primary" href="/projects/{pid}/takeoff/export.csv">Export CSV →</a><a href="/projects/{pid}">Back to Project</a></div><p class="hint">Preliminary estimation only; confirm product specs, openings and approved drawings.</p></div></div>
<script>(function(){{const f=document.getElementById('civora-takeoff-form'),w=document.getElementById('work-select'),unit=f?f.querySelector('[name="unit"]'):null,depth=f?f.querySelector('[name="depth"]'):null;if(!f||!w||!unit||!depth)return;const defaults={{brickwork:.23,blockwork:.20,pcc:.10,rcc:.15,plaster:.012,flooring:.01,painting:.001,excavation:.5,backfill:.3,shuttering:.018,waterproofing:.002,screed:.04,steel:.1}};let lastWork='',lastUnit=unit.value;function sync(){{document.querySelectorAll('[data-work]').forEach(e=>{{const show=e.dataset.work===w.value;e.hidden=!show;e.style.setProperty('display',show?'block':'none','important');e.querySelectorAll('input,select').forEach(x=>x.disabled=!show)}});if(lastWork!==w.value||lastUnit!==unit.value){{const factor={{m:1,ft:.3048,in:.0254,mm:.001}}[unit.value];if(factor && defaults[w.value]!==undefined)depth.value=Number((defaults[w.value]/factor).toPrecision(7));lastWork=w.value;lastUnit=unit.value}}}}w.addEventListener('change',sync);unit.addEventListener('change',sync);sync()}})();</script><script>(function(){{const f=document.getElementById('civora-takeoff-form'),m=document.getElementById('rcc-mode'),s=document.getElementById('rcc-site-method');if(!f||!m||!s)return;function sync(){{const site=m.value==='site',design=site&&s.value==='design';f.querySelectorAll('[data-rcc-site]').forEach(x=>x.style.display=site?'block':'none');f.querySelectorAll('[data-rcc-design]').forEach(x=>x.style.display=design?'block':'none');f.querySelectorAll('[data-rcc-nominal]').forEach(x=>x.style.display=site&&!design?'block':'none')}}m.addEventListener('change',sync);s.addEventListener('change',sync);sync()}})();</script>''')

@app.post('/projects/{pid}/takeoff')
def preview_takeoff(request:Request,pid:str,work:str=Form(...),length:float=Form(...),width:float=Form(...),depth:float=Form(...),openings:float=Form(0),waste:float=Form(5),brick_length:float=Form(.19),brick_height:float=Form(.09),brick_width:float=Form(.09),joint:float=Form(.01),tile_length:float=Form(.6),tile_width:float=Form(.6),coats:int=Form(2),paint_coverage:float=Form(10),adhesive_coverage:float=Form(5),unit:str=Form('m'),mortar_ratio:str=Form('1:6'),plaster_ratio:str=Form('1:4'),pcc_ratio:str=Form('1:4:8'),rcc_grade:str=Form('M20'),rcc_mode:str=Form('rmc'),rcc_site_method:str=Form('nominal'),rcc_nominal_ratio:str=Form('1:1.5:3'),aac_length_mm:float=Form(600),aac_height_mm:float=Form(200),aac_width_mm:float=Form(200),aac_joint_mm:float=Form(4),rcc_cement_kg:float=Form(0),rcc_msand_kg:float=Form(0),rcc_aggregate_kg:float=Form(0),rcc_water_l:float=Form(0),rcc_admixture_kg:float=Form(0),steel_kg_m3:float=Form(0),material_coverage:float=Form(1),steel_diameter_mm:float=Form(12),steel_total_length_m:float=Form(0),steel_bar_count:int=Form(0),steel_cut_length_m:float=Form(0),csrf_token:str=Form(...)):
    owned_project(request,pid);check_csrf(request,csrf_token)
    inputs=dict(work=work,length=length,width=width,depth=depth,openings=openings,waste=waste,brick_length=brick_length,brick_height=brick_height,brick_width=brick_width,joint=joint,tile_length=tile_length,tile_width=tile_width,coats=coats,paint_coverage=paint_coverage,adhesive_coverage=adhesive_coverage,unit=unit,mortar_ratio=mortar_ratio,plaster_ratio=plaster_ratio,pcc_ratio=pcc_ratio,rcc_grade=rcc_grade,rcc_mode=rcc_mode,rcc_site_method=rcc_site_method,rcc_nominal_ratio=rcc_nominal_ratio,rcc_cement_kg=rcc_cement_kg,rcc_msand_kg=rcc_msand_kg,rcc_aggregate_kg=rcc_aggregate_kg,rcc_water_l=rcc_water_l,rcc_admixture_kg=rcc_admixture_kg,steel_kg_m3=steel_kg_m3,material_coverage=material_coverage,steel_diameter_mm=steel_diameter_mm,steel_total_length_m=steel_total_length_m,steel_bar_count=steel_bar_count,steel_cut_length_m=steel_cut_length_m)
    if work=='blockwork':
        aac_values=(aac_length_mm,aac_height_mm,aac_width_mm,aac_joint_mm)
        if not all(math.isfinite(x) for x in aac_values) or not all(1<=x<=3000 for x in aac_values[:3]) or not 3<=aac_joint_mm<=5:
            raise HTTPException(400,'AAC block sizes must be positive (up to 3000 mm); adhesive joint must be 3–5 mm')
        inputs.update(brick_length=aac_length_mm/1000,brick_height=aac_height_mm/1000,brick_width=aac_width_mm/1000,joint=aac_joint_mm/1000)
        inputs.update(aac_length_mm=aac_length_mm,aac_height_mm=aac_height_mm,aac_width_mm=aac_width_mm,aac_joint_mm=aac_joint_mm)
    calculation_inputs={k:v for k,v in inputs.items() if not k.startswith('aac_')}
    try: result=takeoff(**calculation_inputs)
    except ValueError as e: raise HTTPException(400,str(e))
    request.session['pending_takeoff']={'pid':pid,'inputs':inputs}
    return RedirectResponse(f'/projects/{pid}/takeoff/preview',303)

@app.get('/projects/{pid}/takeoff/preview')
def preview_takeoff_page(request:Request,pid:str):
    owned_project(request,pid)
    pending=request.session.get('pending_takeoff')
    if not pending or pending.get('pid')!=pid: return RedirectResponse(f'/projects/{pid}/takeoff',303)
    inputs=pending['inputs']
    try: result=takeoff(**{k:v for k,v in inputs.items() if not k.startswith('aac_')})
    except ValueError as ex: raise HTTPException(400,str(ex))
    rows=''.join(f'<tr><td>{esc(x["material"])}</td><td>{x["quantity"]:,.2f}</td><td>{esc(x["unit"])}</td><td>{esc(x["basis"])}</td></tr>' for x in result['items'])
    notes=''.join(f'<p class="hint">{esc(n)}</p>' for n in result.get('notes',[]))
    return layout(request,'Material Preview',f'''<span class="eyebrow">NOT SAVED · PREVIEW</span><h1>{esc(result['work'])}</h1><div class="card"><h2>Entered dimensions</h2><p>{esc(inputs['length'])} × {esc(inputs['width'])} × {esc(inputs['depth'])} {esc(inputs['unit'])}</p><p>Net area: {result['net_area_m2']:,.3f} m² · Net volume: {result['net_volume_m3']:,.3f} m³</p><p>Wastage: {result['waste_pct']}%</p></div><div class="card"><h2>Material breakdown – preview only</h2><div class="scroll"><table><thead><tr><th>Material</th><th>Quantity</th><th>Unit</th><th>Basis</th></tr></thead><tbody>{rows}</tbody></table></div>{notes}</div><div class="actions"><form action="/projects/{pid}/takeoff/save" method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button>Save Estimate →</button></form><a href="/projects/{pid}/takeoff">← Back without saving</a></div>''')

@app.post('/projects/{pid}/takeoff/save')
def confirm_save_takeoff(request:Request,pid:str,csrf_token:str=Form(...)):
    owned_project(request,pid);check_csrf(request,csrf_token)
    pending=request.session.get('pending_takeoff')
    if not pending or pending.get('pid')!=pid: raise HTTPException(400,'No pending takeoff preview')
    inputs=pending['inputs']
    try: result=takeoff(**{k:v for k,v in inputs.items() if not k.startswith('aac_')})
    except ValueError as ex: raise HTTPException(400,str(ex))
    tid=str(uuid.uuid4())
    with db() as c:c.execute('INSERT INTO material_takeoffs VALUES(?,?,?,?,?,?)',(tid,pid,inputs['work'],json.dumps(inputs),json.dumps(result),int(time.time())))
    request.session.pop('pending_takeoff',None)
    return RedirectResponse(f'/projects/{pid}/takeoff/{tid}',303)

@app.get('/projects/{pid}/takeoff/export.csv')
def export_takeoff(request:Request,pid:str):
    owned_project(request,pid)
    with db() as c:rows=c.execute('SELECT * FROM material_takeoffs WHERE project_id=? ORDER BY created DESC',(pid,)).fetchall()
    buf=io.StringIO();w=csv.writer(buf);w.writerow(['Takeoff ID','Work','Material','Quantity','Unit','Basis','Waste %'])
    for r in rows:
        result=json.loads(r['result_json'])
        for item in result['items']:w.writerow([r['id'],result['work'],item['material'],item['quantity'],item['unit'],item['basis'],result['waste_pct']])
    return Response(buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="civora_material_takeoffs.csv"'})

@app.get('/projects/{pid}/takeoff/{tid}')
def view_takeoff(request:Request,pid:str,tid:str):
    owned_project(request,pid)
    with db() as c:r=c.execute('SELECT * FROM material_takeoffs WHERE id=? AND project_id=?',(tid,pid)).fetchone()
    if not r:raise HTTPException(404,'Estimate not found')
    result=json.loads(r['result_json']); inputs=json.loads(r['input_json'])
    def quantity_text(item):
        quantity=item['quantity']
        if item['unit'] in ('nos','bags (40 kg)'):
            return f'{math.ceil(quantity):,}'
        return f'{quantity:,.2f}'
    rows=''.join(f'<tr><td>{esc(i["material"])}</td><td>{quantity_text(i)}</td><td>{esc(i["unit"])}</td><td>{esc(i["basis"])}</td></tr>' for i in result['items'])
    from engineering import UNIT_TO_M
    unit=inputs.get('unit','m')
    factor=UNIT_TO_M.get(unit,1)
    area_user=result['net_area_m2']/(factor*factor)
    area_label={'ft':'sq.ft','m':'m²','mm':'mm²','in':'sq.in'}.get(unit,unit+'²')
    original_measurements=f"""<p><b>Entered dimensions:</b> {esc(inputs['length'])} × {esc(inputs['width'])} × {esc(inputs['depth'])} {esc(unit)}</p><p><b>Net area in selected unit:</b> {area_user:,.3f} {esc(area_label)}</p><p class="hint">Metric equivalent below is converted from your selected unit. Entering 15 ft never means 15 m.</p>"""

    notes=''.join(f'<p class="warn">{esc(n)}</p>' for n in result.get('notes',[]))
    return layout(request,'Material Results',f'''<span class="eyebrow">SAVED MATERIAL TAKEOFF</span><h1>{esc(result['work'])}</h1><div class="grid"><div class="card"><h2>Measurement</h2>{original_measurements}<p>Converted net area: <b>{result['net_area_m2']:,.3f} m²</b></p><p>Converted net volume: <b>{result['net_volume_m3']:,.3f} m³</b></p><p>Wastage allowance: <b>{result['waste_pct']}%</b></p><p class="muted">Inputs: {esc(inputs['length'])} × {esc(inputs['width'])} × {esc(inputs['depth'])} {esc(inputs.get('unit','m'))}, deduction {esc(inputs['openings'])} {esc(inputs.get('unit','m'))}²</p></div><div class="card"><h2>Important</h2><p>Preliminary estimate only. Check actual dimensions, product specifications, openings, mix design and approved drawings. Not a purchase order or structural approval.</p></div></div><div class="card" style="margin-top:18px"><h2>Material Breakdown</h2>{notes}<div class="scroll"><table><thead><tr><th>Material</th><th>Quantity</th><th>Unit</th><th>Assumption</th></tr></thead><tbody>{rows}</tbody></table></div></div><div class="actions"><a class="primary" href="/projects/{pid}/takeoff">New Takeoff →</a><a href="/projects/{pid}/takeoff/export.csv">Export CSV</a><form method="post" action="/projects/{pid}/takeoff/{tid}/delete" onsubmit="return confirm(&quot;Permanently delete this saved material calculation?&quot;)"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button type="submit" style="background:#a33333">Delete permanently</button></form></div>''')

# v1.1.2: owner-scoped deletion; never delete records without explicit POST + CSRF.
@app.post('/projects/{pid}/uploads/{fid}/delete')
def delete_project_upload(request:Request,pid:str,fid:str,csrf_token:str=Form(...)):
    owned_project(request,pid);check_csrf(request,csrf_token)
    with db() as c:
        row=c.execute('SELECT stored_name FROM uploads WHERE id=? AND project_id=?',(fid,pid)).fetchone()
        if not row:raise HTTPException(404,'Uploaded file not found')
        # Restrict physical deletion to UUID-based stored names in the upload directory.
        stored=Path(row['stored_name']).name
        if stored != row['stored_name'] or not stored.startswith(fid+'.'):
            raise HTTPException(400,'Unsafe stored filename; deletion refused')
        # Delete child records first for SQLite FK compatibility.
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drawing_measurements'").fetchone():
            c.execute('DELETE FROM drawing_measurements WHERE upload_id=? AND project_id=?',(fid,pid))
        c.execute('DELETE FROM uploads WHERE id=? AND project_id=?',(fid,pid))
    # Physical file deletion occurs only after successful database transaction.
    filestore.delete(FILES,stored)
    return RedirectResponse(f'/projects/{pid}',303)

@app.post('/projects/{pid}/materials/{mid}/delete')
def delete_project_measurement(request:Request,pid:str,mid:str,csrf_token:str=Form(...)):
    owned_project(request,pid);check_csrf(request,csrf_token)
    with db() as c:
        result=c.execute('DELETE FROM material_estimates WHERE id=? AND project_id=?',(mid,pid))
        if result.rowcount!=1:raise HTTPException(404,'Saved measurement not found')
    return RedirectResponse(f'/projects/{pid}/materials',303)

@app.post('/projects/{pid}/takeoff/{tid}/delete')
def delete_project_takeoff(request:Request,pid:str,tid:str,csrf_token:str=Form(...)):
    owned_project(request,pid);check_csrf(request,csrf_token)
    with db() as c:
        result=c.execute('DELETE FROM material_takeoffs WHERE id=? AND project_id=?',(tid,pid))
        if result.rowcount!=1:raise HTTPException(404,'Saved calculation not found')
    return RedirectResponse(f'/projects/{pid}/takeoff',303)

# ============================================================
# MODULE REGISTRATION — each module is registered EXACTLY ONCE.
# v2.4.0 cleanup: earlier installers appended a second copy of the
# drawing / recognition / intelligence registrations, which created
# duplicate routes (including the BOQ routes that
# register_intelligent_recognition registers internally).
# Order matters: drawing_workspace re-sorts drawing routes, so it is first.
# ============================================================
# Idempotency markers: older installers (v2.0, v2.2, v2.3) look for these strings
# and skip appending another registration when they are present. Keep them.
# CIVORA_V200_STRUCTURAL_REGISTRATION
# register_structural_design_v220(app,db,owned_project
# register_structural_review_v230(
_REGISTERED_MODULES=set()
def _register_once(name, fn, *args):
    if name in _REGISTERED_MODULES:
        raise RuntimeError(f'Module {name} registered twice; check app.py')
    fn(*args)
    _REGISTERED_MODULES.add(name)

# v1.1+ Drawing workspace (calibrated measurement, drawing BOQ)
from drawing_workspace import register_drawing_routes
_register_once('drawing_workspace', register_drawing_routes, app, db, owned_project, require, csrf, check_csrf, layout, esc, FILES, takeoff, WORKS)

# v1.2 Geometry candidates (recognition)
from recognition import register_recognition
_register_once('recognition', register_recognition, app, db, owned_project, csrf, check_csrf, layout, esc, FILES, takeoff)

# v1.3–v1.9 Drawing intelligence + saved BOQ / rates / Excel / PDF (registers boq_reporting_v170)
from intelligent_recognition import register_intelligent_recognition
_register_once('intelligent_recognition', register_intelligent_recognition, app, db, owned_project, csrf, check_csrf, layout, esc, FILES, takeoff)

# v2.0 Structural worksheet
from structural_v200 import register_structural_v200
_register_once('structural_v200', register_structural_v200, app, db, owned_project, csrf, check_csrf, layout, esc)

# v2.1 Structural Quantity Hub
from structural_v210 import register_structural_v210
_register_once('structural_v210', register_structural_v210, app, db, owned_project, csrf, check_csrf, layout, esc)

# v2.2 Structural design input intake (no design calculations)
from structural_design_v220 import register_structural_design_v220
_register_once('structural_design_v220', register_structural_design_v220, app, db, owned_project, csrf, check_csrf, layout, esc)

# v2.3 Structural review & reconciliation (no design calculations)
from structural_review_v230 import register_structural_review_v230
_register_once('structural_review_v230', register_structural_review_v230, app, db, owned_project, csrf, check_csrf, layout, esc)

# v2.5.0 Project workflow page + Download All
from workflow_v250 import register_workflow_v250
_register_once('workflow_v250', register_workflow_v250, app, db, owned_project, layout, csrf)

# v2.6.0 Rate Master + Smart Estimate (drawing -> full estimate)
from rates_v260 import register_rates_v260
_register_once('rates_v260', register_rates_v260, app, db, require, owned_project, csrf, check_csrf, layout, esc)
from smart_estimate_v260 import register_smart_estimate_v260
_register_once('smart_estimate_v260', register_smart_estimate_v260, app, db, owned_project, require, csrf, check_csrf, layout, esc, FILES, takeoff, store_upload)

# v2.7.0 Team access (roles, invites, activity log, engineer sign-off)
from team_v270 import register_team_v270
_register_once('team_v270', register_team_v270, app, db, owned_project, require, csrf, check_csrf, layout, esc, current_user)

# v2.7.0 Friendly error pages inside the Civora layout (status codes unchanged).
from starlette.exceptions import HTTPException as _StarletteHTTPException
async def _friendly_http_error(request, exc):
    code=getattr(exc,'status_code',500);detail=str(getattr(exc,'detail','') or 'Something went wrong')
    if code==401 and request.method=='GET':
        import team_v270
        from urllib.parse import quote
        return RedirectResponse('/login?next='+quote(team_v270.safe_next(request.url.path),safe=''),303)
    titles={403:'Not allowed for your role',404:'Not found',410:'Link no longer valid',401:'Please sign in',413:'File too large',400:'Please check your input'}
    body=f'<div class="card form" style="max-width:620px"><span class="eyebrow">ERROR {code}</span><h1>{esc(titles.get(code,"Something went wrong"))}</h1><p>{esc(detail)}</p><div class="actions"><a class="cv-btn" href="javascript:history.back()">← Go back</a><a class="cv-btn ghost" href="/">Home</a></div></div>'
    try:
        resp=layout(request,titles.get(code,'Error'),body)
        resp.status_code=code
        return resp
    except Exception:
        return HTMLResponse(f'<h1>{code}</h1><p>{esc(detail)}</p>',status_code=code)
app.add_exception_handler(_StarletteHTTPException,_friendly_http_error)

# v2.8.0 Quick Estimate: built-up area only -> full estimate
from quick_v280 import register_quick_v280
_register_once('quick_v280', register_quick_v280, app, db, owned_project, require, current_user, csrf, check_csrf, layout, esc, takeoff, store_upload)

# v3.0.0 Redesign: Settings (Guided/Expert, language) + Drawing Studio + BBS & BOQ entry
from settings_v300 import register_settings_v300
_register_once('settings_v300', register_settings_v300, app, db, require, csrf, check_csrf, layout, esc)
from studio_v300 import register_studio_v300
_register_once('studio_v300', register_studio_v300, app, db, owned_project, require, csrf, check_csrf, layout, esc, FILES)

# v3.1.0 Cost Intelligence Center, Structural Studio, BBS Studio (read-only pages; forms post to existing routes)
from studio_v310 import register_studio_v310
_register_once('studio_v310', register_studio_v310, app, db, owned_project, require, csrf, layout)

# v3.3.0 Reports Center (read-only; links to the existing export routes) + Tamil interface (ui_shell / i18n_v330)
from reports_v330 import register_reports_v330
_register_once('reports_v330', register_reports_v330, app, db, owned_project, require, layout)

# v3.4.0 Project data: see everything stored, upload, delete items / whole project (backup first), clear rates
from data_v340 import register_data_v340
_register_once('data_v340', register_data_v340, app, db, owned_project, require, csrf, check_csrf, layout, FILES)

# v3.5.0 Move my data (export my projects from one Civora, import into another) + delete buttons next to saved items
from transfer_v350 import register_transfer_v350
_register_once('transfer_v350', register_transfer_v350, app, db, require, csrf, check_csrf, layout, FILES)

# v3.6.0 Data storage page + cloud backup, multi-drawing analysis, Vastu guidance, per sq.ft rate
_register_once('persistence_v360', persistence_v360.register_persistence_v360, app, require, csrf, check_csrf, layout, esc)
from multi_drawing_v360 import register_multi_drawing_v360
_register_once('multi_drawing_v360', register_multi_drawing_v360, app, db, owned_project, require, csrf, check_csrf, layout, esc, FILES, takeoff, store_upload)
from vastu_v360 import register_vastu_v360
_register_once('vastu_v360', register_vastu_v360, app, db, owned_project, require, csrf, check_csrf, layout, esc, FILES, store_upload)
from sqft_rate_v360 import register_sqft_rate_v360
_register_once('sqft_rate_v360', register_sqft_rate_v360, app, db, owned_project, require, csrf, check_csrf, layout, esc)

# v3.8.0 Six-section navigation hubs + guides, site owner admin, audit log, Recycle Bin
from hubs_v380 import register_hubs_v380
_register_once('hubs_v380', register_hubs_v380, app, db, require, csrf, layout, esc, current_user)
from admin_v380 import register_admin_v380
_register_once('admin_v380', register_admin_v380, app, db, require, csrf, check_csrf, layout, esc, FILES)

# v2.4.2: migration history. Versions are recorded once (idempotent).
with db() as c:
    for _v, _d in (
        ('2.3.0', 'Baseline before migration tracking: users, projects, uploads, takeoffs, drawing BOQ, structural v2.0-v2.3 tables'),
        ('2.4.0', 'Step A stabilization: duplicate routes removed, opening labels fixed (no schema change)'),
        ('2.4.1', 'Step B measurement basis stored in BOQ payloads (no table change)'),
        ('2.4.2', 'Step D data safety: schema_migrations table, daily automatic backups, restore tool'),
        ('2.5.0', 'New Civora interface: dashboard, project workflow page, Download All (no table change)'),
        ('2.6.0', 'Smart Estimate flow, Rate Master (new table civora_rate_master_v260), simplified menu'),
        ('2.7.0', 'Team access: members, roles, invite links, activity log, engineer sign-off (4 new tables)'),
        ('2.8.0', 'Quick Estimate from built-up area only (no table change)'),
        ('3.0.0', 'Civora 3.0 redesign: new shell, dashboard, portfolio, wizard, workspace, Drawing Studio; prefs table civora_user_prefs_v300'),
        ('3.1.0', 'Cost Intelligence Center, Structural Studio and BBS Studio (no table change)'),
        ('3.2.0', 'Reinforcement detail drawings (footing, column, beam, slab), site detail sheet, structural rates from Rate Master (no table change)'),
        ('3.3.0', 'Reports Center (all projects + project document center + printable summary) and Tamil interface on main screens (no table change)'),
        ('3.4.0', 'Project data page: delete drawings, estimates and items, delete whole project with backup first, clear rates (no table change)'),
        ('3.5.0', 'Move my data (export / import my projects between Civora sites), delete buttons next to saved items (no table change)'),
        ('3.6.0', 'Cloud backup/persistent disk, multi-drawing analysis, Vastu guidance (civora_vastu_v360), per sq.ft rate (civora_sqft_rate_v360)'),
        ('3.7.0', 'PostgreSQL support (civora_kv, civora_files), calculation audit fixes, preview before save, Vastu from drawing, sample drawings'),
        ('3.8.0', 'Six-section navigation, site owner admin + user analysis, audit log (civora_audit_v380), Recycle Bin (civora_bin_v380), market rates, 48 structural elements, IS code guide'),
        ('3.9.0', 'Complete Rate Master: item-wise labour, doors/windows/services, contingency and contractor margin; rate & amount in previews'),
        ('3.9.1', 'Old estimates re-priced once with the complete Rate Master; hand edit of every quantity and rate, remove lines, add items by hand, re-price keeps hand edits'),
        ('3.9.2', 'Admin = site owner only, everyone else User; server storage page Admin-only'),
    ):
        data_safety.record_migration(c, _v, _d)

# v3.6.0: background cloud backup (only when CIVORA_BACKUP_REPO / CIVORA_BACKUP_TOKEN are set)
persistence_v360.start(DATA, app)
# v3.7.0: on PostgreSQL the drawings are stored in the database; bring back any missing local copies
if dbcompat.is_postgres():
    try:
        _n=filestore.sync_down(FILES)
        print(f'[Civora] Database: {dbcompat.backend_label()}' + (f' · restored {_n} drawing file(s) from the database' if _n else ''), flush=True)
    except Exception as _ex:
        print(f'[Civora] WARNING: could not restore drawing files from the database: {_ex}', flush=True)
