"""Civora AI v3.3 - Reports Center.

  /reports                          every project you can open, with its documents, estimate and review status
  /projects/{pid}/reports           project document center: each report with what is inside, open / download
  /projects/{pid}/reports/summary   printable one-page project report (Print / save PDF)

Read-only: every download link points at an EXISTING export route (BOQ Excel / PDF, structural Excel / PDF / CSV,
review report, takeoff CSV, Download All ZIP). No calculation is reimplemented; the summary shows the values stored
by the existing modules. Access uses the same project roles as every other project page.
"""
import json
import time
from collections import OrderedDict

from ui_shell import esc, icon, inr_short
import workflow_v250 as wf

TYPE_COLOURS = dict(wf.TYPE_COLOURS, PRINT=('#e2e8f0', '#334155'))
SHORT = OrderedDict((('summary', 'Summary'), ('boq', 'BOQ'), ('structural', 'Structural'), ('details', 'Detail sheet'), ('review', 'Review'), ('takeoffs', 'Takeoffs')))
import detailing_v320 as _dv
DETAIL_KINDS = _dv.DETAILABLE
STATUS = {'draft': ('Draft', 'st-draft'), 'input': ('Needs input', 'st-input'), 'progress': ('In progress', 'st-progress'),
          'review': ('Needs review', 'st-review'), 'checked': ('Checked', 'st-checked')}


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(ts):
    try:
        return time.strftime('%d %b %Y', time.localtime(int(ts))) if ts else ''
    except (TypeError, ValueError, OverflowError, OSError):
        return ''


def documents(pid, st):
    """Every report this project can produce: dicts with key, title, ta, sub, kind, files [(type, url)], ready, todo (label, url)."""
    P = f'/projects/{pid}'
    docs = []
    has_cost = st['cost']['total'] > 0
    docs.append({'key': 'summary', 'title': 'Project summary report', 'ta': 'திட்ட சுருக்க அறிக்கை',
                 'sub': 'Cost, materials, structural totals, steel and review status on one printable page',
                 'files': [('PRINT', P + '/reports/summary')], 'ready': bool(has_cost or st['structural_items'] or st['takeoffs']),
                 'todo': ('Run an estimate first', P + '/smart')})
    boq = st.get('boq')
    if boq:
        base = f"{P}/drawings/{boq['drawing_id']}/boq/{boq['id']}"
        files = [('XLSX', base + '/excel'), ('PDF', base + '/pdf')]
    else:
        files = []
    docs.append({'key': 'boq', 'title': 'Material BOQ', 'ta': 'பொருள் பட்டியல் (BOQ)', 'sub': 'Every material with quantity, rate and amount',
                 'files': files, 'ready': bool(boq), 'todo': ('Run Quick or Smart Estimate', P + '/smart')})
    has_struct = bool(st['structural_items'] or st['bar_count'])
    s = P + '/structural/advanced/export'
    docs.append({'key': 'structural', 'title': 'Structural quantities & BBS', 'ta': 'கட்டமைப்பு அளவுகள் & BBS',
                 'sub': 'Concrete, formwork, steel by element and the bar bending schedule',
                 'files': [('XLSX', s + '.xlsx'), ('PDF', s + '.pdf'), ('CSV', s + '.csv')] if has_struct else [],
                 'ready': has_struct, 'todo': ('Add elements in Structural Studio', P + '/structure')})
    n_detail = sum(1 for i in st['structural_items'] if i['kind'] in DETAIL_KINDS)
    docs.append({'key': 'details', 'title': 'Site detail sheet', 'ta': 'தள விவரத் தாள்',
                 'sub': 'Where the rods go, bend and lap - footing, column, beam, slab sketches',
                 'files': [('PRINT', P + '/structure/details')] if n_detail else [], 'ready': bool(n_detail),
                 'todo': ('Add a footing, column, beam or slab', P + '/structure')})
    docs.append({'key': 'review', 'title': 'Structural review report', 'ta': 'கட்டமைப்பு மதிப்பாய்வு',
                 'sub': 'Reconciliation of design inputs against measured quantities',
                 'files': [('HTML', P + '/structural/review/report.html'), ('CSV', P + '/structural/review/export.csv')] if has_struct else [],
                 'ready': has_struct, 'todo': ('Add elements in Structural Studio', P + '/structure')})
    if st['takeoffs']:
        docs.append({'key': 'takeoffs', 'title': 'Material takeoffs', 'ta': 'பொருள் கணக்கீடுகள்', 'sub': f'{len(st["takeoffs"])} saved takeoff(s)',
                     'files': [('CSV', P + '/takeoff/export.csv')], 'ready': True, 'todo': None})
    any_ready = any(d['ready'] for d in docs)
    docs.append({'key': 'all', 'title': 'Download all (ZIP)', 'ta': 'அனைத்தையும் பதிவிறக்கு', 'sub': 'Summary, BOQ Excel + PDF, structural and takeoff CSV in one file',
                 'files': [('ZIP', P + '/workflow/download-all')] if any_ready else [], 'ready': any_ready, 'todo': ('Run an estimate first', P + '/smart')})
    return docs


def ready_count(docs):
    return sum(1 for d in docs if d['ready'] and d['key'] != 'all'), sum(1 for d in docs if d['key'] != 'all')


def _ago(ts):
    import studio_v300
    try:
        return studio_v300._ago(ts) if ts else ''
    except Exception:
        return _date(ts)


def _chip(typ):
    bg, fg = TYPE_COLOURS.get(typ, ('#eef2f7', '#475569'))
    return f'<span class="rc-ty" style="background:{bg};color:{fg}">{esc(typ)}</span>'


def _file_btn(typ, url):
    label = {'PRINT': 'Open & print', 'HTML': 'Open', 'ZIP': 'Download ZIP'}.get(typ, typ)
    ic = 'report' if typ in ('PRINT', 'HTML') else 'download'
    return f'<a class="cv-btn sm{"" if typ in ("PRINT", "ZIP") else " ghost"}" href="{esc(url)}">{icon(ic, 15)}{esc(label)}</a>'


# ------------------------------------------------------------------ preview of what is inside each document
def preview(doc, st, project):
    k = doc['key']
    if not doc['ready']:
        return f'<p class="sub">Not ready yet.</p>'
    if k in ('summary', 'all'):
        rows = ''.join(f'<tr><td>{esc(n)}</td><td class="r">{inr_short(v)}</td></tr>' for n, v, _ in st['cost']['segments'] if v)
        return f'<table class="cv-mt">{rows}<tr><td><b>Total</b></td><td class="r"><b>{inr_short(st["cost"]["total"])}</b></td></tr></table>'
    if k == 'boq':
        data = st['boq']['data']
        lines = [(r.get('work', ''), i) for r in data.get('rows', []) for i in r.get('items', [])]
        top = sorted(lines, key=lambda x: -_f(x[1].get('quantity')) * _f(x[1].get('rate')))[:6]
        rows = ''.join(f'<tr><td>{esc(i.get("material", ""))}<small class="rc-s">{esc(w)}</small></td><td class="r">{_f(i.get("quantity")):,.2f} {esc(i.get("unit", ""))}</td>'
                       f'<td class="r">{inr_short(_f(i.get("quantity")) * _f(i.get("rate")))}</td></tr>' for w, i in top)
        return (f'<p class="sub">{len(lines)} lines · saved {_date(st["boq"]["created"])} · biggest items:</p>'
                f'<table class="cv-mt"><tr><th>Material</th><th class="r">Qty</th><th class="r">Amount</th></tr>{rows}</table>')
    if k in ('structural', 'review'):
        t = st['structural_totals']
        rows = [('Elements', f'{len(st["structural_items"])}'), ('Bar marks', f'{st["bar_count"]}'),
                ('RCC concrete', f'{t["rcc_m3"]:,.2f} m³'), ('Formwork', f'{t["formwork_m2"]:,.1f} m²'), ('Steel', f'{t["steel_kg"]:,.0f} kg')]
        if k == 'review':
            so = st.get('signoff')
            rows.append(('Engineer sign-off', f'{so["who"]} · {_date(so["at"])}' if so else 'Not signed off yet'))
        return '<table class="cv-mt">' + ''.join(f'<tr><td>{esc(a)}</td><td class="r"><b>{esc(b)}</b></td></tr>' for a, b in rows) + '</table>'
    if k == 'details':
        marks = [i['reference'] for i in st['structural_items'] if i['kind'] in DETAIL_KINDS]
        return f'<p class="sub">{len(marks)} drawing(s): {esc(", ".join(marks[:12]))}{" …" if len(marks) > 12 else ""}</p>'
    if k == 'takeoffs':
        mats, n, src = wf.material_summary(st, limit=6)
        return '<table class="cv-mt">' + ''.join(f'<tr><td>{esc(m)}</td><td class="r">{q:,.2f} {esc(u)}</td></tr>' for m, q, u in mats) + '</table>'
    return ''


DIS = (f'<p class="cv-disclaim">{icon("shield", 16)}<span>Reports are planning estimates. Structural quantities are measured values, '
       'not a validated design — DESIGN INCOMPLETE, ENGINEER REVIEW REQUIRED until a licensed engineer approves the design.</span></p>')


def project_reports_html(project, st, role):
    pid = project['id']
    P = f'/projects/{pid}'
    docs = documents(pid, st)
    ready, total = ready_count(docs)
    so = st.get('signoff')
    allzip = next(d for d in docs if d['key'] == 'all')
    head = (f'<div class="cv-ph"><div><span class="eyebrow">REPORTS · அறிக்கைகள்</span><h1>Project reports</h1>'
            f'<div class="meta">{esc(project["name"])} · every document in one place — open, print or download</div></div>'
            + (_file_btn('ZIP', allzip['files'][0][1]) if allzip['ready'] else '') + '</div>')
    kpi = [('Estimate', inr_short(st['cost']['total']) if st['cost']['total'] else '—', 'materials + charges + structural'),
           ('Documents ready', f'{ready} of {total}', 'the rest show what to do'),
           ('Estimate revisions', str(st['boq_count']), f'latest {_date(st["boq"]["created"])}' if st.get('boq') else 'no BOQ saved yet'),
           ('Engineer review', 'Signed off' if so else ('Pending' if st['structural_items'] or st.get('boq_frame') else '—'),
            f'{so["who"]} · {_date(so["at"])}' if so else 'needed before construction')]
    out = [head, '<div class="cc-kpis rc-k4">' + ''.join(f'<div class="cc-kpi"><small>{esc(a)}</small><b>{esc(b)}</b><em>{esc(c)}</em></div>' for a, b, c in kpi) + '</div>']
    cards = []
    for d in docs:
        if d['key'] == 'all':
            continue
        chips = ''.join(_chip(t) for t, _ in d['files']) if d['ready'] else '<span class="cv-status st-draft">Not ready</span>'
        if d['ready']:
            acts = ''.join(_file_btn(t, u) for t, u in d['files'])
        elif d['todo'] and role in ('owner', 'engineer', 'colleague'):
            acts = f'<a class="cv-btn sm ghost" href="{esc(d["todo"][1])}">{esc(d["todo"][0])} {icon("arrow", 14)}</a>'
        else:
            acts = '<span class="sub">The project team has not prepared this yet.</span>'
        cards.append(f'<section class="cv-card rc-doc{"" if d["ready"] else " off"}" id="doc-{d["key"]}"><div class="rc-dh">{icon("report", 20)}'
                     f'<div><h3>{esc(d["title"])}</h3><span class="ta">{esc(d["ta"])}</span></div><span class="rc-chips">{chips}</span></div>'
                     f'<p class="sub">{esc(d["sub"])}</p><div class="rc-pv">{preview(d, st, project)}</div><div class="rc-acts">{acts}</div></section>')
    out.append('<div class="rc-grid">' + ''.join(cards) + '</div>')
    out.append(DIS)
    return ''.join(out)


# ------------------------------------------------------------------ printable summary
def steel_by_dia(c, pid):
    out = OrderedDict()
    try:
        rows = c.execute('SELECT payload FROM civora_bbs_v210 WHERE project_id=?', (pid,)).fetchall()
    except Exception:
        return out
    tmp = {}
    for r in rows:
        try:
            pl = json.loads(r['payload'])
            d = int(_f(pl.get('diameter_mm')))
            tmp.setdefault(d, [0.0, 0.0])
            tmp[d][0] += _f(pl['result'].get('steel_kg'))
            tmp[d][1] += _f(pl['result'].get('order_steel_kg')) or _f(pl['result'].get('steel_kg'))
        except (TypeError, ValueError, KeyError):
            continue
    for d in sorted(tmp):
        out[d] = tmp[d]
    return out


def summary_html(project, st, by_dia, members):
    P = f'/projects/{project["id"]}'
    seg = ''.join(f'<tr><td>{esc(n)}</td><td class="r">₹ {v:,.0f}</td></tr>' for n, v, _ in st['cost']['segments'] if v)
    area = _f(project['area'])
    cost = (f'<table class="cv-mt">{seg}<tr class="rc-tot"><td>Total estimate</td><td class="r">₹ {st["cost"]["total"]:,.0f}</td></tr>'
            + (f'<tr><td>Per sq.ft ({area:,.0f} sq.ft)</td><td class="r">₹ {st["cost"]["total"] / area:,.0f}</td></tr>' if area and st['cost']['total'] else '')
            + '</table>') if st['cost']['total'] else '<p class="sub">No priced estimate yet.</p>'
    if st['cost']['unrated']:
        cost += f'<p class="rc-warn">{st["cost"]["unrated"]} material line(s) have no rate — the total is incomplete.</p>'
    mats, n, src = wf.material_summary(st, limit=14)
    mat = ('<table class="cv-mt"><tr><th>Material</th><th class="r">Quantity</th></tr>'
           + ''.join(f'<tr><td>{esc(m)}</td><td class="r">{q:,.2f} {esc(u)}</td></tr>' for m, q, u in mats) + '</table>'
           + f'<p class="sub">{esc(src)}{f" · showing {len(mats)} of {n}" if n > len(mats) else ""}</p>') if mats else '<p class="sub">No materials yet.</p>'
    t = st['structural_totals']
    struct = ''
    if st['structural_items']:
        struct = ('<table class="cv-mt">' + ''.join(f'<tr><td>{esc(a)}</td><td class="r">{esc(b)}</td></tr>' for a, b in (
            ('Elements measured', str(len(st['structural_items']))), ('RCC concrete (net)', f'{t["rcc_m3"]:,.2f} m³'),
            ('RCC to order', f'{t["rcc_order_m3"]:,.2f} m³'), ('PCC', f'{t["pcc_m3"]:,.2f} m³'), ('Excavation', f'{t["excavation_m3"]:,.2f} m³'),
            ('Formwork', f'{t["formwork_m2"]:,.1f} m²'), ('Steel (BBS)', f'{t["steel_kg"]:,.0f} kg'))) + '</table>')
    elif st.get('boq_frame'):
        fr = st['boq_frame']
        struct = (f'<table class="cv-mt"><tr><td>Preliminary columns</td><td class="r">{fr["columns"]}</td></tr><tr><td>RCC (frame)</td><td class="r">{fr["rcc_m3"]:,.2f} m³</td></tr>'
                  f'<tr><td>Steel planning allowance</td><td class="r">{fr["steel_kg"]:,.0f} kg</td></tr></table><p class="sub">From the estimate - a planning allowance, not a BBS.</p>')
    steel = ''
    if by_dia:
        steel = ('<table class="cv-mt"><tr><th>Diameter</th><th class="r">Theoretical</th><th class="r">To order</th></tr>'
                 + ''.join(f'<tr><td>{d} mm</td><td class="r">{v[0]:,.1f} kg</td><td class="r">{v[1]:,.1f} kg</td></tr>' for d, v in by_dia.items())
                 + f'<tr class="rc-tot"><td>Total</td><td class="r">{sum(v[0] for v in by_dia.values()):,.1f} kg</td><td class="r">{sum(v[1] for v in by_dia.values()):,.1f} kg</td></tr></table>')
    so = st.get('signoff')
    review = (f'<p><span class="cv-status st-checked">Signed off</span> {esc(so["who"])} ({esc(so["role"])}) on {_date(so["at"])}'
              + (f' — “{esc(so["note"])}”' if so['note'] else '') + '</p>') if so else '<p><span class="cv-status st-review">Not signed off</span> An engineer must review the design before construction.</p>'
    team = ', '.join(f'{esc(m["name"])} ({esc(m["role"])})' for m in members) or 'Owner only'
    steps = ''.join(f'<li class="{"ok" if k in st["done"] else ""}">{esc(tt)}</li>' for k, _, tt, *_ in wf.STEPS)

    def sec(title, ta, body):
        return f'<section class="rc-sec"><h2>{esc(title)} <span class="ta">{esc(ta)}</span></h2>{body}</section>' if body else ''
    return (f'<div class="cv-ph rc-noprint"><div><span class="eyebrow">REPORTS · அறிக்கைகள்</span><h1>Project summary report</h1>'
            f'<div class="meta">Print this page or save it as PDF from the print window</div></div>'
            f'<div class="rc-acts"><a class="cv-btn ghost" href="{P}/reports">Back to reports</a>'
            f'<button class="cv-btn" type="button" onclick="window.print()">{icon("download", 16)} Print / save PDF</button></div></div>'
            f'<article class="cv-card rc-paper"><header class="rc-ph"><div><b class="rc-brand">Civora AI</b><h1>{esc(project["name"])}</h1>'
            f'<div class="sub">{esc(project["type"])} · {esc(project["location"])} · {_f(project["area"]):,.0f} sq.ft built-up</div></div>'
            f'<div class="rc-meta">Prepared {time.strftime("%d %b %Y")}<br>Estimate revisions: {st["boq_count"]}</div></header>'
            f'<ul class="rc-steps">{steps}</ul>'
            '<div class="rc-two">' + sec('Cost summary', 'செலவு சுருக்கம்', cost) + sec('Main materials', 'முக்கிய பொருட்கள்', mat) + '</div>'
            '<div class="rc-two">' + sec('Structural quantities', 'கட்டமைப்பு அளவுகள்', struct) + sec('Steel order by diameter', 'கம்பி ஆர்டர்', steel) + '</div>'
            + sec('Engineer review', 'பொறியாளர் ஒப்புதல்', review + f'<p class="sub">Project team: {team}</p>')
            + '<p class="rc-dis"><b>DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.</b> Quantities and costs are planning estimates from the '
              'values entered or read from drawings. They are not a structural design and do not certify compliance with any code. '
              'A qualified, licensed engineer must check and approve the design before construction.</p></article>')


# ------------------------------------------------------------------ cross-project center
def center_rows(c, uid, project_rows):
    rows = []
    for r in project_rows(c, uid):
        docs = documents(r['p']['id'], r['st'])
        rd, tot = ready_count(docs)
        rows.append(dict(r, docs=docs, ready=rd, total=tot))
    return rows


def center_html(rows, q='', show=''):
    ql = q.strip().lower()
    vis = [r for r in rows if (not ql or ql in f'{r["p"]["name"]} {r["p"]["type"]} {r["p"]["location"]}'.lower())
           and (show != 'ready' or r['ready']) and (show != 'review' or r['status'] == 'review')]
    allr = sum(r['ready'] for r in rows)
    kpi = [('Projects', str(len(rows)), 'you own or were invited to'), ('Documents ready', str(allr), 'across all projects'),
           ('Total estimate', inr_short(sum(r['st']['cost']['total'] for r in rows)), 'sum of the latest estimates'),
           ('Needs engineer review', str(sum(1 for r in rows if r['status'] == 'review')), 'design not signed off')]
    head = ('<div class="cv-ph"><div><span class="eyebrow">REPORTS CENTER · அறிக்கை மையம்</span><h1>Reports</h1>'
            '<div class="meta">Every project’s documents in one place — open a project to preview, print or download</div></div></div>'
            '<div class="cc-kpis rc-k4">' + ''.join(f'<div class="cc-kpi"><small>{esc(a)}</small><b>{esc(b)}</b><em>{esc(c)}</em></div>' for a, b, c in kpi) + '</div>')
    opts = ''.join(f'<option value="{k}"{" selected" if show == k else ""}>{esc(v)}</option>' for k, v in (('', 'All projects'), ('ready', 'With reports ready'), ('review', 'Needs engineer review')))
    filt = (f'<form class="rc-filter" method="get" action="/reports"><input name="q" value="{esc(q)}" placeholder="Search by name, type or location" aria-label="Search reports">'
            f'<select name="show" aria-label="Filter">{opts}</select><button class="cv-btn sm">Filter</button></form>')
    if not rows:
        return head + ('<div class="cv-empty" style="margin-top:16px"><b>No projects yet</b>Create a project and run an estimate — its reports appear here.'
                       f'<div class="actions" style="justify-content:center"><a class="cv-btn" href="/projects/new">{icon("plus", 16)} New project</a></div></div>')
    trs = ''
    for r in vis:
        p, st = r['p'], r['st']
        P = f'/projects/{p["id"]}'
        chips = ''.join(f'<span class="rc-tag">{esc(SHORT[d["key"]])}</span>' for d in r['docs'] if d['ready'] and d['key'] in SHORT) or '<span class="sub">none yet</span>'
        lab, cls = STATUS.get(r['status'], ('', 'st-draft'))
        zipd = next(d for d in r['docs'] if d['key'] == 'all')
        trs += (f'<tr><td><a href="{P}/reports"><b>{esc(p["name"])}</b></a><small class="rc-s">{esc(p["type"])} · {esc(p["location"])} · {esc(str(r["role"]).title())}</small></td>'
                f'<td><span class="cv-status {cls}">{esc(lab)}</span></td><td><div class="rc-chips">{chips}</div><small class="rc-s">{r["ready"]} of {r["total"]} ready</small></td>'
                f'<td class="r"><b>{inr_short(st["cost"]["total"]) if st["cost"]["total"] else "—"}</b></td><td>{esc(_ago(r.get("updated")))}</td>'
                f'<td class="rc-acts"><a class="cv-btn sm ghost" href="{P}/reports">Open</a>'
                + (f'<a class="cv-btn sm ghost" href="{P}/workflow/download-all" aria-label="Download all for {esc(p["name"])}">{icon("download", 15)}ZIP</a>' if zipd['ready'] else '')
                + '</td></tr>')
    table = (f'<section class="cv-card" style="margin-top:14px">{filt}<div class="scroll"><table class="cv-mt rc-table"><tr><th>Project</th><th>Status</th>'
             f'<th>Documents</th><th class="r">Estimate</th><th>Updated</th><th></th></tr>'
             + (trs or '<tr><td colspan="6">No projects match this filter.</td></tr>') + '</table></div></section>')
    return head + table + DIS


# ------------------------------------------------------------------ routes
def register_reports_v330(app, db, owned_project, require, layout):
    from fastapi import Request
    import studio_v300

    @app.get('/reports')
    def reports_center(request: Request):
        u = require(request)
        with db() as c:
            rows = center_rows(c, u['id'], studio_v300.project_rows)
        q = request.query_params
        show = q.get('show', '') if q.get('show', '') in ('', 'ready', 'review') else ''
        return layout(request, 'Reports', center_html(rows, q.get('q', '')[:80], show))

    @app.get('/projects/{pid}/reports')
    def project_reports(request: Request, pid: str):
        p = owned_project(request, pid)
        with db() as c:
            st = wf.project_status(c, pid)
        return layout(request, f'{p["name"]} · Reports', project_reports_html(p, st, getattr(request.state, 'cv_role', 'owner')))

    @app.get('/projects/{pid}/reports/summary')
    def project_summary(request: Request, pid: str):
        p = owned_project(request, pid)
        with db() as c:
            st = wf.project_status(c, pid)
            by_dia = steel_by_dia(c, pid)
            try:
                members = c.execute('SELECT u.name, m.role FROM civora_members_v270 m JOIN users u ON u.id=m.user_id WHERE m.project_id=? ORDER BY m.added_at',
                                    (pid,)).fetchall()
            except Exception:
                members = []
        return layout(request, f'{p["name"]} · Summary report', summary_html(p, st, by_dia, members))
