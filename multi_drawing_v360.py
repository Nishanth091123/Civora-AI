"""Civora AI v3.6.0 - Multi-drawing analysis.

Upload or pick several drawings (and every page of a multi-page PDF) at once:
  1. Each sheet is read separately (same reader as Smart Estimate). One unreadable sheet
     never stops the others.
  2. A comparison table shows what was read from each sheet, flags duplicates, sizes that
     disagree between sheets, and sheets that could not be read.
  3. You mark each sheet as Ground / First / Second / Third floor plan, Section/details
     (used only to fill missing heights, thicknesses, plaster), or Not used.
  4. Combined estimate: every floor plan is measured on its OWN sizes (upper floors may be
     smaller or larger), the top floor gets roof waterproofing, and the preliminary RCC frame
     is taken once from the ground floor for all floors. Saved as a normal draft BOQ.
No new tables. Structure remains PRELIMINARY - engineer review required.
"""
import copy
import hashlib
import json
import re
import time
import uuid
from collections import OrderedDict
from pathlib import Path

import smart_estimate_v260 as se

MAX_SHEETS = 8
FRAME_ROWS = ('Excavation for footings', 'PCC 1:4:8 below footings', 'RCC footings', 'RCC columns', 'RCC plinth beam',
              'RCC floor/roof beams', 'Backfilling around footings', 'Formwork – footings', 'RCC staircase', 'Staircase formwork')
ROLES = OrderedDict([('gf', 'Ground floor plan'), ('ff', 'First floor plan'), ('sf', 'Second floor plan'),
                     ('tf', 'Third floor plan'), ('section', 'Section / elevation / details'), ('skip', 'Not used')])
FLOOR_ROLES = ('gf', 'ff', 'sf', 'tf')
FLOOR_SHORT = {'gf': 'GF', 'ff': 'FF', 'sf': 'SF', 'tf': 'TF'}
# evidence a section / other sheet may supply when a floor plan does not show it
FILL_KEYS = ('height', 'slab_thickness', 'external_thickness', 'internal_thickness', 'external_plaster_thickness',
             'internal_plaster_thickness', 'kitchen_tile_area_each', 'bathroom_tile_area_each')
SIZE_KEYS = ('overall_length', 'overall_width')
SHOWN = [('overall_length', 'Length', 'm'), ('overall_width', 'Width', 'm'), ('floor_area', 'Floor area', 'm²'),
         ('height', 'Height', 'm'), ('slab_thickness', 'Slab', 'm'), ('external_thickness', 'Ext. wall', 'm')]

_CACHE = OrderedDict()          # (fid, page, size, mtime) -> schedule


# ------------------------------------------------------------------ pure helpers (unit tested)
def guess_role(name, schedule, used):
    """Role from the file name first (ground/first/section...), else by whether a plan size was read."""
    n = re.sub(r'[^a-z0-9]+', ' ', str(name).lower())
    pats = [('gf', r'\b(ground|gf|g f|gnd)\b'), ('ff', r'\b(first|ff|f f|1st)\b'), ('sf', r'\b(second|sf|2nd)\b'),
            ('tf', r'\b(third|tf|3rd)\b'), ('section', r'\b(section|elevation|elev|detail|details|sec|structural)\b')]
    for role, pat in pats:
        if re.search(pat, n) and (role == 'section' or role not in used):
            return role
    ev = (schedule or {}).get('evidence') or {}
    if all(k in ev for k in SIZE_KEYS) or (schedule or {}).get('rooms'):
        for r in FLOOR_ROLES:
            if r not in used:
                return r
    return 'section'


def sheet_status(schedule):
    ev = (schedule or {}).get('evidence') or {}
    if not schedule or schedule.get('method') in ('unavailable', 'not readable'):
        return 'bad', 'Could not be read'
    if all(k in ev for k in SIZE_KEYS):
        return 'ok', f'{len(ev)} value(s), {len(schedule.get("rooms") or [])} room(s), {len(schedule.get("openings") or [])} opening type(s)'
    if ev:
        return 'part', f'{len(ev)} value(s) read, no overall plan size'
    return 'bad', 'No sizes found'


def compare(sheets):
    """Checks across sheets. sheets: list of dicts(name, role, schedule, digest). Returns list of (level, text)."""
    out = []
    seen = {}
    for s in sheets:
        if s['digest'] in seen:
            out.append(('warn', f'“{s["name"]}” is the same file as “{seen[s["digest"]]}” – it will be counted only once.'))
        else:
            seen[s['digest']] = s['name']
    plans = [s for s in sheets if s['role'] in FLOOR_ROLES]
    roles = [s['role'] for s in plans]
    for r in set(roles):
        if roles.count(r) > 1:
            out.append(('bad', f'More than one sheet is marked as {ROLES[r]}. Mark each floor once.'))
    if plans and 'gf' not in roles:
        out.append(('bad', 'No sheet is marked as Ground floor plan. The structure (footings, columns) is taken from the ground floor.'))
    order = [r for r in FLOOR_ROLES if r in roles]
    if order and order != list(FLOOR_ROLES[:len(order)]):
        out.append(('warn', 'Floors are not continuous (e.g. Ground + Second without First). Check the floor marks.'))
    def ev(s, k):
        e = (s['schedule'].get('evidence') or {}).get(k)
        return float(e['value']) if e and e.get('value') else None
    gf = next((s for s in plans if s['role'] == 'gf'), None)
    if gf and ev(gf, 'overall_length') and ev(gf, 'overall_width'):
        ga = ev(gf, 'overall_length') * ev(gf, 'overall_width')
        for s in plans:
            if s is gf or not (ev(s, 'overall_length') and ev(s, 'overall_width')):
                continue
            a = ev(s, 'overall_length') * ev(s, 'overall_width')
            if a > ga * 1.05:
                out.append(('warn', f'{ROLES[s["role"]]} ({a:.1f} m²) is LARGER than the ground floor ({ga:.1f} m²) – projections/cantilevers need an engineer\'s design.'))
            elif a < ga * 0.95:
                out.append(('info', f'{ROLES[s["role"]]} ({a:.1f} m²) is smaller than the ground floor ({ga:.1f} m²) – each floor is measured on its own size.'))
    for k, label in (('height', 'Floor height'), ('slab_thickness', 'Slab thickness'), ('external_thickness', 'External wall thickness')):
        vals = {round(v, 3) for v in (ev(s, k) for s in sheets if s['role'] != 'skip') if v}
        if len(vals) > 1:
            out.append(('warn', f'{label} differs between sheets ({", ".join(f"{v:g} m" for v in sorted(vals))}). Each floor keeps its own value – check them.'))
    for s in sheets:
        if s['role'] != 'skip' and sheet_status(s['schedule'])[0] == 'bad':
            out.append(('bad', f'“{s["name"]}” could not be read – sizes for it must be entered by hand, or mark it Not used.'))
    if not plans:
        out.append(('bad', 'Mark at least one sheet as a floor plan to make an estimate.'))
    return out


def fill_from(plan_schedule, others):
    """Copy of a floor plan schedule with missing heights/thicknesses taken from the other sheets."""
    sch = copy.deepcopy(plan_schedule or {})
    ev = sch.setdefault('evidence', {})
    for o in others:
        for k in FILL_KEYS:
            e = (o['schedule'].get('evidence') or {}).get(k)
            if k not in ev and e and e.get('value'):
                ev[k] = {'value': e['value'], 'source': f'{e.get("source", "")} (from {o["name"]})'.strip()}
    return sch


def combined_estimate(floors, opts, takeoff):
    """floors: ordered list of (label, inputs, schedule) - ground floor first.
    Each floor is estimated with its own sizes; frame once from the ground floor for all floors."""
    if not floors:
        raise ValueError('Mark at least one sheet as a floor plan')
    n = len(floors)
    rows, breakdown, notes, skipped = [], [], [], []
    sqft = 0.0
    for i, (label, inp, sch) in enumerate(floors):
        one = OrderedDict((k, dict(v)) for k, v in inp.items())
        one['floors'] = {'value': 1, 'source': 'derived', 'note': 'One sheet = one floor'}
        top = i == n - 1
        if not top:
            one['roof_wp'] = {'value': 0, 'source': 'derived', 'note': 'Waterproofing only on the top roof'}
        r = se.estimate(one, opts, takeoff, sch, frame_rows=False, ground=(i == 0))
        rows += [[f'{label}: {w}', a, items] for w, a, items in r['rows']]
        breakdown += [(f'{label}: {m}', q, u) for m, q, u in r['breakdown'] if m != 'Number of floors']
        skipped += [f'{label}: {s}' for s in r['skipped'] if not (not top and s.startswith('Roof waterproofing'))]
        notes += [x for x in r['notes'] if x not in notes]
        sqft += r['builtup_sqft']
    frame = {}
    if opts.get('frame') or n > 1:
        g = OrderedDict((k, dict(v)) for k, v in floors[0][1].items())
        g['floors'] = {'value': n, 'source': 'derived', 'note': f'{n} floor plan(s)'}
        r = se.estimate(g, opts, takeoff, floors[0][2])
        rows += [[w, a, items] for w, a, items in r['rows'] if w.startswith(FRAME_ROWS)]
        frame = r['frame']
        keep = ('Columns (preliminary count)', 'Footing excavation', 'RCC footings', 'RCC columns',
                'Beam length per level (perimeter + internal walls)', 'RCC beams (plinth + floors)')
        breakdown += [(f'Frame: {m}', q, u) for m, q, u in r['breakdown'] if m in keep]
        notes += [x for x in r['notes'] if x.startswith('STRUCTURE IS PRELIMINARY') and x not in notes]
        if n > 1:
            notes.append(f'Preliminary frame (columns, beams, footings) uses the ground floor layout for all {n} floors.')
    breakdown.insert(0, ('Number of floors', n, 'nos'))
    breakdown.insert(1, ('Built-up area (all floors)', sqft / se.SQFT_PER_M2, 'm²'))
    notes.insert(0, f'Combined estimate from {n} floor plan(s): ' + ', '.join(l for l, _, _ in floors) + '. Each floor measured on its own drawing sizes.')
    return {'rows': rows, 'breakdown': breakdown, 'notes': notes, 'skipped': skipped, 'frame': frame,
            'basis_label': se.BASES[opts['basis']], 'builtup_sqft': sqft}


# ------------------------------------------------------------------ web pages
def register_multi_drawing_v360(app, db, owned_project, require, csrf, check_csrf, layout, esc, FILES, takeoff, store_upload):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    from ui_shell import icon
    import rates_v260

    def drawings_of(pid):
        with db() as c:
            return [r for r in c.execute('SELECT * FROM uploads WHERE project_id=? ORDER BY created DESC', (pid,)).fetchall()
                    if str(r['original_name']).lower().endswith(se.DRAWING_EXT)]

    def pdf_pages(path):
        if path.suffix.lower() != '.pdf':
            return 1
        try:
            import fitz
            with fitz.open(str(path)) as d:
                return max(len(d), 1)
        except Exception:
            return 1

    def read(path, page):
        st = path.stat()
        key = (str(path), page, st.st_size, st.st_mtime_ns)
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        try:
            from drawing_schedule import extract
            sch = extract(path, page)
        except Exception as ex:
            sch = {'evidence': {}, 'rooms': [], 'openings': [], 'method': 'unavailable',
                   'warnings': [f'Could not read this sheet ({type(ex).__name__}).']}
        _CACHE[key] = sch
        while len(_CACHE) > 60:
            _CACHE.popitem(last=False)
        return sch

    def load_sheets(pid, ids, roles=None):
        """ids like 'fid' or 'fid:page'. Returns sheet dicts in the given order."""
        rows = {r['id']: r for r in drawings_of(pid)}
        sheets, used = [], set()
        for sid in ids[:MAX_SHEETS]:
            fid, _, pg = sid.partition(':')
            r = rows.get(fid)
            if not r:
                continue
            path = FILES / r['stored_name']
            if not path.is_file():
                continue
            page = int(pg) if pg.isdigit() else 0
            sch = read(path, page)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:20] + f':{page}'
            name = r['original_name'] + (f' (page {page + 1})' if pg else '')
            role = (roles or {}).get(sid) if (roles or {}).get(sid) in ROLES else guess_role(name, sch, used)
            used.add(role)
            sheets.append({'id': sid, 'fid': fid, 'page': page, 'row': r, 'name': name, 'schedule': sch, 'role': role, 'digest': digest})
        # duplicates (same file uploaded twice) are not used twice
        seen = set()
        for s in sheets:
            if s['digest'] in seen and s['role'] != 'skip':
                s['role'], s['dup'] = 'skip', True
            seen.add(s['digest'])
        return sheets

    def expand(pid, ids):
        """Multi-page PDFs become one sheet per page."""
        rows = {r['id']: r for r in drawings_of(pid)}
        out = []
        for fid in ids:
            r = rows.get(fid.partition(':')[0])
            if not r:
                continue
            if ':' in fid:
                out.append(fid); continue
            n = pdf_pages(FILES / r['stored_name'])
            out += [fid] if n == 1 else [f'{fid}:{i}' for i in range(min(n, MAX_SHEETS))]
        return list(OrderedDict.fromkeys(out))[:MAX_SHEETS]

    def floor_plans(p, sheets):
        plans = sorted([s for s in sheets if s['role'] in FLOOR_ROLES], key=lambda s: FLOOR_ROLES.index(s['role']))
        others = [s for s in sheets if s['role'] == 'section'] + plans
        out = []
        for s in plans:
            sch = fill_from(s['schedule'], [o for o in others if o is not s])
            inp = se.build_inputs(sch, float(p['area'] or 0) / max(len(plans), 1))
            out.append((s, sch, inp))
        return out

    def qs(sheets):
        from urllib.parse import urlencode
        q = [('ids', ','.join(s['id'] for s in sheets))] + [(f'role_{s["id"]}', s['role']) for s in sheets]
        return urlencode(q)

    def parse_ids(v):
        return [x for x in re.split(r'[,\s]+', str(v or '')) if re.match(r'^[0-9a-fA-F-]{36}(:\d{1,2})?$', x)]

    # ---- 1. choose drawings
    @app.get('/projects/{pid}/multi')
    def multi_start(request: Request, pid: str):
        p = owned_project(request, pid)
        P = f'/projects/{pid}'
        existing = ''.join(f'<label class="cv-pick" style="flex-direction:row;align-items:center;gap:10px;padding:10px 12px">'
                           f'<input type="checkbox" name="ids" value="{esc(r["id"])}" style="width:auto">'
                           f'<span class="cv-pickt"><b>{esc(r["original_name"])}</b><small>Uploaded {time.strftime("%d %b %Y", time.localtime(r["created"]))}</small></span></label>'
                           for r in drawings_of(pid))
        existing = f'<h2 style="margin:22px 0 10px">Drawings already in this project</h2><div class="cv-picks">{existing}</div>' if existing else ''
        return layout(request, 'Multi-drawing analysis', f'''<span class="eyebrow">MULTI-DRAWING ANALYSIS · {esc(p["name"])}</span>
<h1>Analyse several drawings together</h1>
<p class="muted">Ground floor, first floor, sections… Civora reads every sheet, compares them and makes one combined estimate. Multi-page PDFs are split into pages automatically (up to {MAX_SHEETS} sheets).</p>
<form method="post" action="{P}/multi" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{csrf(request)}">
<div class="cv-drop">{icon("upload", 40)}<b>Upload drawings</b><span>Select several files at once – PDF, DXF, PNG or JPG · up to 30 MB each</span>
<input type="file" name="files" accept=".pdf,.dxf,.png,.jpg,.jpeg" multiple></div>
{existing}
<div class="actions"><button class="cv-btn">{icon("arrow", 16)} Read &amp; compare drawings</button><a class="cv-btn ghost" href="{P}/smart">Single drawing estimate</a></div></form>''')

    @app.post('/projects/{pid}/multi')
    async def multi_upload(request: Request, pid: str):
        owned_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        ids = [str(x) for x in form.getlist('ids')]
        files = [f for f in form.getlist('files') if hasattr(f, 'read') and getattr(f, 'filename', '')]
        if len(files) + len(ids) > MAX_SHEETS:
            raise HTTPException(400, f'Choose at most {MAX_SHEETS} drawings at a time')
        for f in files:
            name = f.filename or 'drawing'
            if not name.lower().endswith(se.DRAWING_EXT):
                raise HTTPException(400, f'{name}: upload PDF, DXF, PNG or JPG drawings')
            content = await f.read(30 * 1024 * 1024 + 1)
            ids.append(store_upload(pid, name, content, getattr(f, 'content_type', None)))
        ids = parse_ids(','.join(ids))
        if not ids:
            raise HTTPException(400, 'Upload or tick at least one drawing')
        from urllib.parse import urlencode
        return RedirectResponse(f'/projects/{pid}/multi/analyse?' + urlencode({'ids': ','.join(expand(pid, ids))}), 303)

    # ---- 2. comparison + roles
    @app.get('/projects/{pid}/multi/analyse')
    def multi_analyse(request: Request, pid: str):
        p = owned_project(request, pid)
        P = f'/projects/{pid}'
        qp = request.query_params
        ids = parse_ids(qp.get('ids'))
        sheets = load_sheets(pid, ids, {k[5:]: v for k, v in qp.items() if k.startswith('role_')})
        if not sheets:
            return RedirectResponse(f'{P}/multi', 303)
        checks = compare(sheets)
        stat_cls = {'ok': ('cv-src d', 'Read'), 'part': ('cv-src t', 'Partly read'), 'bad': ('cv-src w', 'Not read')}
        trs = ''
        for s in sheets:
            ev = s['schedule'].get('evidence') or {}
            st, txt = sheet_status(s['schedule'])
            cls, lab = stat_cls[st]
            vals = ''.join(f'<td>{float(ev[k]["value"]):g}</td>' if k in ev else '<td style="color:#94a3b8">—</td>' for k, _, _ in SHOWN)
            opts = ''.join(f'<option value="{k}"{" selected" if k == s["role"] else ""}>{esc(v)}</option>' for k, v in ROLES.items())
            thumb = f'{P}/drawings/{esc(s["fid"])}/media' + (f'?page={s["page"]}' if s['page'] else '')
            trs += (f'<tr><td><img src="{thumb}" alt="" loading="lazy" style="width:64px;height:48px;object-fit:cover;border-radius:6px;border:1px solid #dbe6f1"></td>'
                    f'<td><b>{esc(s["name"])}</b><br><small class="muted">{esc(s["schedule"].get("method", ""))}</small>'
                    + (' <small style="color:#b45309">duplicate</small>' if s.get('dup') else '') +
                    f'</td><td><span class="{cls}">{lab}</span><br><small class="muted">{esc(txt)}</small></td>{vals}'
                    f'<td><select name="role_{esc(s["id"])}" aria-label="Sheet type">{opts}</select>'
                    + (f'<br><a href="{P}/vastu/drawing/{esc(s["fid"])}" style="font-size:12px">Vastu check →</a>' if s['role'] in FLOOR_ROLES else '') + '</td></tr>')
        head = ''.join(f'<th>{esc(l)}<br><small>{u}</small></th>' for _, l, u in SHOWN)
        colours = {'bad': ('#fef2f2', '#fecaca', '#991b1b'), 'warn': ('#fffbeb', '#fde68a', '#92400e'), 'info': ('#eff6ff', '#bfdbfe', '#1e3a8a')}
        chk = ''.join(f'<div class="cv-review" style="margin:6px 0;background:{colours[l][0]};border-color:{colours[l][1]};color:{colours[l][2]}">'
                      f'{icon("shield", 16)}<span>{esc(t)}</span></div>' for l, t in checks) or \
            f'<div class="cv-review" style="background:#f0fdf4;border-color:#bbf7d0;color:#166534">{icon("check", 16)}<span>All sheets agree. Ready for the combined estimate.</span></div>'
        n_floor = sum(1 for s in sheets if s['role'] in FLOOR_ROLES)
        return layout(request, 'Multi-drawing analysis', f'''<span class="eyebrow">MULTI-DRAWING ANALYSIS · {esc(p["name"])}</span>
<h1>{len(sheets)} sheet(s) read</h1><p class="muted">Check what was read from each sheet and tell Civora what each sheet is. Change a sheet type and press <b>Update</b>.</p>
<form method="get" action="{P}/multi/analyse"><input type="hidden" name="ids" value="{esc(",".join(s["id"] for s in sheets))}">
<section class="cv-card"><div class="scroll"><table class="cv-mt"><tr><th></th><th>Sheet</th><th>Reading</th>{head}<th>This sheet is</th></tr>{trs}</table></div>
<div class="actions"><button class="cv-btn ghost sm" formaction="{P}/multi/analyse">Update</button></div></section>
<h2 style="margin:20px 0 8px">Checks</h2>{chk}
<div class="actions"><button class="cv-btn" formaction="{P}/multi/review" {"disabled" if not n_floor else ""}>{icon("arrow", 16)} Continue – check measurements ({n_floor} floor plan(s))</button>
<a class="cv-btn ghost" href="{P}/multi">Choose other drawings</a></div></form>''')

    # ---- 3. per-floor measurements
    def review_html(request, p, sheets, plans, error=''):
        P = f'/projects/{p["id"]}'
        chip = {'drawing': ('cv-src d', 'From drawing'), 'derived': ('cv-src w', 'Worked out'),
                'typical': ('cv-src t', 'Please check'), 'user': ('cv-src u', 'Your value')}
        floor_cards = ''
        for i, (s, sch, inp) in enumerate(plans):
            fields = ''
            for key, fen, fta, unit, grp, lo, hi, step in se.FIELDS:
                if grp == 'frame' or key == 'floors' or (key == 'plinth_h' and i > 0) or (key == 'parapet_h' and i < len(plans) - 1):
                    continue
                x = inp[key]
                cls, txt = chip[x['source']]
                val = ("%.3f" % x["value"]).rstrip("0").rstrip(".") if step < 1 else f'{int(round(x["value"]))}'
                fields += (f'<div class="cv-field {"need" if x["source"] == "typical" else ""}"><label for="f{i}_{key}"><b>{esc(fen)}</b><small>{esc(fta)}</small></label>'
                           f'<div class="cv-fin"><input id="f{i}_{key}" name="f{i}_{key}" type="number" min="{lo:g}" max="{hi:g}" step="{"1" if step >= 1 else "any"}" value="{val}"><span>{esc(unit)}</span></div>'
                           f'<div class="cv-fsrc"><span class="{cls}">{txt}</span><small title="{esc(x["note"])}">{esc(x["note"])[:90]}</small></div></div>')
            found, check = se.summary_counts(inp)
            floor_cards += (f'<details class="cv-card cv-group"{" open" if i == 0 else ""}><summary><b>{esc(ROLES[s["role"]])}</b> – {esc(s["name"])} '
                            f'<small>({found} read, {check} to check)</small></summary>{fields}</details>')
        g = plans[0][2]
        frame = ''
        for key, fen, fta, unit, grp, lo, hi, step in se.FIELDS:
            if grp != 'frame':
                continue
            x = g[key]
            val = ("%.3f" % x["value"]).rstrip("0").rstrip(".") if step < 1 else f'{int(round(x["value"]))}'
            frame += (f'<div class="cv-field need"><label for="fr_{key}"><b>{esc(fen)}</b><small>{esc(fta)}</small></label>'
                      f'<div class="cv-fin"><input id="fr_{key}" name="{key}" type="number" min="{lo:g}" max="{hi:g}" step="{"1" if step >= 1 else "any"}" value="{val}"><span>{esc(unit)}</span></div>'
                      f'<div class="cv-fsrc"><small>{esc(x["note"])[:90]}</small></div></div>')
        hidden = f'<input type="hidden" name="ids" value="{esc(",".join(s["id"] for s in sheets))}">' + ''.join(
            f'<input type="hidden" name="role_{esc(s["id"])}" value="{esc(s["role"])}">' for s in sheets)
        err = f'<div class="cv-review" style="margin:12px 0;background:#fef2f2;border-color:#fecaca;color:#991b1b">{esc(error)}</div>' if error else ''
        return layout(request, 'Multi-drawing – check measurements', f'''<span class="eyebrow">MULTI-DRAWING ANALYSIS · {esc(p["name"])}</span>
<h1>Check the measurements – {len(plans)} floor(s)</h1><p class="muted">Each floor uses its own sizes. Highlighted values were not on the drawing – replace them with real sizes.</p>{err}
<form method="post" action="{P}/multi/estimate"><input type="hidden" name="csrf_token" value="{csrf(request)}">{hidden}
<div class="cv-groups">{floor_cards}
<section class="cv-card cv-group"><h3>Structure – from the ground floor, for all floors (preliminary)</h3>
<label class="checkline"><input type="checkbox" name="frame" value="yes" checked> Include RCC frame (columns, beams, footings)</label><input type="hidden" name="frame_present" value="1">
<div class="cv-review" style="margin:10px 0">{icon("shield", 16)}<span>Common sizes for QUANTITY only. DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.</span></div>{frame}</section></div>
<div class="cv-stickybar"><span>One combined BOQ for all floors will be saved as a draft.</span><button class="cv-btn">{icon("calc", 17)} Calculate combined estimate</button></div></form>''')

    def _roles_from(qp):
        return {k[5:]: str(v) for k, v in qp.items() if k.startswith('role_')}

    @app.get('/projects/{pid}/multi/review')
    def multi_review(request: Request, pid: str):
        p = owned_project(request, pid)
        sheets = load_sheets(pid, parse_ids(request.query_params.get('ids')), _roles_from(request.query_params))
        bad = [t for l, t in compare(sheets) if l == 'bad' and 'could not be read' not in t]
        if bad:
            return RedirectResponse(f'/projects/{pid}/multi/analyse?' + qs(sheets), 303)
        return review_html(request, p, sheets, floor_plans(p, sheets))

    @app.post('/projects/{pid}/multi/estimate')
    async def multi_estimate(request: Request, pid: str):
        u = require(request)
        p = owned_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        fd = {k: form.get(k) for k in form.keys()}
        sheets = load_sheets(pid, parse_ids(fd.get('ids')), _roles_from(fd))
        if any(l == 'bad' and 'could not be read' not in t for l, t in compare(sheets)):
            return RedirectResponse(f'/projects/{pid}/multi/analyse?' + qs(sheets), 303)
        plans = floor_plans(p, sheets)
        if 'frame_present' in fd and 'frame' not in fd:
            fd['frame'] = 'no'
        try:
            opts = se.parse_options(fd)
            floors = []
            for i, (s, sch, inp) in enumerate(plans):
                sub = {key: fd.get(f'f{i}_{key}', '') for key, *_ in se.FIELDS if key != 'floors'}
                if i == 0:
                    sub.update({key: fd.get(key, '') for key in se.FIELD if se.FIELD[key][4] == 'frame'})
                else:   # frame values on upper floors are not used
                    sub.update({key: '' for key in se.FIELD if se.FIELD[key][4] == 'frame'})
                floors.append((FLOOR_SHORT[s['role']], se.parse_form(sub, inp), sch))
            result = combined_estimate(floors, opts, takeoff)
        except ValueError as ex:
            return review_html(request, p, sheets, plans, error=str(ex))
        gf = plans[0][0]
        merged = {'rooms': [dict(r, name=f'{FLOOR_SHORT[s["role"]]} {r.get("name", "")}') for s, sch, _ in plans for r in (sch.get('rooms') or [])],
                  'openings': [dict(o, label=f'{FLOOR_SHORT[s["role"]]} {o.get("label", "")}') for s, sch, _ in plans for o in (sch.get('openings') or [])],
                  'warnings': [w for s, sch, _ in plans for w in (sch.get('warnings') or []) if w]}
        merged['warnings'] = list(OrderedDict.fromkeys(merged['warnings']))
        import preview_v370
        payload = se.build_payload(p, gf['row'], floors[0][1], opts, result, merged)
        payload.update(source='multi_drawing_v360', floors=len(floors),
                       drawing_name='Combined: ' + ' + '.join(f'{FLOOR_SHORT[s["role"]]} {s["name"]}' for s, _, _ in plans)[:240],
                       sheets=[{'id': s['id'], 'name': s['name'], 'role': ROLES[s['role']]} for s in sheets],
                       inputs=[dict(x, label=f'{lab}: {x["label"]}') for lab, inp, _ in floors
                               for x in se.build_payload(p, gf['row'], inp, opts, result, merged)['inputs']])
        with db() as c:
            rates = rates_v260.rates_for_project(c, p, u['id'])
        if any(v > 0 for v in rates.values()):
            rates_v260.apply_rates(payload, rates, payload['builtup_sqft'])
        if not preview_v370.confirmed(form):     # v3.7.0: preview first
            return preview_v370.gate(request, form, layout, csrf(request), f'Combined estimate – {len(floors)} floor(s)',
                                     preview_v370.boq_summary_html(payload, esc), f'/projects/{pid}/multi/estimate', esc, 'Save estimate')
        with db() as c:
            bid = str(uuid.uuid4())
            c.execute('INSERT INTO civora_boq_reports(id,project_id,drawing_id,payload,created) VALUES(?,?,?,?,?)',
                      (bid, pid, gf['fid'], json.dumps(payload, ensure_ascii=False), int(time.time())))
        try:
            import team_v270
            with db() as c:
                team_v270.log(c, pid, u['id'], f'Combined estimate from {len(floors)} floor plan(s)')
        except Exception:
            pass
        return RedirectResponse(f'/projects/{pid}/workflow?estimate={bid}', 303)
