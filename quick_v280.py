"""Civora AI v2.8.0 - Quick Estimate: only the built-up area -> full estimate.

Type "1000 sq.ft, G+1" and get materials, steel, preliminary frame and cost in one click.
Everything else is a clearly marked typical value (square plan, 3 m floors, 230 mm walls ...),
so the result is a planning estimate; uploading the drawing later gives the accurate one.

  POST /quick                    signed in: creates a project + saved draft BOQ -> workflow
                                 guest: shows quantities only (nothing saved)
  POST /projects/{pid}/quick     same, for an existing project (uses its built-up area)
"""
import csv
import io
import json
import math
import time
import uuid
from collections import OrderedDict

import smart_estimate_v260 as se

MIN_SQFT, MAX_SQFT = 100, 1_000_000
PROJECT_TYPES = ('Residential', 'Commercial', 'Industrial', 'Infrastructure', 'Custom')


def parse_quick(form):
    raw = str(form.get('area', '') or '').replace(',', '').strip()
    try:
        area = float(raw)
    except ValueError:
        raise ValueError('Enter the built-up area in sq.ft, for example 1000')
    if not math.isfinite(area) or not MIN_SQFT <= area <= MAX_SQFT:
        raise ValueError(f'Built-up area must be between {MIN_SQFT:,} and {MAX_SQFT:,} sq.ft')
    try:
        floors = int(str(form.get('floors', '1') or '1'))
    except ValueError:
        raise ValueError('Floors: choose 1, 2 or 3')
    if not 1 <= floors <= 10:
        raise ValueError('Floors must be between 1 and 10')
    return area, floors


def quick_inputs(total_sqft, floors):
    """Typical inputs for a building of `total_sqft` built-up area spread over `floors` floors."""
    plate = total_sqft / floors
    inp = se.build_inputs({}, plate)
    inp['floors'] = {'value': float(floors), 'source': 'user', 'note': 'Chosen by you'}
    note = f'Square plan assumed: {total_sqft:,.0f} sq.ft ÷ {floors} floor(s) = {plate:,.0f} sq.ft per floor'
    for k in ('length', 'width'):
        inp[k]['note'] = note
    # v3.9.0: typical kitchen dado + bathroom tiles (one bathroom per ~500 sq.ft of floor)
    baths = max(round(plate / 500), 1)
    inp['wall_tile'] = {'value': round(8 + 17 * baths, 2), 'source': 'typical',
                        'note': f'Typical: kitchen dado 8 m² + {baths} bathroom(s) × 17 m² per floor'}
    return inp


def quick_estimate(total_sqft, floors, takeoff):
    inp = quick_inputs(total_sqft, floors)
    opts = se.default_options()
    return inp, opts, se.estimate(inp, opts, takeoff, {})


def material_totals(rows):
    agg = OrderedDict()
    for label, area, items in rows:
        for i in items:
            key = (i['material'], i['unit'])
            agg[key] = agg.get(key, 0.0) + float(i['quantity'] or 0)
    return agg


GUEST_KEYS = [('Ready-mix concrete (RMC)', 'm³', 'Ready-mix concrete'), ('Steel planning allowance (not BBS)', 'kg', 'Steel (planning)'),
              ('Cement', 'bags (50 kg)', 'Cement'), ('Bricks', 'nos', 'Bricks'), ('Sand', 'm³', 'Sand'),
              ('Coarse aggregate', 'm³', 'Jelly / aggregate'), ('Tiles', 'nos', 'Floor tiles'), ('Paint', 'litres', 'Paint')]


def save_quick(db, store_upload, p, u, inp, opts, result):
    """Save a quick estimate as a draft BOQ of project p (priced with the project's Rate Master). Returns the BOQ id."""
    import rates_v260
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Item', 'Value', 'Unit', 'Source'])
    for k, x in inp.items():
        w.writerow([se.FIELD[k][1], x['value'], se.FIELD[k][3], se.SOURCE_LABEL[x['source']]])
    fid = store_upload(p['id'], 'Quick_estimate_inputs.csv', out.getvalue().encode('utf-8'), 'text/csv')
    drawing = {'id': fid, 'original_name': 'Quick estimate (area only)'}
    payload = se.build_payload(p, drawing, inp, opts, result, {})
    payload['source_detail'] = 'quick_v280'
    payload['notes'].insert(0, 'QUICK ESTIMATE from built-up area only: plan shape, walls, openings and structure are typical '
                               'values. Upload the drawing (Smart Estimate) for an accurate estimate.')
    with db() as c:
        rates = rates_v260.rates_for_project(c, p, u['id'])
        if any(v > 0 for v in rates.values()):
            rates_v260.apply_rates(payload, rates, payload['builtup_sqft'])
        bid = str(uuid.uuid4())
        c.execute('INSERT INTO civora_boq_reports(id,project_id,drawing_id,payload,created) VALUES(?,?,?,?,?)',
                  (bid, p['id'], fid, json.dumps(payload, ensure_ascii=False), int(time.time())))
    return bid



def register_quick_v280(app, db, owned_project, require, current_user, csrf, check_csrf, layout, esc, takeoff, store_upload):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    from ui_shell import icon
    import rates_v260

    def save(p, u, inp, opts, result):
        return save_quick(db, store_upload, p, u, inp, opts, result)

    def error_page(request, message):
        return layout(request, 'Quick Estimate', f'''<div class="card form" style="max-width:620px"><span class="eyebrow">QUICK ESTIMATE</span>
<h1>Please check the area</h1><p>{esc(message)}</p><div class="actions"><a class="cv-btn" href="javascript:history.back()">← Go back</a></div></div>''')

    def guest_result(request, area, floors, result):
        agg = material_totals(result['rows'])
        rows = ''
        for key, unit, label in GUEST_KEYS:
            q = agg.get((key, unit))
            if q:
                shown = f'{q:,.0f}' if unit in ('nos', 'kg') or 'bag' in unit else f'{q:,.1f}'
                rows += f'<tr><td>{esc(label)}</td><td>{shown} {esc(unit)}</td></tr>'
        fl = 'G' if floors == 1 else f'G+{floors - 1}'
        return layout(request, 'Quick Estimate', f'''<span class="eyebrow">QUICK ESTIMATE · NOT SAVED</span><h1>{area:,.0f} sq.ft · {fl}</h1>
<p class="muted">Main materials for a typical RCC-framed building of this size. Plan shape, walls and structure are typical values.</p>
<div class="cv-row"><section class="cv-card"><h3>{icon("brick", 18)} Main materials</h3><table class="cv-mt"><tr><th>Material</th><th>Quantity</th></tr>{rows}</table>
<p class="hint">Steel is a thumb-rule planning figure; structure sizes need an engineer's design.</p>{__import__("sqft_rate_v360").box_html("", area, 0, save=False, rate=0)}</section>
<section class="cv-card"><h3>{icon("rupee", 18)} Want the cost too?</h3><p>Create a free account to save this project, add your local rates (cement, steel, sand, labour …) and get the full cost, every work item, Excel/PDF reports and team sharing.</p>
<div class="actions"><a class="cv-btn" href="/register">Create free account</a><a class="cv-btn ghost" href="/login">Sign in</a></div></section></div>''')

    @app.post('/quick')
    async def quick(request: Request):
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        try:
            area, floors = parse_quick(form)
            inp, opts, result = quick_estimate(area, floors, takeoff)
        except ValueError as ex:
            return error_page(request, str(ex))
        u = current_user(request)
        if not u:
            return guest_result(request, area, floors, result)
        import preview_v370
        if not preview_v370.confirmed(form):     # v3.7.0: preview first; the project is created only on Save
            pv = {'rows': [{'work': l, 'area': a, 'items': it} for l, a, it in result['rows']], 'notes': result['notes'],
                  'inputs': [{'label': se.FIELD[k][1], 'source': x['source']} for k, x in inp.items()],
                  'builtup_sqft': result['builtup_sqft'], 'floors': floors}
            import rates_v260
            with db() as c:
                rates_v260.apply_rates(pv, rates_v260.effective_rates(rates_v260.load_rates(c, u['id'])), pv['builtup_sqft'])
            return preview_v370.gate(request, form, layout, csrf(request), f'Quick Estimate – {area:,.0f} sq.ft',
                                     preview_v370.boq_summary_html(pv, esc), '/quick', esc, 'Save as new project')
        ptype = form.get('type') if form.get('type') in PROJECT_TYPES else 'Residential'
        name = str(form.get('name', '') or '').strip()[:120] or f'Quick estimate – {area:,.0f} sq.ft'
        location = str(form.get('location', '') or '').strip()[:120] or 'Not specified'
        pid = str(uuid.uuid4())
        with db() as c:
            c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?)', (pid, u['id'], name, ptype, location, area, int(time.time())))
        with db() as c:
            p = c.execute('SELECT * FROM projects WHERE id=?', (pid,)).fetchone()
        bid = save(p, u, inp, opts, result)
        try:
            import team_v270
            with db() as c:
                team_v270.log(c, pid, u['id'], f'Ran Quick Estimate ({area:,.0f} sq.ft, {floors} floor(s))')
        except Exception:
            pass
        return RedirectResponse(f'/projects/{pid}/workflow?estimate={bid}', 303)

    @app.post('/projects/{pid}/quick')
    async def project_quick(request: Request, pid: str):
        p = owned_project(request, pid)                 # edit permission enforced centrally
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        fd = {'area': form.get('area') or p['area'], 'floors': form.get('floors', '1')}
        try:
            area, floors = parse_quick(fd)
            inp, opts, result = quick_estimate(area, floors, takeoff)
        except ValueError as ex:
            return error_page(request, str(ex))
        import preview_v370
        if not preview_v370.confirmed(form):     # v3.7.0: preview first
            pv = {'rows': [{'work': l, 'area': a, 'items': it} for l, a, it in result['rows']], 'notes': result['notes'],
                  'inputs': [{'label': se.FIELD[k][1], 'source': x['source']} for k, x in inp.items()],
                  'builtup_sqft': result['builtup_sqft'], 'floors': floors}
            import rates_v260
            with db() as c:
                rates_v260.apply_rates(pv, rates_v260.rates_for_project(c, p, u['id']), pv['builtup_sqft'])
            return preview_v370.gate(request, form, layout, csrf(request), f'Quick Estimate – {area:,.0f} sq.ft',
                                     preview_v370.boq_summary_html(pv, esc), f'/projects/{pid}/quick', esc, 'Save estimate')
        bid = save(p, u, inp, opts, result)
        return RedirectResponse(f'/projects/{pid}/workflow?estimate={bid}', 303)
