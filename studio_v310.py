"""Civora AI v3.1 - Cost Intelligence Center, Structural Studio and BBS Studio.

  /projects/{pid}/boq        Cost Intelligence Center: unified BOQ by construction stage, sources and formulas,
                             duplicate alerts, cost charts, line rates and charges, structural pricing, revisions
  /projects/{pid}/structure  Structural Studio: element navigator, calculation trace, steel check, add element
  /projects/{pid}/bbs        BBS Studio: searchable bar schedule, shape sketch, order list by diameter, review status

Backend freeze: these pages only READ existing tables. Their forms post to the EXISTING routes
(BOQ rates / costs, structural add / delete, BBS add / delete) with ?return=<this page>; a small
ASGI middleware sends the browser back here after a successful save. No calculation is reimplemented:
structural quantities and bar weights are the values stored by structural_v210.
"""
import json
import time
from collections import OrderedDict
from urllib.parse import quote

import ui_shell
from ui_shell import esc, icon, inr_short
import workflow_v250 as wf

# ------------------------------------------------------------------ return-to middleware
def _safe_return(raw, post_path):
    """Only a same-project page: /projects/<pid>/... where the POST was /projects/<pid>/..."""
    import team_v270
    ret = team_v270.safe_next(raw)
    if not ret or not post_path.startswith('/projects/'):
        return ''
    parts = post_path.split('/')
    if len(parts) < 3:
        return ''
    prefix = '/projects/' + parts[2] + '/'
    return ret if (ret + '/').startswith(prefix) or ret.startswith(prefix) else ''


class ReturnToMiddleware:
    """After a successful (303) POST that carried ?return=<same-project page>, redirect there instead."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or scope.get('method') != 'POST':
            return await self.app(scope, receive, send)
        from urllib.parse import parse_qs
        qs = parse_qs((scope.get('query_string') or b'').decode('latin-1'))
        target = _safe_return((qs.get('return') or [''])[0], scope.get('path', ''))
        if not target:
            return await self.app(scope, receive, send)

        async def _send(msg):
            if msg.get('type') == 'http.response.start' and msg.get('status') == 303:
                headers = [(k, v) for k, v in msg.get('headers', []) if k.lower() != b'location']
                headers.append((b'location', target.encode('latin-1', 'ignore')))
                msg = dict(msg, headers=headers)
            await send(msg)
        await self.app(scope, receive, _send)


def ret(url, back):
    return f'{url}?return={quote(back, safe="")}'


# ------------------------------------------------------------------ shared
STAGES = [('foundation', 'Foundation', '#0d9488'), ('frame', 'Frame & slab', '#2563eb'), ('walls', 'Walls', '#7c3aed'),
          ('finishes', 'Finishes', '#f59e0b'), ('roof', 'Roof', '#0ea5e9'), ('services', 'Doors, windows & services', '#db2777'),
          ('other', 'Other', '#64748b')]
STAGE_NAME = {k: n for k, n, _ in STAGES}


def stage_of(work):
    w = str(work).lower()
    if w.startswith('doors, windows'):
        return 'services'
    if w.startswith('labour'):
        return 'other'
    if any(k in w for k in ('excavation', 'pcc', 'footing', 'backfill', 'plinth', 'foundation')):
        return 'foundation'
    if any(k in w for k in ('column', 'beam', 'rcc slab', 'slab formwork', 'formwork', 'rcc')):
        return 'frame'
    if 'masonry' in w or 'brick' in w or 'block' in w:
        return 'walls'
    if 'waterproof' in w or 'roof' in w:
        return 'roof'
    if any(k in w for k in ('plaster', 'paint', 'tile', 'screed', 'floor')):
        return 'finishes'
    return 'other'


def source_of(work, payload):
    w = str(work).lower()
    if 'preliminary' in w:
        return ('Typical size', 'st-review', 'Preliminary planning size — not from the drawing; engineer to confirm')
    if 'provisional' in w or 'indicative' in w:
        return ('Provisional', 'st-input', 'Worked out from drawing labels with stated assumptions (see notes)')
    if payload.get('source_detail') == 'quick_v280':
        return ('Area only', 'st-input', 'Quick Estimate from built-up area — typical plan shape')
    return ('Measured', 'st-checked', 'From drawing / entered sizes')


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def row_amount(row):
    return sum(_f(i.get('quantity')) * _f(i.get('rate')) for i in row.get('items', []))


def boq_analysis(payload):
    """Stage totals, top materials and unpriced count for one BOQ payload."""
    stages = OrderedDict((k, 0.0) for k, _, _ in STAGES)
    import rates_v260
    mats = OrderedDict()
    unpriced = 0
    labour = 0.0
    for row in payload.get('rows', []):
        amt = row_amount(row)
        for i in row.get('items', []):
            if str(i.get('rate_key', '')).startswith('lab_'):    # v3.9.0: item-wise labour is shown as Labour
                lab = _f(i.get('quantity')) * _f(i.get('rate'))
                labour += lab
                amt -= lab
        stages[stage_of(row.get('work', ''))] += amt
        for i in row.get('items', []):
            if str(i.get('rate_key', '')).startswith('lab_'):
                continue
            a = _f(i.get('quantity')) * _f(i.get('rate'))
            name = 'Steel' if str(i.get('material', '')).startswith(('Steel', 'Reinforcement')) else str(i.get('material', ''))
            mats[name] = mats.get(name, 0.0) + a
            if a == 0 and rates_v260.rate_key_for(i):
                unpriced += 1
    top = sorted(((m, a) for m, a in mats.items() if a > 0), key=lambda x: -x[1])[:7]
    return {'stages': stages, 'top': top, 'unpriced': unpriced, 'material': sum(stages.values())}


def bars_html(pairs, colour_of=None, money=True):
    mx = max([v for _, v in pairs] or [0]) or 1
    out = []
    for label, v in pairs:
        c = colour_of(label) if colour_of else '#2563eb'
        val = inr_short(v) if money else f'{v:,.0f}'
        out.append(f'<div class="cc-bar"><span>{esc(label)}</span><span class="tr"><i style="width:{max(2, round(100 * v / mx))}%;background:{c}"></i></span><b>{esc(val)}</b></div>')
    return '<div class="cc-bars">' + ''.join(out) + '</div>'


def subnav(P, on):
    tabs = [('boq', 'Cost & BOQ', P + '/boq'), ('bbs', 'Bar schedule (BBS)', P + '/bbs'), ('structure', 'Structural Studio', P + '/structure')]
    return '<div class="cc-tabs" role="tablist">' + ''.join(
        f'<a role="tab" aria-selected="{"true" if k == on else "false"}" class="{"on" if k == on else ""}" href="{h}">{esc(t)}</a>' for k, t, h in tabs) + '</div>'


DIS = (f'<p class="cv-disclaim">{icon("shield", 16)}<span>Quantities and costs are planning estimates. Structural quantities are '
       'measured values, not a validated design — DESIGN INCOMPLETE, ENGINEER REVIEW REQUIRED until a licensed engineer approves the design.</span></p>')


# ------------------------------------------------------------------ cost center
def cost_center_html(project, st, boqs, cur, csrf_token, can_edit, rate_form=''):
    pid = project['id']
    P = f'/projects/{pid}'
    head = (f'<div class="cv-ph"><div><span class="eyebrow">BBS &amp; BOQ · COST INTELLIGENCE</span><h1>Cost & BOQ</h1>'
            f'<div class="meta">One place for every quantity, rate and charge in this project</div></div>'
            + (f'<a class="cv-btn" href="{P}/workflow/download-all">{icon("download", 16)} Download all</a>' if (boqs or st['structural_items']) else '') + '</div>'
            + subnav(P, 'boq'))
    if not cur and not st['structural_items']:
        return head + (f'<div class="cv-empty" style="margin-top:16px"><b>No estimate in this project yet</b>Run a Quick Estimate from the area, '
                       f'or Smart Estimate from a drawing — the BOQ appears here with every quantity, rate and cost.'
                       + (f'<div class="actions" style="justify-content:center"><a class="cv-btn" href="{P}/smart">{icon("calc", 16)} Start an estimate</a></div>' if can_edit else '')
                       + '</div>') + DIS
    out = [head]
    data = cur['data'] if cur else {'rows': []}
    an = boq_analysis(data)
    bc = wf.boq_cost(data)
    sub = an['material'] + bc['labour'] + bc['transport'] + bc['other']
    tax = sub * bc['tax_percent'] / 100
    structural = st['structural_amount']
    grand = sub + tax + structural
    sqft = _f(data.get('builtup_sqft')) or _f(project['area'])
    kpi = [('Grand total', inr_short(grand), 'BOQ + charges + GST' + (' + structural' if structural else '')),
           ('Materials', inr_short(an['material']), f'{sum(len(r.get("items", [])) for r in data.get("rows", []))} lines'),
           ('Labour', inr_short(bc['labour']), 'from Rate Master or entered'),
           ('Transport + other', inr_short(bc['transport'] + bc['other']), ''),
           (f'GST {bc["tax_percent"]:g}%', inr_short(tax), 'on materials + charges'),
           ('Per sq.ft', inr_short(grand / sqft) if sqft else '—', f'{sqft:,.0f} sq.ft built-up' if sqft else '')]
    out.append('<div class="cc-kpis">' + ''.join(f'<div class="cc-kpi"><small>{esc(a)}</small><b>{esc(b)}</b><em>{esc(c)}</em></div>' for a, b, c in kpi) + '</div>')
    try:   # v3.6.0: estimate by today's rate per sq.ft
        import sqft_rate_v360
        if sqft > 0:
            out.append(sqft_rate_v360.box_html(project['id'], sqft, grand, csrf_token, can_edit, esc))
    except Exception:
        pass
    # alerts
    alerts = []
    if an['unpriced']:
        alerts.append(('warn', f'{an["unpriced"]} material line(s) have no rate, so the total is incomplete.',
                       ('/rates', 'Set rates in Rate Master') if can_edit else None))
    frame_on = (data.get('options') or {}).get('frame', True)
    frame_keys = {'columns', 'col_b', 'col_d', 'ftg_l', 'ftg_w', 'ftg_t', 'fdn_depth', 'beam_b', 'beam_d'}
    typ = [i for i in data.get('inputs', []) if i.get('source') == 'typical' and (frame_on or i.get('key') not in frame_keys)]
    if typ:
        alerts.append(('info', f'{len(typ)} input(s) were typical assumptions (e.g. {", ".join(i["label"] for i in typ[:3])}). Check them before ordering.', None))
    boq_rcc = {stage_of(r['work']) for r in data.get('rows', []) if 'rcc' in r['work'].lower()}
    hub_kinds = {i['kind'] for i in st['structural_items']}
    dup = []
    if any('slab' in r['work'].lower() and 'rcc' in r['work'].lower() for r in data.get('rows', [])) and 'slab' in hub_kinds:
        dup.append('RCC slab')
    if 'frame' in boq_rcc and hub_kinds & {'column', 'plinth_beam', 'grade_beam', 'roof_beam'} and any('column' in r['work'].lower() or 'beam' in r['work'].lower() for r in data.get('rows', [])):
        dup.append('columns / beams')
    if 'foundation' in boq_rcc and hub_kinds & {'isolated_footing', 'combined_footing', 'raft'} and any('footing' in r['work'].lower() for r in data.get('rows', [])):
        dup.append('footings')
    if dup:
        alerts.append(('err', f'Possible double counting: {", ".join(dup)} appear in BOTH this BOQ and the Structural Studio. Keep them in one place only.', (P + '/structure', 'Open Structural Studio')))
    if st['duplicate_marks']:
        alerts.append(('err', f'Same mark used for different elements: {"; ".join(st["duplicate_marks"])}.', (P + '/structure', 'Fix marks')))
    if alerts:
        cls = {'warn': 'warn', 'info': '', 'err': 'err'}
        out.append('<div class="cc-alerts">' + ''.join(
            f'<div class="cv-banner {cls[k]}">{icon("shield" if k == "err" else "check", 20)}<div><b>{esc(t)}</b>'
            + (f'<a href="{a[0]}">{esc(a[1])} →</a>' if a else '') + '</div></div>' for k, t, a in alerts) + '</div>')
    # charts
    stage_pairs = [(STAGE_NAME[k], v) for k, v in an['stages'].items() if v > 0]
    colours = {n: c for _, n, c in STAGES}
    if stage_pairs:
        out.append(f'''<div class="cv-row" style="margin-top:16px"><section class="cv-card"><h3>{icon("chart", 18)} Material cost by stage</h3>
<p class="sub">What money goes where — and roughly in what order you buy.</p>{bars_html(stage_pairs, lambda n: colours.get(n, "#2563eb"))}</section>
<section class="cv-card"><h3>{icon("brick", 18)} Biggest material costs</h3><p class="sub">Negotiate these first with your dealer.</p>{bars_html(an["top"], lambda n: "#0d9488")}</section></div>''')
    # work-item hierarchy
    if cur:
        fid, bid = cur['drawing_id'], cur['id']
        back = f'{P}/boq?rev={bid}#lines'
        groups = OrderedDict((k, []) for k, _, _ in STAGES)
        for ri, row in enumerate(data.get('rows', [])):
            groups[stage_of(row.get('work', ''))].append((ri, row))
        body = ''
        for key, rows in groups.items():
            if not rows:
                continue
            stotal = sum(row_amount(r) for _, r in rows)
            items_html = ''
            for ri, row in rows:
                lab, scls, stip = source_of(row.get('work', ''), data)
                if row.get('civora_auto_v390'):
                    lab, scls, stip = 'Rate Master', 'st-checked', 'Quantities worked out from the estimate; rates from your Rate Master (editable here)'
                elif row.get('custom'):
                    lab, scls, stip = 'Added by hand', 'st-checked', 'Item added by hand'
                lines = ''
                for mi, it in enumerate(row.get('items', [])):
                    q, r = _f(it.get('quantity')), _f(it.get('rate'))
                    qtxt = f'{q:,.0f}' if str(it.get('unit', '')) in ('nos',) or 'bag' in str(it.get('unit', '')) else f'{q:,.2f}'
                    mark = ' <em class="cc-hand" title="Edited by hand – kept when rates are re-applied" style="font-style:normal;font-size:11px;color:#b45309">✎ edited</em>' if (it.get('manual_rate') or it.get('manual_qty')) else ''
                    rate_cell = (f'<input type="number" name="rate_{ri}_{mi}" min="0" max="100000000" step="any" value="{r:.2f}" aria-label="Rate for {esc(it.get("material", ""))}">'
                                 if can_edit else f'{r:,.2f}')
                    qty_cell = (f'<input type="number" name="qty_{ri}_{mi}" min="0" step="any" value="{("%.3f" % q).rstrip("0").rstrip(".")}" style="width:96px;text-align:right" aria-label="Quantity for {esc(it.get("material", ""))}"> {esc(it.get("unit", ""))}'
                                if can_edit else f'{qtxt} {esc(it.get("unit", ""))}')
                    del_cell = (f'<td style="text-align:center"><label title="Remove this line"><input type="checkbox" name="del_{ri}_{mi}" value="1" style="width:auto"></label></td>' if can_edit else '')
                    lines += (f'<tr><td>{esc(it.get("material", ""))}{mark}<small class="cc-basis">{esc(it.get("basis", ""))}</small></td>'
                              f'<td style="text-align:right;white-space:nowrap">{qty_cell}</td><td class="cc-rate">{rate_cell}</td>'
                              f'<td style="text-align:right;white-space:nowrap">{"₹ " + format(q * r, ",.0f") if r else "<span class=cc-np>not priced</span>"}</td>{del_cell}</tr>')
                items_html += (f'<details class="cc-item"><summary><span class="nm">{esc(row.get("work", ""))}</span>'
                               f'<span class="cv-status {scls}" title="{esc(stip)}">{esc(lab)}</span><b>{inr_short(row_amount(row))}</b></summary>'
                               f'<table class="cv-mt cc-lines"><tr><th>Item · how it was worked out</th><th>Quantity</th><th>Rate ₹</th><th>Amount</th>{"<th>Remove</th>" if can_edit else ""}</tr>{lines}</table></details>')
            body += (f'<section class="cc-stage"><div class="cc-sh"><i style="background:{colours[STAGE_NAME[key]]}"></i><b>{esc(STAGE_NAME[key])}</b>'
                     f'<span class="sub">{len(rows)} work item(s)</span><b class="tot">{inr_short(stotal)}</b></div>{items_html}</section>')
        save = (f'<div class="cv-stickybar"><span>Change any quantity or rate, tick Remove to drop a line, then save. Your edits stay when rates are re-applied.</span><button class="cv-btn">Save changes</button></div>' if can_edit else '')
        form_open = (f'<form method="post" action="{ret(f"{P}/drawings/{fid}/boq/{bid}/rates", back)}"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">' if can_edit else '<div>')
        form_close = '</form>' if can_edit else '</div>'
        basis = esc(data.get('measurement_basis_label') or 'External face')
        out.append(f'''<section class="cv-card" id="lines" style="margin-top:16px"><div class="cv-sec" style="margin:0 0 6px"><h2>{icon("layers", 18)} Work items by stage</h2>
<span class="sub">{esc(data.get("drawing_name", ""))} · brickwork measured on {basis} · click a work item to see its materials</span></div>
{form_open}{body}{save}{form_close}</section>''')
        if can_edit:   # v3.9.0: add any item by hand + re-price with the Rate Master
            groups_opts = ''.join(f'<option>{esc(r.get("work", ""))}</option>' for r in data.get('rows', []) if r.get('custom'))
            out.append(f'''<div class="cv-row" style="margin-top:16px"><section class="cv-card"><h3>{icon("plus", 18)} Add an item by hand</h3>
<p class="sub">Anything not in the estimate – compound wall, gate, borewell, false ceiling, modular kitchen, solar, approval fees …</p>
<form method="post" action="{ret(f"{P}/drawings/{fid}/boq/{bid}/addline", back)}" style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:8px;align-items:end">
<input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
<label style="grid-column:1/-1">Group<input name="group" list="cc-groups" placeholder="Extra items (added by hand)" maxlength="80"><datalist id="cc-groups">{groups_opts}</datalist></label>
<label>Item<input name="item" required maxlength="120" placeholder="Compound wall"></label><label>Quantity<input name="quantity" type="number" min="0.001" step="any" required></label>
<label>Unit<input name="unit" value="nos" maxlength="20"></label><label>Rate ₹<input name="rate" type="number" min="0" step="any" required></label>
<button class="cv-btn sm" style="grid-column:1/-1;justify-self:start">Add item</button></form></section>
<section class="cv-card"><h3>{icon("rupee", 18)} Re-price with my Rate Master</h3><p class="sub">Uses your saved rates (or market rates) for every line. Lines you edited by hand are kept.</p>
<form method="post" action="{ret(f"{P}/drawings/{fid}/boq/{bid}/reprice", back)}"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
<label class="checkline"><input type="checkbox" name="replace" value="1"> Also replace my hand-edited rates and quantities</label>
<div class="actions"><button class="cv-btn sm">Apply rates now</button><a class="cv-btn sm ghost" href="/rates">Open Rate Master</a></div></form></section></div>''')
        # charges
        ex = data.get('cost_extras') or {}
        if can_edit:
            fields = ''.join(f'<label>{lb}<input type="number" name="{k}" min="0" max="{100 if k == "tax_percent" else 100000000}" step="any" value="{_f(ex.get(k)):g}"></label>'
                             for k, lb in (('labour', 'Labour ₹'), ('transport', 'Transport ₹'), ('other', esc(ex.get('other_note') or 'Other charges') + ' ₹'), ('tax_percent', 'GST %')))
            out.append(f'''<section class="cv-card" style="margin-top:16px"><h3>{icon("rupee", 18)} Labour, transport, other charges & GST</h3>
<p class="sub">Labour is item-wise inside the estimate (see “Labour – item-wise”). Use the Labour box only for an extra lump sum. A value you type here is kept when rates are re-applied{" (edited: " + ", ".join(ex.get("manual") or []) + ")" if ex.get("manual") else ""}.</p>
<form method="post" action="{ret(f"{P}/drawings/{fid}/boq/{bid}/costs", f"{P}/boq?rev={bid}")}" class="cc-charges"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">{fields}<button class="cv-btn sm">Save charges</button></form></section>''')
    # structural
    if st['structural_items'] or st['bar_count']:
        t = st['structural_totals']
        out.append(f'''<section class="cv-card" style="margin-top:16px"><div class="cv-sec" style="margin:0 0 6px"><h2>{icon("beam", 18)} Structural Studio quantities</h2><a href="{P}/structure">Open Structural Studio →</a></div>
<dl class="cv-kv"><dt>RCC (incl. wastage)</dt><dd>{t["rcc_order_m3"]:,.2f} m³</dd><dt>PCC</dt><dd>{t["pcc_m3"]:,.2f} m³</dd><dt>Excavation / backfill</dt><dd>{t["excavation_m3"]:,.2f} / {t["backfill_m3"]:,.2f} m³</dd>
<dt>Formwork</dt><dd>{t["formwork_m2"]:,.1f} m²</dd><dt>Steel (BBS)</dt><dd>{t["steel_kg"]:,.0f} kg</dd><dt>Priced with structural rates</dt><dd>{inr_short(structural) if structural else "not priced"}</dd></dl>
<p class="hint">Priced separately with the structural rates (concrete, steel, formwork …) and added to the grand total above.
{f'<a href="{P}/structural/advanced">Set structural rates →</a>' if can_edit and not structural and not rate_form else ''}</p>{rate_form}</section>''')
    # revisions
    if boqs:
        rows = ''
        prev = None
        for i, b in enumerate(reversed(boqs)):
            d = b['data']
            a = boq_analysis(d)
            c = wf.boq_cost(d)
            s = a['material'] + c['labour'] + c['transport'] + c['other']
            total = s * (1 + c['tax_percent'] / 100)
            delta = '' if prev is None else (f'<span style="color:{"#b91c1c" if total > prev else "#15803d"}">{"+" if total >= prev else "−"}{inr_short(abs(total - prev))}</span>')
            prev = total
            src = {'smart_estimate_v260': 'Smart Estimate', 'multi_drawing_v360': 'Multi-drawing estimate'}.get(d.get('source'), 'Drawing BOQ')
            if d.get('source_detail') == 'quick_v280':
                src = 'Quick Estimate'
            is_cur = cur and b['id'] == cur['id']
            rows = (f'<tr{" class=cc-cur" if is_cur else ""}><td>Rev {i + 1}{" · showing" if is_cur else ""}</td><td>{time.strftime("%d %b %Y %H:%M", time.localtime(b["created"]))}</td>'
                    f'<td>{esc(src)}</td><td>{len(d.get("rows", []))}</td><td style="text-align:right">{inr_short(total) if total else "—"}</td><td>{delta}</td>'
                    f'<td><a href="{P}/boq?rev={esc(b["id"])}">View</a> · <a href="{P}/drawings/{esc(b["drawing_id"])}/boq/{esc(b["id"])}/excel">Excel</a> · '
                    f'<a href="{P}/drawings/{esc(b["drawing_id"])}/boq/{esc(b["id"])}/pdf">PDF</a>'
                    + (f'<form method="post" action="{ret(f"{P}/data/estimates/{b["id"]}/delete", P + "/boq")}" class="cv-inline" '
                       f'onsubmit="return confirm(&quot;Delete Rev {i + 1}? This cannot be undone.&quot;)"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">'
                       f'<button class="cv-btn sm ghost dt-danger-t" aria-label="Delete Rev {i + 1}">Delete</button></form>' if can_edit else '')
                    + '</td></tr>') + rows
        out.append(f'''<section class="cv-card" style="margin-top:16px"><h3>{icon("report", 18)} Revisions</h3><p class="sub">Every saved estimate is kept. Compare totals; the change is against the previous revision.</p>
<div class="scroll"><table class="cv-mt"><tr><th>Revision</th><th>Saved</th><th>Source</th><th>Work items</th><th>Total (excl. structural)</th><th>Change</th><th></th></tr>{rows}</table></div></section>''')
    out.append(DIS)
    return ''.join(out)


# ------------------------------------------------------------------ structural studio
GROUPS = [('Foundation', ('excavation', 'pcc', 'isolated_footing', 'combined_footing', 'strip_footing', 'stepped_footing', 'raft',
                          'pile', 'pile_cap', 'pedestal', 'backfill', 'grade_slab')),
          ('Columns & walls', ('column', 'circular_column', 'shear_wall', 'rcc_wall', 'retaining_wall', 'lift_wall', 'compound_wall_beam', 'fins')),
          ('Beams', ('plinth_beam', 'grade_beam', 'tie_beam', 'roof_beam', 'secondary_beam', 'ring_beam', 'cantilever_beam', 'lintel')),
          ('Slabs', ('slab', 'flat_slab', 'sunken_slab', 'cantilever_slab', 'porch_slab', 'loft', 'sunshade')),
          ('Stairs, tanks & others', ('staircase', 'waist_slab', 'stair_landing', 'stair_steps', 'ramp', 'parapet', 'coping',
                                      'overhead_tank', 'sump', 'septic_tank', 'lift_pit', 'manhole', 'other_rcc'))]


def _load_structural(c, pid):
    import structural_v210 as sv
    items = []
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_structural_v210'").fetchone():
        for r in c.execute('SELECT * FROM civora_structural_v210 WHERE project_id=? ORDER BY created, id', (pid,)).fetchall():
            try:
                p = json.loads(r['payload'])
            except (TypeError, ValueError):
                continue
            items.append({'id': r['id'], 'kind': r['kind'], 'name': sv.ELEMENTS.get(r['kind'], (r['kind'],))[0], 'mark': r['reference'],
                          'drawing_ref': r['drawing_ref'], 'created': r['created'], 'p': p, 'q': p.get('result', {})})
    bars = []
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_bbs_v210'").fetchone():
        for r in c.execute('SELECT * FROM civora_bbs_v210 WHERE project_id=? ORDER BY created, id', (pid,)).fetchall():
            try:
                p = json.loads(r['payload'])
            except (TypeError, ValueError):
                continue
            bars.append({'id': r['id'], 'mark': r['reference'], 'created': r['created'], 'p': p, 'q': p.get('result', {})})
    return items, bars


def bars_for(mark, bars):
    m = str(mark).strip().upper()
    return [b for b in bars if str(b['mark']).strip().upper() == m or str(b['mark']).strip().upper().startswith(m + '-')]


def structure_html(project, st, items, bars, intake, signoff, sel_id, csrf_token, can_edit, can_design, rate_form=''):
    import structural_v210 as sv
    pid = project['id']
    P = f'/projects/{pid}'
    back = f'{P}/structure'
    head = (f'<div class="cv-ph"><div><span class="eyebrow">STRUCTURAL STUDIO · கட்டமைப்பு</span><h1>Structural Studio</h1>'
            f'<div class="meta">Measured structural quantities, bars and design inputs — element by element</div></div>'
            + (f'<a class="cv-btn ghost" href="{P}/structural/design">{icon("shield", 16)} Design inputs</a>' if can_design else '') + '</div>' + subnav(P, 'structure'))
    nav = ''
    for gname, kinds in GROUPS:
        els = [i for i in items if i['kind'] in kinds]
        if not els:
            continue
        import data_v340
        links = ''.join(f'<div class="dt-row"><a class="{"on" if i["id"] == sel_id else ""}" href="{P}/structure?el={esc(i["id"])}"><b>{esc(i["mark"])}</b>'
                        f'<span>{esc(i["name"])}</span><em>{_f(i["q"].get("net_m3")):,.2f} m³</em></a>'
                        + (data_v340.x_form(ret(f'{P}/structural/advanced/{i["id"]}/delete', back), csrf_token, f'Delete {i["mark"]}?', f'Delete {i["mark"]}') if can_edit else '')
                        + '</div>' for i in els)
        nav += f'<div class="ss-group"><h4>{esc(gname)} <small>({len(els)})</small></h4>{links}</div>'
    if st.get('boq_frame'):
        fr = st['boq_frame']
        nav += (f'<div class="ss-group"><h4>Preliminary frame <small>(typical)</small></h4><a href="{P}/boq#lines"><b>Smart Estimate</b>'
                f'<span>{fr["columns"]} columns · typical sizes</span><em>{fr["rcc_m3"]:,.1f} m³</em></a></div>')
    left = (f'<aside class="ds-panel ss-nav"><h3>Elements</h3><a class="ss-all{" on" if not sel_id else ""}" href="{P}/structure">Overview</a>'
            f'{nav or "<p class=sub>No elements yet. Add the first one on the right.</p>"}</aside>')
    sel = next((i for i in items if i['id'] == sel_id), None)
    tot = st['structural_totals']
    if sel is None:
        counts = ''.join(f'<li><span class="nm">{esc(g)}</span><b>{sum(1 for i in items if i["kind"] in ks)}</b></li>' for g, ks in GROUPS)
        so = (f'<div class="cv-signed">{icon("check", 16)}<span><b>Reviewed by {esc(signoff["who"])}</b> on {time.strftime("%d %b %Y", time.localtime(signoff["at"]))}: “{esc(signoff["note"])}”</span></div>'
              if signoff else '<div class="cv-review">' + icon('shield', 16) + '<span>No engineer sign-off yet. DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.</span></div>')
        centre = f'''<section class="cv-card"><h3>{icon("beam", 18)} Project structure overview</h3>
<div class="cc-kpis" style="grid-template-columns:repeat(3,minmax(0,1fr));margin:6px 0 12px">
<div class="cc-kpi"><small>RCC net</small><b>{tot["rcc_m3"]:,.2f} m³</b><em>{tot["rcc_order_m3"]:,.2f} m³ to order</em></div>
<div class="cc-kpi"><small>Steel (BBS)</small><b>{tot["steel_kg"]:,.0f} kg</b><em>{(tot["steel_kg"] / tot["rcc_m3"]) if tot["rcc_m3"] else 0:,.0f} kg per m³ RCC</em></div>
<div class="cc-kpi"><small>Formwork</small><b>{tot["formwork_m2"]:,.1f} m²</b><em>verified areas only</em></div></div>
<ul class="cv-files ss-counts">{counts}</ul>{so}
<p class="hint">Pick an element on the left to see its full calculation, its bars, its steel check and its reinforcement drawing.</p>
<div class="actions"><a class="cv-btn sm" href="{P}/structure/details">{icon("drawing", 15)} Site detail sheet (all elements)</a></div>{rate_form}</section>'''
    else:
        p, q = sel['p'], sel['q']
        n, L, W, D = p.get('count', 1), _f(p.get('length_m')), _f(p.get('width_m')), _f(p.get('depth_m'))
        gross, ded, net, order = _f(q.get('gross_m3')), _f(q.get('deduction_m3')), _f(q.get('net_m3')), _f(q.get('order_m3'))
        mybars = bars_for(sel['mark'], bars)
        steel = sum(_f(b['q'].get('steel_kg')) for b in mybars)
        ratio = steel / net if net else 0
        typical = {'column': (120, 250), 'isolated_footing': (50, 110), 'combined_footing': (50, 110), 'raft': (60, 130), 'slab': (60, 110),
                   'plinth_beam': (90, 180), 'grade_beam': (90, 180), 'roof_beam': (100, 200), 'lintel': (50, 110)}.get(sel['kind'])
        if not mybars:
            steel_note = f'<p class="sub">No bars linked. Add bars with mark “{esc(sel["mark"])}” or “{esc(sel["mark"])}-MAIN” in the BBS Studio.</p>'
        elif typical and not typical[0] <= ratio <= typical[1]:
            steel_note = (f'<div class="cv-review">{icon("shield", 16)}<span>{ratio:,.0f} kg/m³ is outside the usual {typical[0]}–{typical[1]} kg/m³ range for this element. '
                          'Check the bar schedule — this is a planning check, not a design rule.</span></div>')
        else:
            steel_note = f'<p class="sub">{ratio:,.0f} kg of steel per m³ of concrete{f" — within the usual {typical[0]}–{typical[1]} kg/m³ planning range" if typical else ""}.</p>'
        bar_rows = ''.join(f'<tr><td><a href="{P}/bbs?bar={esc(b["id"])}#bar">{esc(b["mark"])}</a></td><td>{b["p"].get("diameter_mm")} mm</td><td>{b["p"].get("count")}</td>'
                           f'<td style="text-align:right">{_f(b["q"].get("steel_kg")):,.1f} kg</td></tr>' for b in mybars)
        di = [r for r in intake if str(r['element_mark']).strip().upper() == str(sel['mark']).strip().upper()]
        import detailing_v320 as rd
        block = rd.detail_block(sel, bars)
        detail_html = (f'<h3 style="margin-top:16px">{icon("drawing", 18)} Reinforcement detail · கம்பி அமைப்பு</h3>{block}'
                       f'<p><a href="{P}/structure/details">Open the site detail sheet for all elements →</a></p>') if block else ''
        delete = (f'<form method="post" action="{ret(f"{P}/structural/advanced/{sel["id"]}/delete", back)}" class="cv-inline" onsubmit="return confirm(&quot;Delete {esc(sel["mark"])}?&quot;)">'
                  f'<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><button class="cv-btn sm ghost" style="color:#b91c1c">Delete</button></form>') if can_edit else ''
        centre = f'''<section class="cv-card"><div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:flex-start">
<div><small class="sub" style="margin:0">{esc(sel["name"])}</small><h2 style="margin:2px 0">{esc(sel["mark"])}</h2>
<span class="sub">{esc(sel["drawing_ref"]) or "No drawing reference"} · saved {time.strftime("%d %b %Y", time.localtime(sel["created"]))}</span></div>
<div style="display:flex;gap:6px;flex-wrap:wrap"><span class="cv-status st-checked">Measured quantity</span>
<span class="cv-status {"st-progress" if di else "st-draft"}">{"Design inputs recorded" if di else "No design inputs"}</span>
<span class="cv-status {"st-checked" if signoff and signoff["at"] >= sel["created"] else "st-review"}">{"Covered by sign-off" if signoff and signoff["at"] >= sel["created"] else "Needs engineer review"}</span></div></div>
<h3 style="margin-top:14px">How the quantity was worked out</h3>
<ol class="ss-trace"><li>Gross = count × length × width × depth = {n} × {L:g} × {W:g} × {D:g} = <b>{gross:,.3f} m³</b></li>
<li>Net = gross − verified deductions = {gross:,.3f} − {ded:,.3f} = <b>{net:,.3f} m³</b></li>
<li>To order = net × (1 + {_f(p.get("waste_pct")):g}% wastage) = <b>{order:,.3f} m³</b></li>
<li>Formwork (verified, entered) = <b>{_f(q.get("formwork_m2")):,.2f} m²</b></li></ol>
<h3 style="margin-top:14px">Reinforcement</h3>{f'<table class="cv-mt"><tr><th>Bar mark</th><th>Dia</th><th>Nos</th><th>Steel</th></tr>{bar_rows}</table>' if bar_rows else ''}
<p style="margin:8px 0 4px"><b>{steel:,.1f} kg</b> steel linked</p>{steel_note}
{detail_html}<div class="actions">{f'<a class="cv-btn sm ghost" href="{P}/structural/advanced/{esc(sel["id"])}/edit">Edit sizes</a>' if can_edit else ''}{delete}
<a class="cv-btn sm ghost" href="{P}/bbs">Bar schedule</a>{f'<a class="cv-btn sm ghost" href="{P}/structural/design">Design inputs</a>' if can_design else ''}</div></section>'''
    if can_edit:
        opts = ''.join(f'<optgroup label="{esc(g)}">' + ''.join(f'<option value="{k}">{esc(sv.ELEMENTS[k][0])}</option>' for k in ks) + '</optgroup>' for g, ks in GROUPS)
        right = f'''<aside class="ds-panel ss-add"><h3>Add element</h3>
<div class="cv-guide" style="font-size:12.5px">{icon("check", 16)}<div>Take sizes from the structural drawing. Give each element its own mark (F1, C1, B1, S1).<span class="ta">ஒவ்வொரு உறுப்புக்கும் தனி குறியீடு கொடுக்கவும்.</span></div></div>
<form method="post" action="{ret(f"{P}/structural/advanced/add", back)}"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
<label>Element<select name="kind">{opts}</select></label><label>Mark<input name="reference" maxlength="100" required placeholder="F1 / C1 / B1"></label>
<div class="ss-two"><label>Count<input name="count" type="number" min="1" step="1" value="1" required></label><label>Length m<input name="length" type="number" min="0.0001" step="any" required></label></div>
<div class="ss-two"><label>Width m<input name="width" type="number" min="0.0001" step="any" required></label><label>Depth m<input name="depth" type="number" min="0.0001" step="any" required></label></div>
<div class="cv-expert"><label>Drawing / sheet ref<input name="drawing_ref" maxlength="150" placeholder="S-02 Rev B"></label>
<div class="ss-two"><label>Deduction m³<input name="deduction" type="number" min="0" step="any" value="0"></label><label>Wastage %<input name="waste" type="number" min="0" max="30" step="any" value="5"></label></div>
<label>Verified formwork m²<input name="formwork" type="number" min="0" step="any" value="0"></label></div>
<p class="hint" style="font-size:12px;margin:6px 0 0">Round piles / circular columns: enter the diameter as length and width. Stair steps: count = steps, length = tread, width = stair width, depth = riser.</p><button class="cv-btn" style="width:100%;justify-content:center;margin-top:10px">Calculate &amp; preview</button></form>
<p class="hint">Guided mode uses 5% wastage and no deductions; switch to Expert mode in Settings for every field.</p></aside>'''
    else:
        right = ''
    grid = 'ss-g3' if right else 'ss-g2'
    banner = ('<div class="cv-review" style="margin:12px 0">' + icon('shield', 16) + '<span><b>Measured quantity ≠ validated design.</b> '
              'Civora measures concrete and steel from the sizes you enter. A licensed engineer must design and approve the structure.</span></div>')
    return head + banner + f'<div class="ds {grid}">{left}{centre}{right}</div>' + DIS


# ------------------------------------------------------------------ bbs studio
def bar_svg(p):
    """Schematic bar shape from the stored allowances (straight + bends / hooks). Not to scale."""
    hook, bend = _f(p.get('hook')) > 0, _f(p.get('bend')) > 0
    parts = ['<line x1="40" y1="60" x2="260" y2="60" stroke="#0f172a" stroke-width="5" stroke-linecap="round"/>']
    if bend:
        parts.append('<polyline points="40,60 40,20" fill="none" stroke="#0f172a" stroke-width="5" stroke-linecap="round"/>'
                     '<polyline points="260,60 260,20" fill="none" stroke="#0f172a" stroke-width="5" stroke-linecap="round"/>')
    if hook:
        y = 20 if bend else 60
        parts.append(f'<path d="M40 {y} q -18 0 -18 14 q 0 12 14 12" fill="none" stroke="#2563eb" stroke-width="4" stroke-linecap="round"/>'
                     f'<path d="M260 {y} q 18 0 18 14 q 0 12 -14 12" fill="none" stroke="#2563eb" stroke-width="4" stroke-linecap="round"/>')
    label = f'{_f(p.get("length")):g} m straight'
    return (f'<svg viewBox="0 0 300 100" width="100%" role="img" aria-label="Bar shape sketch: {esc(label)}{", with bends" if bend else ""}{", with hooks" if hook else ""}">'
            + ''.join(parts) + f'<text x="150" y="86" text-anchor="middle" font-size="12" fill="#5b6b7f">{esc(label)} · sketch, not to scale</text></svg>')


def bbs_html(project, bars, signoff, sel_id, csrf_token, can_edit):
    import structural_v210 as sv
    pid = project['id']
    P = f'/projects/{pid}'
    back = f'{P}/bbs'
    head = (f'<div class="cv-ph"><div><span class="eyebrow">BBS STUDIO · கம்பி அட்டவணை</span><h1>Bar Bending Schedule</h1>'
            f'<div class="meta">{len(bars)} bar mark(s) · manual entries from the approved structural drawings</div></div>'
            + (f'<a class="cv-btn ghost" href="{P}/structural/advanced/export.xlsx">{icon("download", 16)} Excel</a>' if bars else '') + '</div>' + subnav(P, 'bbs'))
    by_dia = OrderedDict()
    for b in sorted(bars, key=lambda x: int(x['p'].get('diameter_mm') or 0)):
        d = int(b['p'].get('diameter_mm') or 0)
        cur = by_dia.setdefault(d, [0.0, 0.0, 0])
        cur[0] += _f(b['q'].get('steel_kg')); cur[1] += _f(b['q'].get('order_steel_kg')); cur[2] += int(b['p'].get('count') or 0)
    total, order = sum(v[0] for v in by_dia.values()), sum(v[1] for v in by_dia.values())
    out = [head]
    if bars:
        dia_rows = ''.join(f'<tr><td><b>{d} mm</b></td><td>{v[2]:,}</td><td style="text-align:right">{v[0]:,.1f} kg</td><td style="text-align:right"><b>{v[1]:,.1f} kg</b></td>'
                           f'<td style="text-align:right">{v[1] / 1000:,.3f} t</td></tr>' for d, v in by_dia.items())
        out.append(f'''<div class="cv-row" style="margin-top:14px"><section class="cv-card"><h3>{icon("truck", 18)} Order list by diameter</h3>
<p class="sub">Give this to the steel dealer. “To order” includes the wastage % entered for each bar.</p>
<table class="cv-mt"><tr><th>Diameter</th><th>Bars</th><th>Theoretical</th><th>To order</th><th>Tonnes</th></tr>{dia_rows}
<tr><td><b>Total</b></td><td></td><td style="text-align:right">{total:,.1f} kg</td><td style="text-align:right"><b>{order:,.1f} kg</b></td><td style="text-align:right"><b>{order / 1000:,.3f} t</b></td></tr></table></section>
<section class="cv-card"><h3>{icon("chart", 18)} Steel by diameter</h3>{bars_html([(f"{d} mm", v[1]) for d, v in by_dia.items()], lambda n: "#0d9488", money=False)}
<p class="hint">kg to order. Unit weight = d² ÷ 162 kg per metre.</p></section></div>''')
    # table + side panel
    sel = next((b for b in bars if b['id'] == sel_id), None)
    import data_v340
    rows = ''
    for b in bars:
        p, q = b['p'], b['q']
        reviewed = bool(signoff and signoff['at'] >= b['created'])
        rows += (f'<tr data-s="{esc((b["mark"] + " " + str(p.get("diameter_mm"))).lower())}" class="{"cc-cur" if sel and b["id"] == sel["id"] else ""}">'
                 f'<td><a href="{P}/bbs?bar={esc(b["id"])}#bar"><b>{esc(b["mark"])}</b></a></td><td>{p.get("diameter_mm")} mm</td><td>{p.get("count")}</td>'
                 f'<td style="text-align:right">{_f(q.get("cut_length_m")):,.3f} m</td><td style="text-align:right">{_f(q.get("total_length_m")):,.1f} m</td>'
                 f'<td style="text-align:right">{_f(q.get("steel_kg")):,.1f}</td><td style="text-align:right">{_f(q.get("order_steel_kg")):,.1f}</td>'
                 f'<td><span class="cv-status {"st-checked" if reviewed else "st-input"}">{"Reviewed" if reviewed else "Manual entry"}</span></td>'
                 + (f'<td>{data_v340.x_form(ret(f"{P}/structural/advanced/bbs/{b["id"]}/delete", back), csrf_token, f"Delete bar {b["mark"]}?", f"Delete bar {b["mark"]}")}</td>' if can_edit else '')
                 + '</tr>')
    search = ('<div class="pf-bar" style="margin:0 0 10px"><input id="bbs-q" placeholder="Search bar mark or diameter (e.g. C1, 12)" aria-label="Search bars" '
              'oninput="var v=this.value.toLowerCase();document.querySelectorAll(\'#bbs-t tr[data-s]\').forEach(function(r){r.style.display=r.dataset.s.indexOf(v)>-1?\'\':\'none\'})"></div>')
    table = (f'<section class="cv-card" style="margin-top:16px"><h3>{icon("layers", 18)} Bar schedule</h3>{search if bars else ""}'
             + (f'<div class="scroll"><table class="cv-mt" id="bbs-t"><tr><th>Mark</th><th>Dia</th><th>Nos</th><th>Cut length</th><th>Total length</th><th>kg</th><th>kg to order</th><th>Status</th>{"<th></th>" if can_edit else ""}</tr>{rows}</table></div>'
                if bars else '<div class="cv-empty"><b>No bars yet</b>Add the first bar on the right from the approved structural drawing.</div>') + '</section>')
    panel = ''
    if sel:
        p, q = sel['p'], sel['q']
        d = int(p.get('diameter_mm') or 0)
        reviewed = bool(signoff and signoff['at'] >= sel['created'])
        delete = (f'<form method="post" action="{ret(f"{P}/structural/advanced/bbs/{sel["id"]}/delete", back)}" class="cv-inline" onsubmit="return confirm(&quot;Delete bar {esc(sel["mark"])}?&quot;)">'
                  f'<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><button class="cv-btn sm ghost" style="color:#b91c1c">Delete bar</button></form>') if can_edit else ''
        panel = f'''<aside class="ds-panel" id="bar"><h3>Bar {esc(sel["mark"])}</h3>{bar_svg(p)}
<dl class="ds-kv"><dt>Diameter</dt><dd>{d} mm</dd><dt>Number of bars</dt><dd>{p.get("count")}</dd><dt>Straight length</dt><dd>{_f(p.get("length")):g} m</dd>
<dt>Bend deduction</dt><dd>{_f(p.get("bend")):g} m</dd><dt>Hook allowance</dt><dd>{_f(p.get("hook")):g} m</dd><dt>Lap allowance</dt><dd>{_f(p.get("lap")):g} m</dd><dt>Wastage</dt><dd>{_f(p.get("waste")):g} %</dd></dl>
<h3 style="margin-top:12px">Calculation</h3><ol class="ss-trace" style="font-size:13px">
<li>Cut length = straight + hook + lap − bend deductions = <b>{_f(q.get("cut_length_m")):,.3f} m</b></li>
<li>Unit weight = d² ÷ 162 = {d}² ÷ 162 = <b>{_f(q.get("unit_weight_kg_m")):,.3f} kg/m</b></li>
<li>Weight = {p.get("count")} × {_f(q.get("cut_length_m")):,.3f} × {_f(q.get("unit_weight_kg_m")):,.3f} = <b>{_f(q.get("steel_kg")):,.2f} kg</b></li>
<li>To order = weight × (1 + {_f(p.get("waste")):g}%) = <b>{_f(q.get("order_steel_kg")):,.2f} kg</b></li></ol>
<p class="sub">Entered {time.strftime("%d %b %Y", time.localtime(sel["created"]))} · {"covered by engineer sign-off on " + time.strftime("%d %b %Y", time.localtime(signoff["at"])) if reviewed else "not yet reviewed by an engineer"}.
Bends, hooks and laps are taken as entered — Civora does not detail bars to the code.</p><div class="actions">{delete}<a class="cv-btn sm ghost" href="{P}/bbs">Close</a></div></aside>'''
    if can_edit:
        dia_opts = ''.join(f'<option value="{d}"{" selected" if d == 12 else ""}>{d} mm</option>' for d in sv.DIAMETERS)
        add = f'''<aside class="ds-panel"><h3>Add bar</h3><form method="post" action="{ret(f"{P}/structural/advanced/bbs/add", back)}"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
<label>Bar mark<input name="reference" maxlength="100" required placeholder="C1-MAIN"></label>
<div class="ss-two"><label>Diameter<select name="diameter">{dia_opts}</select></label><label>No. of bars<input name="count" type="number" min="1" step="1" required></label></div>
<label>Straight length per bar (m)<input name="length" type="number" min="0.001" step="any" required></label>
<div class="ss-two"><label>Bend deduction m<input name="bend" type="number" min="0" step="any" value="0"></label><label>Hook m<input name="hook" type="number" min="0" step="any" value="0"></label></div>
<div class="ss-two"><label>Lap m<input name="lap" type="number" min="0" step="any" value="0"></label><label>Wastage %<input name="waste" type="number" min="0" max="30" step="any" value="3"></label></div>
<button class="cv-btn" style="width:100%;justify-content:center;margin-top:10px">Calculate &amp; save bar</button></form>
<p class="hint cv-guide-hint">Use the same mark as the element (C1 → C1-MAIN, C1-TIES) so the Structural Studio links the steel to it.</p></aside>'''
    else:
        add = ''
    right = panel + add
    if right:
        out.append(f'<div class="ds bb-g">{table}<div class="ss-side">{panel}{add}</div></div>')
    else:
        out.append(table)
    out.append(DIS)
    return ''.join(out)


def struct_rate_form(c, project, uid, back, csrf_token):
    """'Use my Rate Master rates' -> posts to the EXISTING structural rates route (all six fields)."""
    import rates_v260
    master = rates_v260.rates_for_project(c, project, uid)
    pick = {'concrete_rate': master.get('rmc', 0), 'steel_rate': master.get('steel', 0), 'formwork_rate': master.get('formwork', 0),
            'excavation_rate': master.get('excavation', 0), 'backfill_rate': master.get('backfill', 0)}
    if not any(v > 0 for v in pick.values()):
        return ''
    cur = {}
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_rates_v210'").fetchone():
        r = c.execute('SELECT * FROM civora_rates_v210 WHERE project_id=?', (project['id'],)).fetchone()
        cur = dict(r) if r else {}
    vals = {k: (v if v > 0 else _f(cur.get(k))) for k, v in pick.items()}
    vals['pcc_rate'] = _f(cur.get('pcc_rate'))
    same = all(abs(vals[k] - _f(cur.get(k))) < 1e-9 for k in vals)
    hidden = ''.join(f'<input type="hidden" name="{k}" value="{v:g}">' for k, v in vals.items())
    shown = ', '.join(f'{lbl} ₹{vals[k]:,.0f}' for k, lbl in (('concrete_rate', 'RMC/m³'), ('steel_rate', 'steel/kg'), ('formwork_rate', 'formwork/m²')) if vals[k])
    pid = project['id']
    return (f'<form method="post" action="{ret(f"/projects/{pid}/structural/advanced/rates", back)}" class="cc-rateuse"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">{hidden}'
            f'<span>{"Structural rates match your Rate Master" if same else "Price structural quantities with your Rate Master"}: {esc(shown)}</span>'
            + ('' if same else '<button class="cv-btn sm">Use my Rate Master rates</button>') + '</form>')


def detail_sheet_html(project, items, bars):
    import detailing_v320 as rd
    pid = project['id']
    P = f'/projects/{pid}'
    blocks = ''
    for i in items:
        b = rd.detail_block(i, bars)
        if b:
            q = i['q']
            blocks += (f'<section class="cv-card rd-sheet"><div class="cv-sec" style="margin:0 0 6px"><h2>{esc(i["mark"])} · {esc(i["name"])}</h2>'
                       f'<span class="sub">{int(_f(i["p"].get("count")) or 1)} nos · {_f(i["p"].get("length_m")):g} × {_f(i["p"].get("width_m")):g} × {_f(i["p"].get("depth_m")):g} m · '
                       f'{_f(q.get("net_m3")):,.2f} m³ concrete</span></div>{b}</section>')
    if not blocks:
        blocks = (f'<div class="cv-empty"><b>No footings, columns, beams or slabs yet</b>Add them in the Structural Studio, then add their bars '
                  f'in the BBS Studio (e.g. C1-MAIN, C1-TIES).<div class="actions" style="justify-content:center"><a class="cv-btn" href="{P}/structure">Open Structural Studio</a></div></div>')
    return (f'<div class="cv-ph"><div><span class="eyebrow">SITE DETAIL SHEET · தள விவரத் தாள்</span><h1>Reinforcement details</h1>'
            f'<div class="meta">{esc(project["name"])} · where the rods go, bend and lap — for checking on site</div></div>'
            f'<button class="cv-btn ghost" type="button" onclick="window.print()">{icon("download", 16)} Print / save PDF</button></div>'
            + subnav(P, 'structure') + '<div class="rd-grid">' + blocks + '</div>' + DIS)


# ------------------------------------------------------------------ routes
def register_studio_v310(app, db, owned_project, require, csrf, layout):
    from fastapi import Request, HTTPException
    import team_v270
    app.add_middleware(ReturnToMiddleware)

    def boq_list(c, pid):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_boq_reports'").fetchone():
            return []
        out = []
        for r in c.execute('SELECT id, drawing_id, payload, created FROM civora_boq_reports WHERE project_id=? ORDER BY created DESC, rowid DESC', (pid,)).fetchall():
            try:
                out.append({'id': r['id'], 'drawing_id': r['drawing_id'], 'data': json.loads(r['payload']), 'created': r['created']})
            except (TypeError, ValueError):
                continue
        return out

    def role(request):
        r = getattr(request.state, 'cv_role', 'owner')
        return r, team_v270.allowed(r, 'edit'), team_v270.allowed(r, 'design')

    @app.get('/projects/{pid}/boq')
    def cost_center(request: Request, pid: str):
        p = owned_project(request, pid)
        _, can_edit, _ = role(request)
        with db() as c:
            st = wf.project_status(c, pid)
            boqs = boq_list(c, pid)
            rf = struct_rate_form(c, p, require(request)['id'], f'/projects/{pid}/boq', csrf(request)) if can_edit and st['structural_items'] else ''
        want = request.query_params.get('rev', '')
        cur = next((b for b in boqs if b['id'] == want), boqs[0] if boqs else None)
        return layout(request, 'Cost & BOQ', cost_center_html(p, st, boqs, cur, csrf(request), can_edit, rf))

    @app.get('/projects/{pid}/structure')
    def structure(request: Request, pid: str):
        p = owned_project(request, pid)
        _, can_edit, can_design = role(request)
        with db() as c:
            st = wf.project_status(c, pid)
            items, bars = _load_structural(c, pid)
            intake = c.execute('SELECT element_type, element_mark, status FROM civora_design_intake_v220 WHERE project_id=?', (pid,)).fetchall() \
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_design_intake_v220'").fetchone() else []
            signoff = team_v270.latest_signoff(c, pid)
            rf = struct_rate_form(c, p, require(request)['id'], f'/projects/{pid}/structure', csrf(request)) if can_edit and items else ''
        return layout(request, 'Structural Studio', structure_html(p, st, items, bars, intake, signoff, request.query_params.get('el', ''),
                                                                   csrf(request), can_edit, can_design, rf))

    @app.get('/projects/{pid}/structure/details')
    def structure_details(request: Request, pid: str):
        p = owned_project(request, pid)
        with db() as c:
            items, bars = _load_structural(c, pid)
        return layout(request, 'Reinforcement details', detail_sheet_html(p, items, bars))

    @app.get('/projects/{pid}/bbs')
    def bbs(request: Request, pid: str):
        p = owned_project(request, pid)
        _, can_edit, _ = role(request)
        with db() as c:
            _, bars = _load_structural(c, pid)
            signoff = team_v270.latest_signoff(c, pid)
        return layout(request, 'Bar Bending Schedule', bbs_html(p, bars, signoff, request.query_params.get('bar', ''), csrf(request), can_edit))
