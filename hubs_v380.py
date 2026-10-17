"""Civora AI v3.8.0 - the six sections: Home, Projects, Estimate, Structure, Guide, More.

Estimate / Structure / More are hub pages: every tool of the app in one place, for the chosen
project. Guide holds the Vastu guide, the IS code guide (what each code is used for in Civora),
how-to steps and the sample drawings.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / 'sample_drawings'

IS_CODES = [
    # code, title, what Civora uses it for, what Civora does NOT do
    ('IS 456 : 2000', 'Plain and reinforced concrete – code of practice',
     'Concrete grades (M15–M50), nominal mix M20 = 1:1.5:3, minimum RCC grade M20, typical clear cover in the reinforcement sketches (footing 50, column 40, beam 25, slab 20 mm).',
     'No strength, deflection, crack-width or member design check.'),
    ('IS 10262 : 2019', 'Concrete mix proportioning – guidelines',
     'Site-mix "approved design mix" option: you enter the cement, sand, aggregate and water kg per m³ from the lab mix design.',
     'Civora does not design the mix.'),
    ('IS 269 / 1489 / 455', 'OPC, PPC and PSC cement',
     'Cement in 50 kg bags; Rate Master cement prices (OPC 53, PPC).', 'Cement type selection is the engineer\'s decision.'),
    ('IS 383 : 2016', 'Coarse and fine aggregates (incl. M-sand)',
     'Sand / M-sand / 20 mm jelly quantities by dry volume (dry factor 1.33 for mortar, 1.54 for concrete).', 'No grading or quality test.'),
    ('IS 1786 : 2008', 'High-strength deformed steel bars (TMT Fe500/500D)',
     'Unit weight of bars = d²/162 kg/m (density 7,850 kg/m³) in the BBS and steel quantities.', 'No bar size or spacing design.'),
    ('IS 2502 : 1963', 'Bending and fixing of bars',
     'Bar bending schedule: cut length = straight + hooks + laps − bend deductions (45° = 1d, 90° = 2d, 135° = 3d per bend).', 'Lap and anchorage lengths come from the approved drawing.'),
    ('IS 13920 : 2016', 'Ductile design and detailing (earthquake)',
     'Reinforcement sketches show the usual 135° hooks on ties and lap zones away from joints – for site checking.', 'No ductile detailing design.'),
    ('SP 34 : 1987', 'Handbook on concrete reinforcement and detailing',
     'Drawing conventions in the footing / column / beam / slab detail sketches.', '—'),
    ('IS 1200 (Parts 1, 2, 3, 5, 12, 13, 15)', 'Method of measurement of building works',
     'Units (m³ concrete, m² plaster/paint/formwork), opening deductions from walls, plaster on both faces, measurement basis (external / centreline / internal).', 'Civora applies simplified rules – check the contract measurement.'),
    ('IS 1077 : 1992', 'Common burnt clay building bricks',
     'Brick 190 × 90 × 90 mm + 10 mm joint = 500 bricks per m³; mortar = wall volume − brick volume.', '—'),
    ('IS 2185 (Part 3)', 'AAC (autoclaved aerated concrete) blocks',
     'AAC block count (600 × 200 × 200 mm default), thin-bed adhesive by coverage kg/m².', '—'),
    ('IS 2212 : 1991', 'Brickwork – code of practice', 'Mortar 1:6 default for brickwork (1:3 to 1:8 selectable).', '—'),
    ('IS 1661 : 1972', 'Cement and cement-lime plaster', 'Plaster 12 mm inside, 15 mm outside, 6 mm ceiling; mortar 1:4.', '—'),
    ('IS 875 (Parts 1–3)', 'Design loads – dead, imposed, wind', 'Not used in calculations.', 'Loads must be taken by the structural engineer.'),
    ('IS 1893 : 2016', 'Earthquake resistant design', 'Not used in calculations.', 'Seismic design must be done by the engineer.'),
    ('IS 1904 / IS 2950', 'Foundations – shallow and raft', 'Typical footing sizes are only PLANNING values for quantity.', 'Bearing capacity and footing design by the engineer.'),
    ('IS 2911', 'Pile foundations', 'Pile concrete volume = count × π/4 × D² × length.', 'No pile capacity design.'),
    ('IS 3370', 'Concrete water-retaining structures', 'Tank / sump component quantities only.', 'Water-tightness design by the engineer.'),
    ('NBC 2016', 'National Building Code of India', 'Typical parapet height 0.9–1.0 m, staircase planning values.', 'Approval rules (setbacks, FSI) are local – check with your authority.'),
]

HOW_TO = [
    ('1. Set your rates', 'More → Rate Master. Market prices are already filled – change any to your dealer\'s price.', '/rates'),
    ('2. Create a project', 'Projects → New project: name, place, built-up area.', '/projects/new'),
    ('3. Estimate', 'Estimate → Quick (only area), Smart (one drawing) or Multi-drawing (GF + FF + sections). Check the preview, then Save.', '/estimate'),
    ('4. Structure', 'Structure → add footings, columns, beams, slabs from the structural drawing, then bars in the BBS.', '/structure'),
    ('5. Vastu', 'Guide → Vastu: upload the plan, say which side is North, get room-by-room suggestions.', '/guide/vastu'),
    ('6. Cost & reports', 'Project → BOQ & Cost; More → Reports for Excel / PDF / Download all.', '/reports'),
]


def register_hubs_v380(app, db, require, csrf, layout, esc, current_user):
    from fastapi import Request, HTTPException
    from fastapi.responses import FileResponse, RedirectResponse
    from ui_shell import icon
    import team_v270

    def projects_for(u):
        with db() as c:
            return team_v270.accessible_projects(c, u['id'], limit=200)

    def picker(request, u, base):
        rows = projects_for(u)
        want = request.query_params.get('p', '')
        sel = next((r for r in rows if r['id'] == want), rows[0] if rows else None)
        if not rows:
            return None, (f'<div class="cv-review" style="margin:0 0 16px">{icon("folder", 16)}<span>Create a project first – every tool works inside a project. '
                          f'<a href="/projects/new"><b>New project →</b></a></span></div>')
        opts = ''.join(f'<option value="{esc(r["id"])}"{" selected" if sel and r["id"] == sel["id"] else ""}>{esc(r["name"])} · {esc(r["location"])}</option>' for r in rows)
        return sel, (f'<form method="get" action="{base}" class="cv-card" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 16px;padding:12px 16px">'
                     f'<b>Project</b><select name="p" onchange="this.form.submit()" style="max-width:420px">{opts}</select>'
                     f'<noscript><button class="cv-btn sm">Open</button></noscript></form>')

    def cards(items):
        out = ''
        for ic, title, sub, href in items:
            if href:
                out += (f'<a class="cv-card" href="{esc(href)}" style="display:block;text-decoration:none;color:inherit">'
                        f'<h3>{icon(ic, 18)} {esc(title)}</h3><p class="sub" style="margin:0">{esc(sub)}</p></a>')
            else:
                out += f'<div class="cv-card" style="opacity:.55"><h3>{icon(ic, 18)} {esc(title)}</h3><p class="sub" style="margin:0">{esc(sub)}</p></div>'
        return f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px">{out}</div>'

    def hub(request, title, eyebrow, intro, items):
        return layout(request, title, f'<span class="eyebrow">{esc(eyebrow)}</span><h1>{esc(title)}</h1><p class="muted">{esc(intro)}</p>{items}')

    @app.get('/estimate')
    def estimate_hub(request: Request):
        u = require(request)
        sel, pick = picker(request, u, '/estimate')
        P = f'/projects/{sel["id"]}' if sel else None
        g = lambda s: f'{P}/{s}' if P else ''
        items = cards([
            ('calc', 'Quick Estimate', 'Only the built-up area → full materials and cost.', '/#quick' if not P else g('smart') + '#quick'),
            ('upload', 'Smart Estimate', 'Upload one drawing → Civora reads it, you check, then save.', g('smart')),
            ('layers', 'Multi-drawing analysis', 'Ground + first floor + sections together → one combined estimate.', g('multi')),
            ('drawing', 'Drawing Studio', 'See every drawing of the project and what was read from it.', g('studio')),
            ('drawing', 'Measure on drawing', 'Calibrate the scale and measure lengths / areas by clicking.', g('drawings')),
            ('brick', 'Material takeoff', 'One work item at a time: brickwork, plaster, concrete, tiles, paint, steel.', g('takeoff')),
            ('rupee', 'BOQ & Cost', 'All materials with rates, cost by stage, rate per sq.ft.', g('boq')),
        ])
        return hub(request, 'Estimate', 'ESTIMATE · மதிப்பீடு', 'Every way to get quantities and cost.', pick + items)

    @app.get('/structure')
    def structure_hub(request: Request):
        u = require(request)
        sel, pick = picker(request, u, '/structure')
        P = f'/projects/{sel["id"]}' if sel else None
        g = lambda s: f'{P}/{s}' if P else ''
        items = cards([
            ('beam', 'Structural Studio', 'Footings, piles, columns, beams, slabs, stairs, tanks – 48 element types.', g('structure')),
            ('brick', 'Bar Bending Schedule', 'Bars by mark, cut length, weight, order list by diameter.', g('bbs')),
            ('drawing', 'Reinforcement details', 'Footing / column / beam / slab sketches for site checking.', g('structure/details')),
            ('shield', 'Design inputs', 'Record the engineer\'s design inputs (concrete grade, loads, soil …).', g('structural/design')),
            ('check', 'Design review & sign-off', 'Compare quantities and inputs; the engineer signs off.', g('structural/review')),
            ('book', 'IS code guide', 'Which IS code is used for what in Civora.', '/guide/is-codes'),
        ])
        return hub(request, 'Structure', 'STRUCTURE · கட்டமைப்பு', 'Structural quantities, steel and the engineer\'s review.', pick + items)

    @app.get('/guide')
    def guide_hub(request: Request):
        require(request)
        items = cards([
            ('pin', 'Vastu guide & drawing check', 'What goes where, and a room-by-room check of your plan.', '/guide/vastu'),
            ('book', 'IS code guide', 'Every IS code Civora follows and what it is used for.', '/guide/is-codes'),
            ('check', 'How to use Civora', 'Six steps from rates to reports.', '/guide/how-to'),
            ('download', 'Sample drawings', 'Practice files for estimate and Vastu (PDF, PNG, DXF).', '/guide/samples'),
        ])
        return hub(request, 'Guide', 'GUIDE · வழிகாட்டி', 'Vastu, IS codes, how-to and practice drawings.', items)

    @app.get('/guide/vastu')
    def guide_vastu(request: Request):
        u = require(request)
        import vastu_v360 as vv
        sel, pick = picker(request, u, '/guide/vastu')
        P = f'/projects/{sel["id"]}' if sel else ''
        act = (f'<div class="actions" style="margin:0 0 16px"><a class="cv-btn" href="{P}/vastu/drawing">{icon("upload", 16)} Check a drawing</a>'
               f'<a class="cv-btn ghost" href="{P}/vastu">Choose rooms myself</a></div>') if P else ''
        rows = ''.join(f'<tr><td><b>{esc(w)}</b></td><td>{esc(en)}<br><small class="muted">{esc(ta)}</small></td></tr>' for w, en, ta in vv.GUIDE)
        tips = ''.join(f'<li>{esc(en)}<br><small class="muted">{esc(ta)}</small></li>' for en, ta in vv.TIPS)
        best = ''.join(f'<tr><td><b>{esc(en)}</b><br><small class="muted">{esc(ta)}</small></td><td>{esc(", ".join(vv.ZONE[z][1] for z in ideal)) or "Depends on plot facing"}</td>'
                       f'<td>{esc(", ".join(vv.ZONE[z][1] for z in avoid)) or "—"}</td></tr>' for _k, en, ta, ideal, ok, avoid, _t in vv.ITEMS)
        body = (pick + act + f'<div class="cv-review" style="margin:0 0 16px">{icon("shield", 16)}<span>Vastu is traditional guidance, not engineering. Structure, light, ventilation, fire safety and approval rules come first.</span></div>'
                f'<section class="cv-card"><h3>What goes where · எது எங்கே</h3><div class="scroll"><table class="cv-mt"><tr><th style="width:28%">Direction</th><th>Best used for</th></tr>{rows}</table></div></section>'
                f'<section class="cv-card" style="margin-top:16px"><h3>Room by room · அறை வாரியாக</h3><div class="scroll"><table class="cv-mt"><tr><th>Room / item</th><th>Best</th><th>Avoid</th></tr>{best}</table></div></section>'
                f'<section class="cv-card" style="margin-top:16px"><h3>General tips · பொது குறிப்புகள்</h3><ul>{tips}</ul></section>')
        return hub(request, 'Vastu guide', 'GUIDE · வாஸ்து', 'Traditional direction guidance for Indian homes.', body)

    @app.get('/guide/is-codes')
    def guide_codes(request: Request):
        require(request)
        rows = ''.join(f'<tr><td style="white-space:nowrap"><b>{esc(c)}</b></td><td><b>{esc(t)}</b><br><small>{esc(use)}</small></td><td><small class="muted">{esc(no)}</small></td></tr>'
                       for c, t, use, no in IS_CODES)
        body = (f'<div class="cv-review" style="margin:0 0 16px">{icon("shield", 16)}<span>Civora follows these codes for <b>quantities, units and site-checking sketches</b>. '
                'It does NOT design or certify structures – DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.</span></div>'
                f'<section class="cv-card"><div class="scroll"><table class="cv-mt"><tr><th>Code</th><th>Used in Civora for</th><th>Not done by Civora</th></tr>{rows}</table></div></section>')
        return hub(request, 'IS code guide', 'GUIDE · IS CODES', 'Which Indian Standard is used for what in Civora.', body)

    @app.get('/guide/how-to')
    def guide_how(request: Request):
        require(request)
        body = cards([('check', t, d, h) for t, d, h in HOW_TO])
        return hub(request, 'How to use Civora', 'GUIDE · HOW TO', 'From rates to reports in six steps.', body)

    @app.get('/guide/samples')
    def guide_samples(request: Request):
        require(request)
        files = sorted(p.name for p in SAMPLES.glob('Civora_Sample_*') if p.suffix.lower() in ('.pdf', '.png', '.dxf'))
        rows = ''.join(f'<tr><td>{esc(n)}</td><td><a class="cv-btn sm ghost" href="/guide/samples/{esc(n)}">Download</a></td></tr>' for n in files)
        body = (f'<section class="cv-card"><p class="sub"><b>Estimate plan</b> – 12 × 10 m 2BHK with full notes, for Smart / Multi-drawing estimate. '
                f'<b>Vastu plan</b> – east-facing house (one room deliberately in the wrong corner).</p>'
                f'<table class="cv-mt"><tr><th>File</th><th></th></tr>{rows}</table></section>')
        return hub(request, 'Sample drawings', 'GUIDE · SAMPLES', 'Practice files.', body)

    @app.get('/guide/samples/{name}')
    def guide_sample_file(request: Request, name: str):
        require(request)
        path = SAMPLES / Path(name).name
        if not path.name.startswith('Civora_Sample_') or not path.is_file():
            raise HTTPException(404, 'Sample not found')
        return FileResponse(path, filename=path.name)

    @app.get('/more')
    def more_hub(request: Request):
        u = require(request)
        import admin_v380
        sel, pick = picker(request, u, '/more')
        P = f'/projects/{sel["id"]}' if sel else None
        g = lambda s: f'{P}/{s}' if P else ''
        items = [('rupee', 'Rate Master', 'Market prices, editable – used by every estimate.', '/rates'),
                 ('report', 'Reports', 'Excel, PDF, printable summary, Download all.', '/reports'),
                 ('users', 'Project team', 'Invite engineers, colleagues, customers to this project.', g('team')),
                 ('folder', 'Project data', 'Everything stored in this project, with delete.', g('data')),
                 ('layers', 'Recycle Bin', 'Deleted items – restore them.', '/bin'),
                 ('download', 'Move my data', 'Export / import projects between PC and online.', '/transfer'),
                 ('settings', 'Settings', 'Guided / Expert mode, Tamil / English.', '/settings')]
        if admin_v380.is_site_owner(u):
            items.append(('shield', 'Data storage', 'Where your data is kept and if it is safe.', '/system/storage'))
            items[0:0] = [('users', 'Users & activity', 'All users, what they do, delete a user.', '/admin/users'),
                          ('chart', 'Audit log', 'Every action by every user.', '/admin/audit')]
        return hub(request, 'More', 'MORE · மேலும்', 'Rates, reports, team, data and settings.', pick + cards(items))

    @app.get('/projects/{pid}/more')
    def project_more(request: Request, pid: str):
        return RedirectResponse(f'/more?p={pid}', 303)
