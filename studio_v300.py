"""Civora AI v3.0 - redesigned screens on top of the unchanged backend.

  dashboard_html()   Dashboard: one big "How big is your building?" question + command-center tiles
  portfolio_html()   Projects: table / card view, search, type and status filters
  wizard_html()      New Project: guided steps in one form (posts the same fields as before)
  workspace_html()   Project workspace: next step, 6 workflow cards, files and tools
  Drawing Studio     /projects/{pid}/studio[/{fid}]: drawings | zoomable viewer | what Civora read | saved measurements
  BBS & BOQ          moved to studio_v310.py (Cost Intelligence Center, v3.1)

Everything here only READS existing tables; every form posts to an existing route.
"""
import json
import time
from functools import lru_cache

import ui_shell
from ui_shell import esc, icon, inr_short, STEPS
import workflow_v250 as wf

DRAWING_EXT = ('.png', '.jpg', '.jpeg', '.pdf', '.dxf')
STATUS = {  # key: (label, css class)
    'draft': ('Draft', 'st-draft'), 'input': ('Needs input', 'st-input'), 'progress': ('In progress', 'st-progress'),
    'review': ('Needs review', 'st-review'), 'checked': ('Checked', 'st-checked'),
}
EVIDENCE_LABELS = {
    'overall_length': 'Outside length', 'overall_width': 'Outside width', 'floor_area': 'Floor area', 'slab_area': 'Slab area',
    'height': 'Wall height', 'external_thickness': 'External wall', 'internal_thickness': 'Internal wall',
    'slab_thickness': 'Slab thickness', 'external_plaster_thickness': 'External plaster', 'internal_plaster_thickness': 'Internal plaster',
    'floor_tile_area_each': 'Floor tile (each)', 'kitchen_tile_area_each': 'Kitchen tile (each)', 'bathroom_tile_area_each': 'Bathroom tile (each)',
    'waste': 'Wastage', 'roof_waterproof_area': 'Roof waterproofing', 'wall_length': 'Wall length',
}
EVIDENCE_UNITS = {'overall_length': 'm', 'overall_width': 'm', 'floor_area': 'm²', 'slab_area': 'm²', 'height': 'm',
                  'external_thickness': 'm', 'internal_thickness': 'm', 'slab_thickness': 'm', 'external_plaster_thickness': 'm',
                  'internal_plaster_thickness': 'm', 'floor_tile_area_each': 'm²', 'kitchen_tile_area_each': 'm²',
                  'bathroom_tile_area_each': 'm²', 'waste': '%', 'roof_waterproof_area': 'm²', 'wall_length': 'm'}


def status_of(st):
    """One meaningful status per project (label + colour, never colour alone)."""
    done = st['done']
    if not (st['boq'] or st['takeoffs'] or st['structural_items']):
        return 'draft'
    if 'cost' not in done:
        return 'input'
    if (st.get('boq_frame') or st['structural_items']) and not st.get('signoff'):
        return 'review'
    if st.get('signoff'):
        return 'checked'
    return 'progress'


def status_chip(key, text=None):
    label, cls = STATUS[key]
    return f'<span class="cv-status {cls}">{esc(text or label)}</span>'


def last_updated(c, p, st):
    ts = [p['created']]
    if st.get('boq'):
        ts.append(st['boq']['created'])
    ts += [u['created'] for u in st['uploads'][:1]]
    try:
        r = c.execute('SELECT MAX(at) FROM civora_activity_v270 WHERE project_id=?', (p['id'],)).fetchone()
        if r and r[0]:
            ts.append(r[0])
    except Exception:
        pass
    return max(ts)


def _ago(ts):
    d = max(int(time.time()) - int(ts), 0)
    if d < 3600:
        return f'{max(d // 60, 1)} min ago'
    if d < 86400:
        return f'{d // 3600} h ago'
    if d < 86400 * 7:
        return f'{d // 86400} d ago'
    return time.strftime('%d %b %Y', time.localtime(ts))


def project_rows(c, uid, where='', args=()):
    import team_v270
    out = []
    for p in team_v270.accessible_projects(c, uid, where, args):
        st = wf.project_status(c, p['id'])
        out.append({'p': p, 'st': st, 'role': p['my_role'], 'status': status_of(st), 'updated': last_updated(c, p, st)})
    return out


# ------------------------------------------------------------------ dashboard
def dashboard_data(c, user):
    import team_v270
    rows = project_rows(c, user['id'])
    ids = [r['p']['id'] for r in rows]
    acts = []
    if ids:
        q = ','.join('?' * len(ids))
        try:
            acts = c.execute(f'SELECT a.action, a.at, u.name AS who, p.name AS pname, p.id AS pid FROM civora_activity_v270 a '
                             f'LEFT JOIN users u ON u.id=a.user_id JOIN projects p ON p.id=a.project_id '
                             f'WHERE a.project_id IN ({q}) ORDER BY a.at DESC, a.id DESC LIMIT 6', ids).fetchall()
        except Exception:
            acts = []
    rates_set = 0
    try:
        import rates_v260
        rates_set = sum(1 for v in rates_v260.effective_rates(rates_v260.load_rates(c, user['id'])).values() if v > 0)
    except Exception:
        pass
    return {'rows': rows, 'activity': acts, 'rates_set': rates_set,
            'budget': sum(r['st']['cost']['total'] for r in rows),
            'review': sum(1 for r in rows if r['status'] == 'review'),
            'input': sum(1 for r in rows if r['status'] in ('input', 'draft'))}


def _greeting():
    h = time.localtime().tm_hour
    return 'Good morning' if h < 12 else ('Good afternoon' if h < 17 else 'Good evening')


def ask_card(csrf_token, user, latest_pid=None):
    seg = ''.join(f'<label><input type="radio" name="floors" value="{n}"{" checked" if n == 1 else ""}><span>{lbl}</span></label>'
                  for n, lbl in ((1, 'G'), (2, 'G+1'), (3, 'G+2'), (4, 'G+3')))
    alt_href = (f'/projects/{esc(latest_pid)}/studio' if latest_pid else '/projects/new?next=smart') if user else '/register'
    return f'''<section class="db-ask" aria-labelledby="ask-h"><div class="k">QUICK ESTIMATE · ஒரு நிமிட மதிப்பீடு</div>
<h2 id="ask-h">How big is your building?</h2><div class="ta">உங்கள் கட்டிடம் எவ்வளவு பெரியது?</div>
<form method="post" action="/quick"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
<label>Built-up area (all floors)<span class="db-area"><input name="area" inputmode="numeric" required placeholder="1000" aria-label="Built-up area in square feet"><b>sq.ft</b></span></label>
<fieldset style="border:0;padding:0;margin:0"><legend style="color:#c7d7ea;font-size:12.5px;font-weight:600;padding:0 0 6px">Floors</legend><div class="db-seg">{seg}</div></fieldset>
<button class="db-go">Get full estimate →</button></form>
<div class="alt">Materials, steel and cost in one click. Have a drawing? <a href="{alt_href}">Upload it for an exact estimate</a></div></section>'''


def dashboard_html(user, data, csrf_token, prefs=None):
    prefs = prefs or {}
    if not user:
        return f'''<div class="db-top"><div><h1>Civora AI</h1><div class="sub">Construction Intelligence Workspace · quantities, steel, cost and reports</div></div></div>
<div class="db-grid">{ask_card(csrf_token, None)}
<section class="cv-card"><h3>{icon("users", 18)} Free account</h3><p class="sub">Save projects, upload drawings, set your local rates, share with your engineer, dealer and customer.</p>
<div class="actions"><a class="cv-btn" href="/register">Create free account</a><a class="cv-btn ghost" href="/login">Sign in</a></div></section></div>
<p class="cv-disclaim">{icon("shield", 16)}<span>Quantities, costs and structural sizes are planning estimates. All structural design must be reviewed and approved by a qualified, licensed engineer before construction.</span></p>'''
    rows = data['rows']
    latest = rows[0] if rows else None
    first = esc(str(user['name']).split()[0]) if user['name'] else ''
    mode = prefs.get('mode', 'guided')
    stats = (f'<a class="db-stat" href="/projects"><small>Active projects</small><b>{len(rows)}</b><em>owned + shared with you</em></a>'
             f'<a class="db-stat" href="/projects?status=review"><small>Needs engineer review</small><b>{data["review"]}</b><em>estimates without sign-off</em></a>'
             f'<a class="db-stat" href="/projects?status=input"><small>Needs input</small><b>{data["input"]}</b><em>no estimate or no prices yet</em></a>'
             f'<a class="db-stat" href="/rates"><small>Estimated budget</small><b>{esc(inr_short(data["budget"]))}</b><em>{data["rates_set"]} of {len(__import__("rates_v260").RATE_KEYS)} rates set</em></a>')
    if latest:
        st, p = latest['st'], latest['p']
        nxt = next((s for s in STEPS if s[0] not in st['done']), None)
        P = f'/projects/{p["id"]}'
        mini = ''.join(f'<i class="{"on" if s[0] in st["done"] else ""}" title="{esc(s[2])}"></i>' for s in STEPS)
        go = {'setup': P, 'input': P + '/studio', 'materials': P + '/smart', 'structure': P + '/structure',
              'cost': '/rates', 'reports': P + '/reports'}
        nxt_html = (f'<a class="cv-btn" href="{go[nxt[0]]}">Next: {esc(nxt[2])} {icon("arrow", 15)}</a>' if nxt
                    else f'<a class="cv-btn" href="{P}/workflow/download-all">{icon("download", 15)} Download reports</a>')
        total = st['cost']['total']
        cont = f'''<section class="cv-card db-cont"><div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap">
<div><small class="sub" style="margin:0">Continue where you left off</small><h3>{esc(p["name"])}</h3><span class="sub">{esc(p["type"])} · {esc(p["location"])} · {float(p["area"] or 0):,.0f} sq.ft</span></div>
<div style="text-align:right">{status_chip(latest["status"])}<div style="font-size:22px;font-weight:800;margin-top:4px">{esc(inr_short(total)) if total else "—"}</div></div></div>
<div class="db-mini" aria-label="{len(st["done"])} of 6 steps done">{mini}</div><div class="next">{nxt_html}<a class="cv-btn ghost" href="{P}">Open workspace</a><a class="cv-btn ghost" href="{P}/studio">Drawing Studio</a></div></section>'''
        trs = ''.join(f'<tr><td><a href="/projects/{esc(r["p"]["id"])}">{esc(r["p"]["name"])}</a>'
                      f'{"" if r["role"] == "owner" else f" <small class=sub>· {esc(r["role"].title())}</small>"}</td>'
                      f'<td>{status_chip(r["status"])}</td><td style="text-align:right">{esc(inr_short(r["st"]["cost"]["total"])) if r["st"]["cost"]["total"] else "—"}</td></tr>'
                      for r in rows[:5])
        recent = f'<section class="cv-card"><div class="cv-sec" style="margin:0 0 8px"><h2>Projects</h2><a href="/projects">View all →</a></div><table class="cv-mt"><tr><th>Project</th><th>Status</th><th>Estimate</th></tr>{trs}</table></section>'
    else:
        cont = (f'<section class="cv-card">{ui_shell.recent_html([])}</section>')
        recent = ''
    acts = ''.join(f'<li><span class="dot"></span><span><b>{esc(a["who"] or "Someone")}</b> {esc(a["action"])}<small>'
                   f'<a href="/projects/{esc(a["pid"])}">{esc(a["pname"])}</a> · {_ago(a["at"])}</small></span></li>' for a in data['activity'])
    activity = f'<section class="cv-card"><h3>{icon("layers", 18)} Recent activity</h3><ul class="cv-activity">{acts or "<li class=sub>Nothing yet — your team’s work shows here.</li>"}</ul></section>'
    guide = ('<div class="cv-guide">' + icon('check', 20) + '<div><b>New here? Type your building’s built-up area below and press “Get full estimate”.</b>'
             'Have a drawing? Upload it in Drawing Studio for an exact estimate.<span class="ta">தொடங்க: கட்டிடப் பரப்பை (சதுர அடி) உள்ளிட்டு “Get full estimate” அழுத்தவும்.</span></div></div>')
    return f'''<div class="db-top"><div><h1>{_greeting()}, {first}</h1><div class="sub">{time.strftime("%A, %d %B %Y")} · <a href="/settings">{"Guided" if mode == "guided" else "Expert"} mode</a></div></div>
<a class="cv-btn ghost" href="/projects/new">{icon("plus", 16)} New project</a></div>{guide}
<div class="db-grid">{ask_card(csrf_token, user, latest["p"]["id"] if latest else None)}<div class="db-stats">{stats}</div></div>
<div class="db-row"><div style="display:flex;flex-direction:column;gap:16px">{cont}{recent}</div>{activity}</div>
<p class="cv-disclaim">{icon("shield", 16)}<span>Quantities, costs and structural sizes are planning estimates. All structural design must be reviewed and approved by a qualified, licensed engineer before construction.</span></p>'''


# ------------------------------------------------------------------ projects portfolio
TYPES = ['Residential', 'Commercial', 'Industrial', 'Infrastructure', 'Custom']


def portfolio_html(rows, q='', ftype='', fstatus='', view='table'):
    def keep(r):
        return (not ftype or r['p']['type'] == ftype) and (not fstatus or r['status'] == fstatus)
    shown = [r for r in rows if keep(r)]
    qs = lambda **kw: '/projects?' + '&'.join(f'{k}={esc(v)}' for k, v in {'q': q, 'type': ftype, 'status': fstatus, 'view': view, **kw}.items() if v)
    topt = '<option value="">All types</option>' + ''.join(f'<option{" selected" if t == ftype else ""}>{t}</option>' for t in TYPES)
    sopt = '<option value="">All statuses</option>' + ''.join(f'<option value="{k}"{" selected" if k == fstatus else ""}>{v[0]}</option>' for k, v in STATUS.items())
    bar = (f'<form class="pf-bar" method="get" action="/projects" role="search"><input name="q" value="{esc(q)}" placeholder="Search name, type, location" aria-label="Search projects">'
           f'<select name="type" aria-label="Type" onchange="this.form.submit()">{topt}</select><select name="status" aria-label="Status" onchange="this.form.submit()">{sopt}</select>'
           f'<input type="hidden" name="view" value="{esc(view)}"><button class="cv-btn sm">Apply</button>'
           f'<span class="seg"><a class="{"on" if view != "cards" else ""}" href="{qs(view="table")}">Table</a><a class="{"on" if view == "cards" else ""}" href="{qs(view="cards")}">Cards</a></span></form>')
    if not rows and not q:
        return ui_shell.recent_html([])
    if not shown:
        return bar + f'<div class="cv-empty"><b>No projects match{f" “{esc(q)}”" if q else ""}</b>Try a different name, type or location. <a href="/projects">Show all projects</a></div>'
    if view == 'cards':
        body = '<div class="pf-cards">' + ''.join(
            f'<a class="pf-card" href="/projects/{esc(r["p"]["id"])}"><span style="display:flex;justify-content:space-between;gap:8px"><b>{esc(r["p"]["name"])}</b>{status_chip(r["status"])}</span>'
            f'<span class="sub" style="margin:0">{esc(r["p"]["type"])} · {esc(r["p"]["location"])} · {float(r["p"]["area"] or 0):,.0f} sq.ft</span>'
            f'<span class="pf-prog" style="width:100%"><i style="width:{round(100 * len(r["st"]["done"]) / 6)}%"></i></span>'
            f'<span style="display:flex;justify-content:space-between;font-size:13px"><span>{esc(inr_short(r["st"]["cost"]["total"])) if r["st"]["cost"]["total"] else "No estimate"}</span>'
            f'<span class="sub" style="margin:0">{"Shared · " + esc(r["role"].title()) + " · " if r["role"] != "owner" else ""}{_ago(r["updated"])}</span></span></a>' for r in shown) + '</div>'
    else:
        trs = ''.join(f'<tr><td><a href="/projects/{esc(r["p"]["id"])}"><b>{esc(r["p"]["name"])}</b></a>'
                      f'{f"<br><small class=sub>Shared · {esc(r["role"].title())}</small>" if r["role"] != "owner" else ""}</td>'
                      f'<td>{esc(r["p"]["type"])}</td><td>{esc(r["p"]["location"])}</td><td style="text-align:right">{float(r["p"]["area"] or 0):,.0f}</td>'
                      f'<td>{status_chip(r["status"])}</td><td><span class="pf-prog"><i style="width:{round(100 * len(r["st"]["done"]) / 6)}%"></i></span> <small>{len(r["st"]["done"])}/6</small></td>'
                      f'<td style="text-align:right">{esc(inr_short(r["st"]["cost"]["total"])) if r["st"]["cost"]["total"] else "—"}</td><td>{_ago(r["updated"])}</td>'
                      f'<td>{f"<a class=pf-del href=/projects/{esc(r["p"]["id"])}/data#delete>Delete</a>" if r["role"] == "owner" else ""}</td></tr>' for r in shown)
        body = (f'<div class="scroll"><table class="pf-table"><tr><th>Project</th><th>Type</th><th>Location</th><th>Area (sq.ft)</th><th>Status</th>'
                f'<th>Progress</th><th>Estimate</th><th>Updated</th><th></th></tr>{trs}</table></div>')
    return bar + body


# ------------------------------------------------------------------ new project wizard
def wizard_html(csrf_token, chosen='Residential', prefill='', nxt=''):
    icons = {'Residential': 'home', 'Commercial': 'site', 'Industrial': 'truck', 'Infrastructure': 'beam', 'Custom': 'layers'}
    types = ''.join(f'<label><input type="radio" name="type" value="{t}"{" checked" if t == chosen else ""}><span><b>{icon(icons[t], 22)} {t}</b></span></label>' for t in TYPES)
    starts = [('quick', 'Area only', 'பரப்பு மட்டும்', 'Full estimate now from the built-up area and floors. Typical sizes are used.'),
              ('smart', 'Upload a drawing', 'வரைபடம்', 'Civora reads the plan and asks only for what is missing. Most accurate.'),
              ('', 'Set up later', 'பிறகு', 'Just create the project; add drawings and estimates any time.')]
    default = nxt if nxt in ('quick', 'smart') else 'quick'
    start_html = ''.join(f'<label><input type="radio" name="next" value="{k}"{" checked" if k == default else ""}><span><b>{t}</b><em style="font-style:normal">{ta}</em>{d}</span></label>' for k, t, ta, d in starts)
    floors = ''.join(f'<option value="{n}">{lbl}</option>' for n, lbl in ((1, 'G (ground only)'), (2, 'G + 1'), (3, 'G + 2'), (4, 'G + 3')))
    steps = ''.join(f'<li><b>{i}</b><a href="#wz{i}" style="color:inherit;text-decoration:none">{t}</a></li>' for i, t in enumerate(('Basic details', 'Building', 'How to start', 'Review'), 1))
    return f'''<span class="eyebrow">NEW PROJECT · புதிய திட்டம்</span><h1>Create a project</h1><p class="muted">Four short steps. Everything can be changed later.</p>
<div class="wz"><ol class="wz-steps" aria-label="Steps">{steps}</ol>
<form method="post" action="/projects/new"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
<section class="wz-sec" id="wz1"><h2><b>1</b>Basic details</h2><p class="ta">அடிப்படை விவரங்கள்</p>
<label for="wz-name">Project name</label><input id="wz-name" name="name" maxlength="120" required placeholder="Example: Kumar Residence" value="{esc(prefill)}">
<label>Project type</label><div class="cv-types">{types}</div></section>
<section class="wz-sec" id="wz2"><h2><b>2</b>Building</h2><p class="ta">கட்டிடம்</p>
<div class="cv-row" style="grid-template-columns:repeat(3,minmax(0,1fr))"><div><label for="wz-loc">Location</label><input id="wz-loc" name="location" required placeholder="City, District"></div>
<div><label for="wz-area">Built-up area, all floors (sq.ft)</label><input id="wz-area" name="area" type="number" min="1" max="100000000" step="any" required placeholder="1200"></div>
<div><label for="wz-floors">Floors</label><select id="wz-floors" name="floors">{floors}</select></div></div></section>
<section class="wz-sec" id="wz3"><h2><b>3</b>How do you want to start?</h2><p class="ta">எப்படி தொடங்க வேண்டும்?</p><div class="wz-choice">{start_html}</div></section>
<section class="wz-sec" id="wz4"><h2><b>4</b>Review &amp; create</h2><p class="ta">சரிபார்த்து உருவாக்கவும்</p>
<p class="sub">Your project is private to you until you invite people from the Team page. Structural sizes in any estimate are for quantity planning only — an engineer must review them.</p>
<div class="actions"><button class="cv-btn">Create project →</button><a class="cv-btn ghost" href="/projects">Cancel</a></div></section></form></div>'''


# ------------------------------------------------------------------ project workspace
def workspace_html(project, st, csrf_token, role, files, estimate_id=''):
    import team_v270
    pid = project['id']
    P = f'/projects/{pid}'
    can_edit = team_v270.allowed(role, 'edit')
    nxt = next((s for s in STEPS if s[0] not in st['done']), None)
    go = {'setup': (P + '/studio', 'Upload a drawing'), 'input': (P + '/studio', 'Open Drawing Studio'),
          'materials': (P + '/smart', 'Start Smart Estimate'), 'structure': (P + '/structure', 'Open Structural Studio'),
          'cost': ('/rates', 'Set your rates'), 'reports': (P + '/reports', 'Open reports')}
    if nxt and can_edit:
        href, label = go[nxt[0]]
        nxt_card = (f'<div class="cv-banner" style="background:#eff6ff;border-color:#bfdbfe;color:#1e3a8a">{icon("arrow", 22)}<div><b>Next step: {esc(nxt[2])}</b>'
                    f'{esc(nxt[3])}.<div style="margin-top:10px"><a class="cv-btn" href="{href}">{esc(label)}</a></div></div></div>')
    elif not nxt:
        nxt_card = (f'<div class="cv-banner">{icon("check", 22)}<div><b>All six steps are done.</b>Download every report as one ZIP.'
                    f'<div style="margin-top:10px"><a class="cv-btn" href="{P}/workflow/download-all">{icon("download", 15)} Download all reports</a></div></div></div>')
    else:
        nxt_card = ''
    links = {'setup': P, 'input': P + '/studio', 'materials': P + '/smart', 'structure': '#structure', 'cost': '#cost', 'reports': '#reports'}
    file_rows = ''.join(
        f'<li><span class="ty" style="background:#e0f2fe;color:#0369a1">{esc(str(f["original_name"]).rsplit(".", 1)[-1].upper()[:4])}</span>'
        f'<span class="nm">{esc(f["original_name"])}<small>{time.strftime("%d %b %Y", time.localtime(f["created"]))}</small></span>'
        + (f'<a class="cv-btn sm ghost" href="{P}/studio/{esc(f["id"])}">Studio</a>' if str(f['original_name']).lower().endswith(DRAWING_EXT) else '')
        + f'<a class="dl" href="/files/{esc(f["id"])}" aria-label="Download {esc(f["original_name"])}">{icon("download", 18)}</a>'
        + (f'<form method="post" action="{P}/data/files/{esc(f["id"])}/delete?return={P}" class="cv-inline" onsubmit="return confirm(&quot;Permanently delete this file and the estimates and measurements made from it?&quot;)">'
           f'<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><button class="cv-btn sm ghost" style="color:#b91c1c">Delete</button></form>' if role == 'owner' else '')
        + '</li>' for f in files)
    upload = (f'<form id="upload" action="{P}/upload" method="post" enctype="multipart/form-data" class="cv-fin" style="margin-bottom:8px">'
              f'<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><input type="hidden" name="next" value="studio">'
              f'<input type="file" name="file" accept=".png,.jpg,.jpeg,.pdf,.dxf,.xlsx,.csv" required aria-label="Choose file"><button class="cv-btn sm">Upload</button></form>'
              if can_edit else '<form id="upload" hidden></form>')
    tools = (f'<div class="actions" style="margin-top:6px"><a class="cv-btn sm" href="{P}/smart">{icon("calc", 15)} Start Smart Estimate</a>'
             f'<a class="cv-btn sm ghost" href="{P}/studio">{icon("drawing", 15)} Drawing Studio</a><a class="cv-btn sm ghost" href="{P}/workflow">Project workflow</a><a class="cv-btn sm ghost" href="{P}/data">Stored data · delete</a></div>'
             if can_edit else f'<div class="actions" style="margin-top:6px"><a class="cv-btn sm ghost" href="{P}/workflow">Project workflow</a></div>')
    return (nxt_card + ui_shell.stepper(st['done'], links) + '<div style="height:16px"></div>'
            + wf.workflow_cards(project, st, csrf_token=csrf_token, role=role)
            + f'<section class="cv-card" style="margin-top:16px"><h3>{icon("folder", 18)} Drawings &amp; files</h3><p class="sub">PDF, DXF, PNG, JPG, Excel or CSV · up to 30 MB</p>'
              f'{upload}<ul class="cv-files">{file_rows or "<li class=sub>No files yet.</li>"}</ul>{tools}</section>'
            + f'<p class="cv-disclaim">{icon("shield", 16)}<span>Quantities and costs are planning estimates. All structural design must be reviewed and approved by a qualified, licensed engineer.</span></p>')


# ------------------------------------------------------------------ drawing studio
@lru_cache(maxsize=32)
def _read_schedule(path_str, page, mtime):
    from drawing_schedule import extract
    return extract(path_str, page)


def read_schedule(path, page=0):
    try:
        return _read_schedule(str(path), int(page), path.stat().st_mtime)
    except Exception as ex:
        return {'evidence': {}, 'rooms': [], 'openings': [], 'method': 'not available',
                'warnings': [f'Could not read this drawing automatically ({type(ex).__name__}).']}


def pdf_pages(path):
    if path.suffix.lower() != '.pdf':
        return 1
    try:
        import fitz
        with fitz.open(str(path)) as d:
            return max(len(d), 1)
    except Exception:
        return 1


ZOOM_JS = ("<script>(function(){var img=document.getElementById('ds-img');if(!img)return;var z=100,out=document.getElementById('ds-zoom');"
           "function set(v){z=Math.max(25,Math.min(400,v));img.style.width=z+'%';img.style.maxWidth='none';if(z===100)img.style.maxWidth='100%';out.textContent=z+'%';}"
           "document.getElementById('ds-in').onclick=function(){set(z+25)};document.getElementById('ds-out').onclick=function(){set(z-25)};"
           "document.getElementById('ds-fit').onclick=function(){set(100)};})();</script>")


def register_studio_v300(app, db, owned_project, require, csrf, check_csrf, layout, esc_, FILES):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    import team_v270

    def drawings(pid):
        with db() as c:
            return [r for r in c.execute('SELECT * FROM uploads WHERE project_id=? ORDER BY created DESC', (pid,)).fetchall()
                    if str(r['original_name']).lower().endswith(DRAWING_EXT)]

    def studio_page(request, p, files, cur, page):
        pid = p['id']
        P = f'/projects/{pid}'
        role = getattr(request.state, 'cv_role', 'owner')
        can_edit = team_v270.allowed(role, 'edit')
        token = csrf(request)
        import data_v340
        can_delete = team_v270.allowed(role, 'manage')
        flist = ''.join(f'<li class="dt-row"><a class="{"on" if cur is not None and f["id"] == cur["id"] else ""}" href="{P}/studio/{esc(f["id"])}">'
                        f'<span class="th"><img loading="lazy" src="{P}/drawings/{esc(f["id"])}/media" alt=""></span>'
                        f'<span style="min-width:0;overflow:hidden;text-overflow:ellipsis">{esc(f["original_name"])}</span></a>'
                        + (data_v340.x_form(f'{P}/data/files/{f["id"]}/delete?return={P}/studio', token,
                                            f'Delete {f["original_name"]} and the estimates made from it?', f'Delete {f["original_name"]}') if can_delete else '')
                        + '</li>' for f in files)
        upload = (f'<form action="{P}/upload" method="post" enctype="multipart/form-data" style="margin-top:12px"><input type="hidden" name="csrf_token" value="{token}">'
                  f'<input type="hidden" name="next" value="studio"><input type="file" name="file" accept=".pdf,.dxf,.png,.jpg,.jpeg" required aria-label="Choose drawing" style="font-size:12px;padding:6px">'
                  f'<button class="cv-btn sm" style="margin-top:8px;width:100%;justify-content:center">{icon("upload", 15)} Upload drawing</button></form>') if can_edit else ''
        left = f'<aside class="ds-panel"><h3>Drawings</h3><ul class="ds-files">{flist or "<li class=sub>No drawings yet.</li>"}</ul>{upload}</aside>'
        if cur is None:
            centre = (f'<section class="ds-viewer"><div class="ds-canvas" style="align-items:center">'
                      f'<div class="cv-empty" style="max-width:420px"><b>No drawing yet</b>Upload a building plan (PDF, DXF, PNG or JPG) on the left. '
                      f'Civora reads its sizes, rooms and door/window schedule.</div></div></section>')
            body = f'<div class="ds" style="grid-template-columns:240px minmax(0,1fr)">{left}{centre}</div>'
            return layout(request, 'Drawing Studio', '<span class="eyebrow">DRAWING STUDIO · வரைபட ஸ்டுடியோ</span><h1>Drawing Studio</h1>' + body)
        path = FILES / cur['stored_name']
        n_pages = pdf_pages(path)
        page = max(0, min(page, n_pages - 1))
        sched = read_schedule(path, page)
        ev = sched.get('evidence') or {}
        found = len(ev)
        pages = ''.join(f'<a class="cv-btn sm{"" if i == page else " ghost"}" href="{P}/studio/{esc(cur["id"])}?page={i}">{i + 1}</a>' for i in range(min(n_pages, 12))) if n_pages > 1 else ''
        centre = f'''<section class="ds-viewer"><div class="ds-tool"><b style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">{esc(cur["original_name"])}</b>
<button type="button" id="ds-out" aria-label="Zoom out">−</button><span id="ds-zoom" style="min-width:44px;text-align:center">100%</span><button type="button" id="ds-in" aria-label="Zoom in">+</button><button type="button" id="ds-fit">Fit</button>{pages}</div>
<div class="ds-canvas"><img id="ds-img" src="{P}/drawings/{esc(cur["id"])}/media?page={page}" alt="Drawing {esc(cur["original_name"])}, page {page + 1}"></div></section>'''
        ev_rows = ''.join(f'<dt>{esc(EVIDENCE_LABELS.get(k, k.replace("_", " ").title()))}</dt><dd title="{esc(v.get("source", ""))}">{v["value"]:g} {esc(EVIDENCE_UNITS.get(k, ""))}</dd>'
                          for k, v in ev.items() if isinstance(v.get('value'), (int, float)))
        rooms = ''.join(f'<tr><td>{esc(r["name"])}</td><td>{float(r["length"]):g} × {float(r["width"]):g} m</td><td>{float(r["area"]):,.1f} m²</td></tr>' for r in sched.get('rooms') or [])
        opens = ''.join(f'<tr><td>{esc(o["label"])}</td><td>{o["count"]}</td><td>{float(o["width"]):g} × {float(o["height"]):g} m</td></tr>' for o in sched.get('openings') or [])
        warn = ''.join(f'<p class="hint">{esc(w)}</p>' for w in sched.get('warnings') or [])
        F = f'{P}/drawings/{esc(cur["id"])}'
        actions = ''
        if can_edit:
            actions = (f'<a class="cv-btn" style="width:100%;justify-content:center" href="{P}/smart/{esc(cur["id"])}">{icon("calc", 16)} Smart Estimate from this drawing</a>'
                       f'<div class="actions" style="margin-top:8px"><a class="cv-btn sm ghost" href="{F}?page={page}">Measure on drawing</a>'
                       f'<a class="cv-btn sm ghost cv-expert" href="{F}/intelligence?page={page}">Classic auto quantities</a></div>')
        actions += f'<div class="actions" style="margin-top:8px"><a class="cv-btn sm ghost" href="/files/{esc(cur["id"])}">{icon("download", 15)} Original file</a></div>'
        right = f'''<aside class="ds-panel ds-right"><h3>What Civora read</h3>
<div class="ds-found"><b>{found}</b><span>sizes found on this page<br><small class="sub" style="margin:0">{esc(sched.get("method", ""))}</small></span></div>
{f'<dl class="ds-kv">{ev_rows}</dl>' if ev_rows else '<p class="sub">No sizes could be read. Smart Estimate will ask you for them.</p>'}
{f'<h3 style="margin-top:14px">Rooms ({len(sched.get("rooms") or [])})</h3><table class="cv-mt"><tr><th>Room</th><th>Size</th><th>Area</th></tr>{rooms}</table>' if rooms else ''}
{f'<h3 style="margin-top:14px">Doors &amp; windows</h3><table class="cv-mt"><tr><th>Item</th><th>Nos</th><th>Size</th></tr>{opens}</table>' if opens else ''}
{warn}<div style="margin-top:14px">{actions}</div></aside>'''
        with db() as c:
            meas = c.execute('SELECT * FROM drawing_measurements WHERE project_id=? AND upload_id=? ORDER BY created DESC', (pid, cur['id'])).fetchall() \
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drawing_measurements'").fetchone() else []
            boqs = c.execute('SELECT id, created FROM civora_boq_reports WHERE project_id=? AND drawing_id=? ORDER BY created DESC', (pid, cur['id'])).fetchall() \
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_boq_reports'").fetchone() else []

        def mres(m):
            try:
                r = json.loads(m['result_json'])
            except (TypeError, ValueError):
                return ''
            parts = []
            if r.get('net_area_m2'):
                parts.append(f'{float(r["net_area_m2"]):,.2f} m²')
            if r.get('net_volume_m3'):
                parts.append(f'{float(r["net_volume_m3"]):,.3f} m³')
            return ' · '.join(parts)
        mrows = ''.join(f'<tr><td>{time.strftime("%d %b %Y", time.localtime(m["created"]))}</td><td>Page {int(m["page"]) + 1}</td><td>{esc(m["work"])}</td><td>{esc(mres(m))}</td>'
                        f'<td><a href="{P}/drawings/saved/{esc(m["id"])}">Open</a></td></tr>' for m in meas)
        brows = ''.join(f'<tr><td>{time.strftime("%d %b %Y %H:%M", time.localtime(b["created"]))}</td><td>Saved estimate (BOQ)</td><td></td><td></td>'
                        f'<td><a href="{F}/boq/{esc(b["id"])}">Open</a></td></tr>' for b in boqs)
        sched_html = (f'<section class="cv-card ds-sched"><h3>{icon("report", 18)} Measurement schedule for this drawing</h3>'
                      + (f'<div class="scroll"><table class="cv-mt"><tr><th>Date</th><th>Where</th><th>Work</th><th>Quantity</th><th></th></tr>{brows}{mrows}</table></div>'
                         if (mrows or brows) else '<p class="sub">Nothing saved from this drawing yet. Use Smart Estimate, or Measure on drawing for a single wall or slab.</p>')
                      + '</section>')
        guide = ('<div class="cv-guide">' + icon('check', 20) + '<div><b>Check the sizes on the right against your drawing, then press “Smart Estimate from this drawing”.</b>'
                 'Use + and − to zoom. Values Civora could not read are asked in the next step.<span class="ta">வலது பக்கம் உள்ள அளவுகளை சரிபார்த்து “Smart Estimate” அழுத்தவும்.</span></div></div>') if can_edit else \
            ('<div class="cv-guide">' + icon('check', 20) + '<div><b>You are viewing this drawing and the sizes Civora read from it.</b>Use + and − to zoom. Only the project team can change it.</div></div>')
        return layout(request, f'Drawing Studio · {cur["original_name"]}',
                      f'<span class="eyebrow">DRAWING STUDIO · வரைபட ஸ்டுடியோ</span><h1 style="margin-bottom:12px">Drawing Studio</h1>{guide}'
                      f'<div class="ds">{left}{centre}{right}</div>{sched_html}{ZOOM_JS}')

    @app.get('/projects/{pid}/studio')
    def studio_home(request: Request, pid: str):
        p = owned_project(request, pid)
        files = drawings(pid)
        if files:
            return RedirectResponse(f'/projects/{pid}/studio/{files[0]["id"]}', 303)
        return studio_page(request, p, files, None, 0)

    @app.get('/projects/{pid}/studio/{fid}')
    def studio_file(request: Request, pid: str, fid: str, page: int = 0):
        p = owned_project(request, pid)
        files = drawings(pid)
        cur = next((f for f in files if f['id'] == fid), None)
        if cur is None:
            raise HTTPException(404, 'Drawing not found in this project')
        return studio_page(request, p, files, cur, page)
    # v3.1: /projects/{pid}/boq is the Cost Intelligence Center in studio_v310.py
