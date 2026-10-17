"""Civora AI v2.5.0 - Project Workflow page (the 6-card project view from the mockup).

Reads existing data only (no new tables, nothing is written):
  uploads, material_takeoffs, civora_boq_reports, civora_structural_v210, civora_bbs_v210,
  civora_rates_v210, civora_design_intake_v220.
Routes:
  GET /projects/{pid}/workflow                 six-card workflow page
  GET /projects/{pid}/workflow/download-all    ZIP of every available report
"""
import csv
import io
import json
import math
import time
import zipfile
from collections import Counter, OrderedDict

import ui_shell
from ui_shell import esc, icon, inr_short, STEPS

SQFT_PER_M2 = 10.7639


def _has_table(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _rows(c, table, sql, args):
    return c.execute(sql, args).fetchall() if _has_table(c, table) else []


def _f(v):
    try:
        v = float(v or 0)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ data
def project_status(c, pid):
    """Everything the workflow needs, read from existing tables. `c` is an open sqlite3 connection."""
    st = {'pid': pid}
    st['uploads'] = _rows(c, 'uploads', 'SELECT * FROM uploads WHERE project_id=? ORDER BY created DESC', (pid,))
    st['takeoffs'] = _rows(c, 'material_takeoffs', 'SELECT * FROM material_takeoffs WHERE project_id=? ORDER BY created DESC', (pid,))
    st['measurements'] = len(_rows(c, 'material_estimates', 'SELECT id FROM material_estimates WHERE project_id=?', (pid,)))
    st['drawing_measurements'] = len(_rows(c, 'drawing_measurements', 'SELECT id FROM drawing_measurements WHERE project_id=?', (pid,)))
    boqs = _rows(c, 'civora_boq_reports', 'SELECT * FROM civora_boq_reports WHERE project_id=? ORDER BY created DESC', (pid,))
    try:                                   # v3.9.0: bring estimates saved before the complete Rate Master up to date (once)
        import rates_v260
        p = c.execute('SELECT * FROM projects WHERE id=?', (pid,)).fetchone()
        if p and rates_v260.upgrade_saved(c, p, boqs):
            boqs = _rows(c, 'civora_boq_reports', 'SELECT * FROM civora_boq_reports WHERE project_id=? ORDER BY created DESC', (pid,))
    except Exception:
        pass
    st['boq_count'] = len(boqs)
    st['boq'] = None
    if boqs:
        b = boqs[0]
        try:
            st['boq'] = {'id': b['id'], 'drawing_id': b['drawing_id'], 'data': json.loads(b['payload']), 'created': b['created']}
        except (TypeError, ValueError):
            st['boq'] = None
    items = _rows(c, 'civora_structural_v210', 'SELECT * FROM civora_structural_v210 WHERE project_id=? ORDER BY created', (pid,))
    bars = _rows(c, 'civora_bbs_v210', 'SELECT * FROM civora_bbs_v210 WHERE project_id=? ORDER BY created', (pid,))
    rates = _rows(c, 'civora_rates_v210', 'SELECT * FROM civora_rates_v210 WHERE project_id=?', (pid,))
    rates = dict(rates[0]) if rates else {}
    st['structural_items'] = []
    tot = {'rcc_m3': 0.0, 'rcc_order_m3': 0.0, 'pcc_m3': 0.0, 'excavation_m3': 0.0, 'backfill_m3': 0.0,
           'formwork_m2': 0.0, 'steel_kg': 0.0}
    for it in items:
        try:
            q = json.loads(it['payload'])['result']
        except (TypeError, ValueError, KeyError):
            continue
        st['structural_items'].append({'kind': it['kind'], 'reference': it['reference'], 'net_m3': _f(q.get('net_m3'))})
        k = it['kind']
        if k in ('excavation', 'backfill', 'pcc'):
            tot[k + '_m3'] += _f(q.get('net_m3'))
        else:
            tot['rcc_m3'] += _f(q.get('net_m3'))
            tot['rcc_order_m3'] += _f(q.get('order_m3'))
        tot['formwork_m2'] += _f(q.get('formwork_m2'))
    for b in bars:
        try:
            tot['steel_kg'] += _f(json.loads(b['payload'])['result']['steel_kg'])
        except (TypeError, ValueError, KeyError):
            pass
    st['structural_totals'] = tot
    st['bar_count'] = len(bars)
    st['structural_amount'] = (tot['rcc_order_m3'] * _f(rates.get('concrete_rate')) + tot['pcc_m3'] * _f(rates.get('pcc_rate'))
                               + tot['excavation_m3'] * _f(rates.get('excavation_rate')) + tot['backfill_m3'] * _f(rates.get('backfill_rate'))
                               + tot['formwork_m2'] * _f(rates.get('formwork_rate')) + tot['steel_kg'] * _f(rates.get('steel_rate')))
    st['legacy_structural'] = len(_rows(c, 'civora_structural_v200', 'SELECT id FROM civora_structural_v200 WHERE project_id=?', (pid,)))
    st['design_intake'] = _rows(c, 'civora_design_intake_v220',
                                'SELECT element_type,element_mark,status FROM civora_design_intake_v220 WHERE project_id=? ORDER BY updated_at DESC', (pid,))
    # duplicate structural marks (e.g. Slab F1 and Raft F1)
    marks = Counter(i['reference'].strip().upper() for i in st['structural_items'])
    st['duplicate_marks'] = sorted(OrderedDict.fromkeys(
        f"{m} ({', '.join(sorted({i['kind'] for i in st['structural_items'] if i['reference'].strip().upper() == m}))})"
        for m, n in marks.items() if n > 1))
    st['boq_frame'] = boq_frame(st['boq']['data']) if st.get('boq') else {}
    st['cost'] = cost_breakdown(st)
    import team_v270
    st['signoff'] = team_v270.latest_signoff(c, pid) if _has_table(c, 'civora_signoff_v270') else None
    st['team'] = (_rows(c, 'civora_members_v270', 'SELECT u.name, m.role FROM civora_members_v270 m JOIN users u ON u.id=m.user_id '
                        'WHERE m.project_id=? ORDER BY m.added_at', (pid,)))
    st['done'] = stages_done(st)
    return st


def boq_frame(data):
    """Preliminary RCC frame summary from a Smart Estimate BOQ (v2.6)."""
    if (data or {}).get('source') not in ('smart_estimate_v260', 'multi_drawing_v360'):
        return {}
    b = {x.get('measurement'): _f(x.get('quantity')) for x in data.get('breakdown', [])}
    if not b.get('Columns (preliminary count)'):
        return {}
    steel = sum(_f(i.get('quantity')) for r in data.get('rows', []) for i in r.get('items', [])
                if i.get('material') == 'Steel planning allowance (not BBS)')
    rcc = sum(b.get(k, 0) for k in ('RCC footings', 'RCC columns', 'RCC beams (plinth + floors)'))
    return {'columns': int(b['Columns (preliminary count)']), 'rcc_m3': rcc, 'steel_kg': steel,
            'typical': sum(1 for i in data.get('inputs', []) if i.get('source') == 'typical')}


def _priceable(item):
    """False for lines that only restate another line (cement in kg next to cement bags) or carry no cost (water)."""
    name, unit = str(item.get('material', '')), str(item.get('unit', '')).lower()
    return not ((name == 'Cement' and unit == 'kg') or name == 'Mixing water')


def boq_cost(data):
    material = 0.0
    item_labour = 0.0
    rated = unrated = 0
    for row in (data or {}).get('rows', []):
        for item in row.get('items', []):
            q, r = _f(item.get('quantity')), _f(item.get('rate'))
            if str(item.get('rate_key', '')).startswith('lab_'):
                item_labour += q * r                 # v3.9.0: item-wise labour shown as Labour, not Materials
            else:
                material += q * r
            if r > 0:
                rated += 1
            elif q > 0 and _priceable(item):
                unrated += 1        # v3.7.0: alternative lines (cement in kg, mixing water) do not count as missing
    ex = (data or {}).get('cost_extras') or {}
    labour, transport, other = _f(ex.get('labour')) + item_labour, _f(ex.get('transport')), _f(ex.get('other'))
    tax_pct = _f(ex.get('tax_percent'))
    sub = material + labour + transport + other
    return {'material': material, 'labour': labour, 'transport': transport, 'other': other,
            'tax_percent': tax_pct, 'tax': sub * tax_pct / 100, 'rated': rated, 'unrated': unrated}


def cost_breakdown(st):
    bc = boq_cost(st['boq']['data']) if st.get('boq') else boq_cost({})
    segs = [('Materials & services', bc['material'], '#1467ef'), ('Labour', bc['labour'], '#16a34a'),
            ('Transport', bc['transport'], '#f59e0b'), ('Contingency & margin', bc['other'], '#7c3aed'),
            ('Structural works', st.get('structural_amount', 0.0), '#ea580c'),
            (f"Tax ({bc['tax_percent']:g}%)", bc['tax'], '#0ea5e9')]
    total = sum(v for _, v, _ in segs)
    return {'segments': segs, 'total': total, 'rated': bc['rated'], 'unrated': bc['unrated']}


def stages_done(st):
    tot = st['structural_totals']
    has_structural = bool(st['structural_items'] or st['bar_count'] or st['legacy_structural'])
    done = {'setup'}
    if st['uploads'] or st['measurements'] or st['drawing_measurements'] or has_structural:
        done.add('input')
    if st['boq'] or st['takeoffs']:
        done.add('materials')
    if has_structural or st['design_intake'] or st.get('boq_frame'):
        done.add('structure')
    if st['cost']['total'] > 0:
        done.add('cost')
    if 'cost' in done and (st['boq'] or st['structural_items']):
        done.add('reports')
    return done


def material_summary(st, limit=7):
    """[(material, quantity, unit)] from the latest saved BOQ, else from saved takeoffs."""
    agg = OrderedDict()
    source = ''
    if st.get('boq'):
        source = 'Latest saved drawing BOQ'
        for row in st['boq']['data'].get('rows', []):
            for it in row.get('items', []):
                key = (str(it.get('material', '')).strip(), str(it.get('unit', '')).strip())
                agg[key] = agg.get(key, 0.0) + _f(it.get('quantity'))
    elif st.get('takeoffs'):
        source = f"{len(st['takeoffs'])} saved material takeoff(s)"
        for t in st['takeoffs']:
            try:
                res = json.loads(t['result_json'])
            except (TypeError, ValueError):
                continue
            for it in res.get('items', []):
                key = (str(it.get('material', '')).strip(), str(it.get('unit', '')).strip())
                agg[key] = agg.get(key, 0.0) + _f(it.get('quantity'))
    rows = [(m, q, u) for (m, u), q in agg.items() if m and q > 0]
    # v2.6: the materials a buyer cares about most come first
    order = ['Ready-mix concrete (RMC)', 'Steel planning allowance (not BBS)', 'Reinforcement steel', 'Cement', 'Cement 50 kg bags',
             'Bricks', 'AAC blocks', 'Sand', 'M-sand', 'Coarse aggregate', 'Tiles', 'Wall tiles', 'Paint']
    rows.sort(key=lambda r: (order.index(r[0]) if r[0] in order else len(order), 1 if 'kg' == r[2] and r[0] == 'Cement' else 0))
    return rows[:limit], len(rows), source


# ------------------------------------------------------------------ report list
def report_links(pid, st):
    """[(label, sub, type, url-or-None)]"""
    out = []
    if st.get('boq'):
        base = f"/projects/{pid}/drawings/{st['boq']['drawing_id']}/boq/{st['boq']['id']}"
        out += [('Material BOQ', 'Drawing quantities with rates', 'XLSX', base + '/excel'),
                ('Material BOQ', 'Printable summary', 'PDF', base + '/pdf')]
    else:
        out += [('Material BOQ', 'Save a drawing BOQ first', 'XLSX', None)]
    if st['structural_items'] or st['bar_count']:
        s = f'/projects/{pid}/structural/advanced/export'
        out += [('Structural quantities', 'Concrete, steel, formwork, BBS', 'XLSX', s + '.xlsx'),
                ('Structural quantities', 'Printable summary', 'PDF', s + '.pdf'),
                ('Structural review', 'Reconciliation report', 'HTML', f'/projects/{pid}/structural/review/report.html')]
    else:
        out += [('Structural quantities', 'Add elements in Structural Hub', 'XLSX', None)]
    if st['takeoffs']:
        out += [('Material takeoffs', 'All saved takeoffs', 'CSV', f'/projects/{pid}/takeoff/export.csv')]
    return out


TYPE_COLOURS = {'XLSX': ('#dcfce7', '#15803d'), 'PDF': ('#fee2e2', '#b91c1c'), 'HTML': ('#e0f2fe', '#0369a1'),
                'CSV': ('#fef3c7', '#b45309'), 'ZIP': ('#ede9fe', '#6d28d9')}


# ------------------------------------------------------------------ rendering helpers
def _card(num, key, title, body, footer=''):
    _, _, _, _, colour, ic = next(s for s in STEPS if s[0] == key)
    return (f'<section class="cv-card cv-fc" id="{key}"><div class="hd"><span class="n" style="background:{colour}">{num}</span>'
            f'<h3>{esc(title)}</h3><span style="color:{colour}">{icon(ic, 20)}</span></div>{body}'
            f'{"<div class=ft>" + footer + "</div>" if footer else ""}</section>')


def _empty(title, text, href, label):
    return (f'<div class="cv-empty"><b>{esc(title)}</b>{esc(text)}'
            f'<div style="margin-top:10px"><a class="cv-btn sm" href="{esc(href)}">{esc(label)}</a></div></div>')


def massing_svg(area_sqft, floors_hint=1):
    """Isometric concept block sized from built-up area. Purely illustrative."""
    side = max(math.sqrt(max(_f(area_sqft), 1) / SQFT_PER_M2), 1)
    w = 70.0
    d = 70.0
    h = 34.0 * floors_hint
    ox, oy = 150, 150
    cx, cy = math.cos(math.radians(30)), math.sin(math.radians(30))

    def P(x, y, z):
        return f'{ox + (x - y) * cx:.1f},{oy + (x + y) * cy - z:.1f}'
    top = ' '.join(P(*p) for p in ((0, 0, h), (w, 0, h), (w, d, h), (0, d, h)))
    left = ' '.join(P(*p) for p in ((0, d, 0), (w, d, 0), (w, d, h), (0, d, h)))
    right = ' '.join(P(*p) for p in ((w, 0, 0), (w, d, 0), (w, d, h), (w, 0, h)))
    win = ''.join(f'<polygon points="{P(w, y0, 10)} {P(w, y0 + 9, 10)} {P(w, y0 + 9, 24)} {P(w, y0, 24)}" fill="#bfe0ff"/>' for y0 in (10, 30, 50))
    door = f'<polygon points="{P(30, d, 0)} {P(40, d, 0)} {P(40, d, 22)} {P(30, d, 22)}" fill="#7a5a3a"/>'
    return (f'<svg viewBox="60 104 180 146" width="100%" height="100%" role="img" aria-label="Concept block view">'
            f'<polygon points="{top}" fill="#e7eef7" stroke="#8aa4c0"/><polygon points="{left}" fill="#c9d8ea" stroke="#8aa4c0"/>'
            f'<polygon points="{right}" fill="#dbe6f3" stroke="#8aa4c0"/>{win}{door}'
            f'<text x="150" y="242" text-anchor="middle" font-size="9" fill="#64798d">Concept block · ≈{side:.1f} m × {side:.1f} m footprint</text></svg>')


def donut(segments, total):
    if total <= 0:
        return None
    stops, acc = [], 0.0
    for _, v, colour in segments:
        if v <= 0:
            continue
        a0 = acc / total * 360
        acc += v
        stops.append(f'{colour} {a0:.2f}deg {acc / total * 360:.2f}deg')
    legend = ''.join(f'<li><i style="background:{c}"></i>{esc(n)}<span>{inr_short(v)}</span></li>' for n, v, c in segments if v > 0)
    return (f'<div class="cv-donut"><div class="ring" style="background:conic-gradient({", ".join(stops)})"><div class="hole">'
            f'<span><b>{esc(inr_short(total))}</b><br><small>Estimated total</small></span></div></div>'
            f'<ul class="cv-legend">{legend}</ul></div>')


# ------------------------------------------------------------------ the six cards
def workflow_cards(project, st, compact=False, csrf_token='', role='owner'):
    import team_v270
    can_edit = team_v270.allowed(role, 'edit')
    can_design = team_v270.allowed(role, 'design')
    pid = project['id']
    P = f'/projects/{pid}'
    done = st['done']

    # 1. Project input
    area = _f(project['area'])
    b1 = (f'<dl class="cv-kv"><dt>Project type</dt><dd>{esc(project["type"])}</dd><dt>Location</dt><dd>{esc(project["location"])}</dd>'
          f'<dt>Built-up area</dt><dd>{area:,.0f} sq.ft <small style="color:#64798d">({area / SQFT_PER_M2:,.1f} m²)</small></dd>'
          f'<dt>Drawings & files</dt><dd>{len(st["uploads"])}</dd><dt>Created</dt><dd>{time.strftime("%d %b %Y", time.localtime(project["created"]))}</dd></dl>')
    c1 = _card(1, 'setup', 'Project Input', b1,
               f'<a class="cv-btn sm ghost" href="{P}">{icon("folder", 16)}Project details</a>'
               + (f'<a class="cv-btn sm" href="{P}#upload">{icon("upload", 16)}Upload drawing</a>' if can_edit else ''))

    # 2. Drawing view (2D / 3D)
    img = next((u for u in st['uploads'] if str(u['original_name']).lower().rsplit('.', 1)[-1] in ('png', 'jpg', 'jpeg', 'pdf', 'dxf')), None)
    if img:
        v2d = f'<div class="cv-view cv-v2d"><img loading="lazy" src="{P}/drawings/{esc(img["id"])}/media" alt="{esc(img["original_name"])}"></div>'
        cap = f'<p class="sub" style="margin:8px 0 0">{esc(img["original_name"])}</p>'
    else:
        v2d = '<div class="cv-view cv-v2d">' + _empty('No drawing yet', 'Upload a plan (PDF, DXF, PNG or JPG).', f'{P}#upload', 'Upload drawing') + '</div>'
        cap = ''
    v3d = (f'<div class="cv-view cv-v3d">{massing_svg(area)}</div>')
    b2 = (f'<input type="radio" name="cv-v" id="cv-t2" checked><input type="radio" name="cv-v" id="cv-t3">'
          f'<div class="cv-hdr" style="display:flex;margin:-4px 0 10px"><span class="cv-tabs"><label for="cv-t2">2D Plan</label><label for="cv-t3">3D Concept</label></span></div>'
          f'<div class="cv-viewwrap">{v2d}{v3d}</div>{cap}')
    c2 = _card(2, 'input', '2D Plan & 3D View', b2,
               f'<a class="cv-btn sm ghost" href="{P}/drawings">{icon("drawing", 16)}Drawing workspace</a>'
               + (f'<a class="cv-btn sm" href="{P}/smart">{icon("calc", 16)}Smart Estimate</a>' if can_edit else ''))

    # 3. Material estimation
    mats, n_mats, source = material_summary(st)
    if mats:
        b3 = (f'<p class="sub">{esc(source)}'
              + (f' · basis: {esc(st["boq"]["data"].get("measurement_basis_label") or "External face")}' if st.get('boq') else '')
              + '</p><table class="cv-mt"><tr><th>Material</th><th>Quantity</th></tr>'
              + ''.join(f'<tr><td>{esc("Steel (planning)" if m.startswith("Steel planning") else m)}</td><td>{q:,.0f} {esc(u)}</td></tr>' if u in ('nos', 'kg') or 'bag' in u
                      else f'<tr><td>{esc(m)}</td><td>{q:,.2f} {esc(u)}</td></tr>' for m, q, u in mats) + '</table>'
              + (f'<p class="sub" style="margin:8px 0 0">+ {n_mats - len(mats)} more materials in the full BOQ</p>' if n_mats > len(mats) else ''))
    else:
        b3 = _empty('No quantities yet', 'Smart Estimate reads your drawing and calculates every material.', f'{P}/smart', 'Start Smart Estimate')
    boq_url = f"{P}/drawings/{st['boq']['drawing_id']}/boq/{st['boq']['id']}" if st.get('boq') else f'{P}/drawings/boq'
    c3 = _card(3, 'materials', 'Material Estimation', b3,
               (f'<a class="cv-btn sm ghost" href="{P}/smart">{icon("calc", 16)}New estimate</a>' if can_edit else '')
               + f'<a class="cv-btn sm" href="{boq_url}">{icon("report", 16)}Open full BOQ</a>')

    # 4. Structural guidance
    tot = st['structural_totals']
    if st['structural_items'] or st['bar_count'] or st['design_intake']:
        kinds = Counter(i['kind'] for i in st['structural_items'])
        b4 = (f'<dl class="cv-kv"><dt>Elements measured</dt><dd>{len(st["structural_items"])}'
              + (f' <small style="color:#64798d">({", ".join(f"{n} {k}" for k, n in kinds.most_common(4))})</small>' if kinds else '')
              + f'</dd><dt>RCC concrete</dt><dd>{tot["rcc_m3"]:,.2f} m³</dd><dt>Reinforcement (BBS)</dt><dd>{tot["steel_kg"]:,.1f} kg</dd>'
              f'<dt>Formwork</dt><dd>{tot["formwork_m2"]:,.1f} m²</dd><dt>Design inputs recorded</dt><dd>{len(st["design_intake"])}</dd></dl>')
        if st['duplicate_marks']:
            b4 += (f'<div class="cv-review" style="margin-top:10px;background:#fef2f2;border-color:#fecaca;color:#991b1b">{icon("shield", 16)}'
                   f'<span>Same mark used for different elements: {esc("; ".join(st["duplicate_marks"]))}. Give each element a unique mark (e.g. S1 for slab).</span></div>')
    elif st.get('boq_frame'):
        fr = st['boq_frame']
        b4 = (f'<p class="sub">Preliminary frame from Smart Estimate (typical sizes, for quantity only)</p>'
              f'<dl class="cv-kv"><dt>Columns</dt><dd>{fr["columns"]}</dd><dt>RCC – footings, columns, beams</dt><dd>{fr["rcc_m3"]:,.2f} m³</dd>'
              f'<dt>Steel (all RCC, thumb rule)</dt><dd>{fr["steel_kg"]:,.0f} kg</dd></dl>'
              f'<p class="sub" style="margin:8px 0 0">For a real design, enter the engineer\'s element sizes in the Structural Hub.</p>')
    else:
        b4 = _empty('No structural elements yet', 'Run Smart Estimate for a preliminary frame, or add elements in the Structural Hub.', f'{P}/smart', 'Smart Estimate')
    b4 += (f'<div class="cv-review" style="margin-top:10px">{icon("shield", 16)}<span>DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED. '
           f'Civora records quantities and design inputs; it does not certify structural design.</span></div>')
    so = st.get('signoff')
    if so:
        b4 += (f'<div class="cv-signed">{icon("check", 16)}<span><b>Reviewed by {esc(so["who"])} ({esc(team_v270.role_label(so["role"]))})</b> on '
               f'{time.strftime("%d %b %Y", time.localtime(so["at"]))}: “{esc(so["note"])}”. This is the reviewer\'s own record, not a Civora certification.</span></div>')
    if can_design and csrf_token:
        b4 += (f'<details class="cv-signform"><summary><b>{"Sign off again" if so else "Engineer sign-off"}</b> <small>(Owner / Engineer)</small></summary>'
               f'<form method="post" action="{P}/signoff"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">'
               f'<textarea name="note" required minlength="5" maxlength="500" placeholder="What did you check? e.g. Column sizes and footing sizes verified against structural drawing S-02 Rev B"></textarea>'
               f'<label class="checkline"><input type="checkbox" name="confirm" value="yes" required> I reviewed this design myself and take responsibility for this sign-off.</label>'
               f'<button class="cv-btn sm">Sign off</button></form></details>')
    c4 = _card(4, 'structure', 'Structural Guidance', b4,
               f'<a class="cv-btn sm ghost" href="{P}/structural/design">{icon("shield", 16)}Design inputs</a><a class="cv-btn sm" href="{P}/structural/review">{icon("beam", 16)}Review</a>')

    # 5. Cost summary
    cost = st['cost']
    d = donut(cost['segments'], cost['total'])
    if d:
        b5 = d
        if cost['unrated']:
            b5 += f'<p class="sub" style="margin:10px 0 0">{cost["unrated"]} BOQ material line(s) still have no rate — the total is incomplete.</p>'
        sqft = _f((st['boq']['data'] if st.get('boq') else {}).get('builtup_sqft')) or _f(project['area'])
        if sqft > 0:
            b5 += f'<p class="cv-persqft"><b>{esc(inr_short(cost["total"] / sqft))}</b> per sq.ft <small>on {sqft:,.0f} sq.ft built-up</small></p>'
        if st.get('boq') and st['structural_amount'] > 0:
            b5 += '<p class="sub" style="margin:6px 0 0">Drawing BOQ and Structural Hub are priced separately — check that no item (e.g. RCC slab) is counted in both.</p>'
    else:
        b5 = _empty('No prices yet', 'Save your local rates once in the Rate Master — every estimate is then priced automatically.', '/rates', 'Set my rates')
    # v3.6.0: estimate by today's rate per sq.ft (area × rate), next to the BOQ total
    try:
        import sqft_rate_v360
        _sq = _f((st['boq']['data'] if st.get('boq') else {}).get('builtup_sqft')) or _f(project['area'])
        if _sq > 0:
            b5 += sqft_rate_v360.box_html(project['id'], _sq, cost['total'] if d else 0, csrf_token, can_edit, esc)
    except Exception:
        pass
    apply = (f'<form method="post" action="{P}/rates/apply" style="margin:0"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">'
             f'<button class="cv-btn sm">{icon("rupee", 16)}Apply my rates</button></form>') if (st.get('boq') and csrf_token and can_edit) else ''
    c5 = _card(5, 'cost', 'Cost Summary', b5,
               (f'<a class="cv-btn sm ghost" href="/rates">{icon("settings", 16)}Rate Master</a>{apply}'
                + (f'<a class="cv-btn sm ghost" href="{boq_url}">Edit line rates</a>' if st.get('boq') else '')) if can_edit
               else (f'<a class="cv-btn sm ghost" href="{boq_url}">{icon("report", 16)}See every line</a>' if st.get('boq') else ''))

    # 6. Reports
    lis = []
    for label, sub, typ, url in report_links(pid, st):
        bg, fg = TYPE_COLOURS.get(typ, ('#eef2f7', '#475569'))
        act = (f'<a class="dl" href="{esc(url)}" aria-label="Download {esc(label)} {typ}">{icon("download", 18)}</a>' if url
               else '<span class="na">Not ready</span>')
        lis.append(f'<li><span class="ty" style="background:{bg};color:{fg}">{typ}</span><span class="nm">{esc(label)}<small>{esc(sub)}</small></span>{act}</li>')
    any_ready = any(u for *_, u in report_links(pid, st))
    b6 = '<ul class="cv-files">' + ''.join(lis) + '</ul>'
    c6 = _card(6, 'reports', 'Reports', b6,
               (f'<a class="cv-btn sm" href="{P}/workflow/download-all">{icon("download", 16)}Download All (ZIP)</a>' if any_ready
                else '<span class="sub">Reports appear here once you save a BOQ or structural quantities.</span>'))
    return '<div class="cv-flow">' + c1 + c2 + c3 + c4 + c5 + c6 + '</div>'


def workflow_page_html(project, st, csrf_token='', estimate_id='', priced=False, role='owner', admin=False):
    import team_v270
    can_edit = team_v270.allowed(role, 'edit')
    pid = project['id']
    P = f'/projects/{pid}'
    links = {'setup': f'{P}', 'input': f'{P}/smart', 'materials': f'{P}/smart', 'structure': '#structure',
             'cost': '#cost', 'reports': '#reports'}
    nxt = next((s for s in STEPS if s[0] not in st['done']), None)
    if nxt and nxt[0] == 'cost':
        nxt_html = f'<a class="cv-btn" href="/rates">Next: set your rates {icon("arrow", 16)}</a>'
    elif nxt:
        nxt_html = f'<a class="cv-btn" href="{esc(links[nxt[0]])}">Next: {esc(nxt[2])} {icon("arrow", 16)}</a>'
    else:
        nxt_html = f'<a class="cv-btn" href="{P}/workflow/download-all">{icon("download", 16)}Download All</a>'
    if not can_edit:
        nxt_html = f'<a class="cv-btn" href="{P}/workflow/download-all">{icon("download", 16)}Download reports</a>'
    rl = team_v270.display(role, admin)
    people = [(n, r) for n, r in st.get('team') or []]
    stack = ''.join(f'<span class="cv-avatar sm" style="background:{team_v270.ROLES.get(r, rl)[3]}" title="{esc(n)} – {esc(team_v270.role_label(r))}">'
                    f'{esc("".join(w[0] for w in str(n).split()[:2]).upper())}</span>' for n, r in people[:5])
    team_html = (f'<a class="cv-team" href="{P}/team" title="Team">{f"<span class=cv-stack>{stack}</span>" if stack else ""}'
                 f'<span class="cv-btn sm ghost">{icon("users", 15)}Team{f" ({len(people) + 1})" if people else ""}</span></a>')
    nxt_html = f'<div class="cv-team">{team_html}{nxt_html}</div>'
    head = (f'<div class="cv-ph"><div><span class="eyebrow">PROJECT WORKFLOW</span><h1>{esc(project["name"])}</h1>'
            f'<div class="meta"><span>{icon("site", 15)}{esc(project["type"])}</span><span>{icon("pin", 15)}{esc(project["location"])}</span>'
            f'<span>{_f(project["area"]):,.0f} sq.ft</span><span>{len(st["done"])} of 6 steps done</span>'
            f'<span class="cv-chip" style="background:{rl[3]}1a;color:{rl[3]}">You: {esc(rl[0])}</span></div></div>{nxt_html}</div>')
    if not can_edit:
        head += (f'<div class="cv-banner" style="background:#f0f7ff;border-color:#c7dcfb;color:#123a6b">{icon("users", 22)}<div><b>You are viewing as {esc(rl[0])}.</b>'
                 'You can see the estimate, cost and reports and download everything. Only the project team can make changes.</div></div>')
    banner = ''
    boq = st.get('boq')
    if estimate_id and boq and boq['id'] == estimate_id:
        data = boq['data']
        frame_keys = {'columns', 'col_b', 'col_d', 'ftg_l', 'ftg_w', 'ftg_t', 'fdn_depth', 'beam_b', 'beam_d'}
        frame_on = (data.get('options') or {}).get('frame', True)
        typ = [i for i in data.get('inputs', []) if i.get('source') == 'typical' and (frame_on or i.get('key') not in frame_keys)]
        n_rows = len(data.get('rows', []))
        bc = boq_cost(data)
        price = (f'{bc["rated"]} lines priced from your Rate Master.' if bc['rated']
                 else 'No prices yet — set your rates in the Rate Master, then press “Apply my rates”.')
        url = f"{P}/drawings/{boq['drawing_id']}/boq/{boq['id']}"
        banner = (f'<div class="cv-banner{" warn" if typ else ""}">{icon("check", 24)}<div><b>Estimate ready — {n_rows} work items calculated.</b>'
                  + (f'{len(typ)} value(s) were typical assumptions ({esc(", ".join(i["label"] for i in typ[:6]))}{"…" if len(typ) > 6 else ""}). Check them in the full BOQ. '
                     if typ else 'All measurements came from your drawing or your entries. ')
                  + f'{price} <a href="{url}"><b style="display:inline">Open full BOQ →</b></a>'
                  + (('<div style="margin-top:8px">' + __import__('preview_v370').delete_button(f'{P}/data/estimates/{boq["id"]}/delete', csrf_token,
                      'Delete this estimate', 'Delete this saved estimate?', esc, f'{P}/workflow') + '</div>') if (csrf_token and can_edit) else '')
                  + '</div></div>')
    elif priced:
        banner = f'<div class="cv-banner">{icon("check", 22)}<div><b>Your rates were applied to the latest BOQ.</b>Lines without a saved rate stay unpriced.</div></div>'
    return (head + banner + ui_shell.stepper(st['done'], links) + '<div style="height:18px"></div>' + workflow_cards(project, st, csrf_token=csrf_token, role=role)
            + f'<p class="cv-disclaim">{icon("shield", 16)}<span>Quantities and costs are planning estimates from your drawings and inputs. '
              'All structural design must be reviewed and approved by a qualified, licensed engineer.</span></p>')


# ------------------------------------------------------------------ download all
def _safe_name(s):
    return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in str(s))[:60] or 'Project'


def build_zip(project, st, structural_rows=None):
    buf = io.BytesIO()
    name = _safe_name(project['name'])
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        lines = [f'Civora AI project report pack - {project["name"]}',
                 f'Generated: {time.strftime("%Y-%m-%d %H:%M")}', '',
                 f'Type: {project["type"]}', f'Location: {project["location"]}', f'Built-up area: {_f(project["area"]):,.0f} sq.ft', '',
                 'Workflow status:']
        lines += [f'  [{"x" if k in st["done"] else " "}] {n}. {t}' for k, n, t, *_ in STEPS]
        lines += ['', 'Cost summary (INR):']
        lines += [f'  {n:<22} {v:>16,.2f}' for n, v, _ in st['cost']['segments']]
        lines += [f'  {"TOTAL":<22} {st["cost"]["total"]:>16,.2f}', '',
                  'DESIGN INCOMPLETE - ENGINEER REVIEW REQUIRED.',
                  'Quantities and costs are planning estimates. Structural design must be checked and approved',
                  'by a qualified, licensed engineer before construction.']
        z.writestr(f'{name}_Summary.txt', '\r\n'.join(lines))
        if st.get('boq'):
            from boq_export_v171 import excel_bytes, pdf_bytes
            z.writestr(f'{name}_Material_BOQ.xlsx', excel_bytes(st['boq']['data']))
            z.writestr(f'{name}_Material_BOQ.pdf', pdf_bytes(st['boq']['data']))
        if structural_rows:
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(['Element', 'Mark', 'Net volume m3'])
            for r in structural_rows:
                w.writerow([r['kind'], r['reference'], f"{r['net_m3']:.3f}"])
            t = st['structural_totals']
            w.writerow([])
            w.writerow(['Total RCC m3', f"{t['rcc_m3']:.3f}"])
            w.writerow(['Total steel kg', f"{t['steel_kg']:.2f}"])
            w.writerow(['Total formwork m2', f"{t['formwork_m2']:.2f}"])
            z.writestr(f'{name}_Structural_Quantities.csv', out.getvalue())
        if st.get('takeoffs'):
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(['Work', 'Material', 'Quantity', 'Unit'])
            for t in st['takeoffs']:
                try:
                    res = json.loads(t['result_json'])
                except (TypeError, ValueError):
                    continue
                for it in res.get('items', []):
                    w.writerow([res.get('work', t['work_key']), it.get('material', ''), it.get('quantity', ''), it.get('unit', '')])
            z.writestr(f'{name}_Material_Takeoffs.csv', out.getvalue())
    return buf.getvalue()


# ------------------------------------------------------------------ routes
def register_workflow_v250(app, db, owned_project, layout, csrf=None):
    from fastapi import Request
    from fastapi.responses import Response

    @app.get('/projects/{pid}/workflow')
    def project_workflow(request: Request, pid: str):
        p = owned_project(request, pid)
        with db() as c:
            st = project_status(c, pid)
        q = request.query_params
        return layout(request, f'{p["name"]} · Workflow',
                      workflow_page_html(p, st, csrf(request) if csrf else '', q.get('estimate', ''), q.get('priced') == '1',
                                         getattr(request.state, 'cv_role', 'owner'), getattr(request.state, 'cv_admin', False)))

    @app.get('/projects/{pid}/workflow/download-all')
    def project_download_all(request: Request, pid: str):
        p = owned_project(request, pid)
        with db() as c:
            st = project_status(c, pid)
        data = build_zip(p, st, st['structural_items'])
        fname = _safe_name(p['name']) + '_Civora_Reports.zip'
        return Response(data, media_type='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="{fname}"', 'Cache-Control': 'private, no-store'})
