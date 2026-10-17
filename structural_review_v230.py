"""Civora AI v2.3 review studio: no structural design calculations or approvals."""
import csv, io, json, math, time
from html import escape as h
from fastapi import Request, HTTPException
from fastapi.responses import Response

CHECKS = {
 'footing': [('geometry','Approved footing geometry / levels'),('soil','Geotechnical report and bearing/settlement checks'),('loads','Verified axial, moments and combinations'),('shear','One-way and punching shear verification'),('steel','Flexural reinforcement and development checks'),('detail','Cover, starter bars, laps and drawing revision')],
 'column': [('geometry','Effective length, slenderness and restraint'),('loads','Axial force and biaxial moments'),('capacity','Strength interaction and second-order checks'),('steel','Longitudinal steel and minimum/maximum limits'),('ties','Tie spacing, hooks and confinement'),('splice','Lap zones and development length')],
 'beam': [('geometry','Effective span, continuity and supports'),('loads','Factored moments, shear and torsion'),('flexure','Flexural capacity and bar arrangement'),('shear','Shear reinforcement and detailing'),('service','Deflection and crack control'),('splice','Development, anchorage and splice zones')],
 'slab': [('geometry','Panel spans, support conditions and openings'),('loads','Dead, imposed and other applicable actions'),('analysis','One-way/two-way structural analysis'),('flexure','Required steel and arrangement checks'),('service','Deflection, shear and cracking'),('detail','Top/bottom bars, cover and anchorage')],
}
STANDARDS=[('IS 456','Concrete design/detailing'),('IS 875','Relevant design loads'),('IS 1893','Earthquake criteria where applicable'),('IS 13920','Ductile RC detailing where applicable'),('IS 1786','Reinforcement material'),('IS 1904','Foundation/geotechnical design'),('IS 2502','Bar bending and fixing'),('IS 1200','Quantity measurement')]

def register_structural_review_v230(app, db, owned_project, csrf, check_csrf, layout, esc):
    def base(pid): return f'/projects/{pid}/structural/review'
    def records(pid):
        with db() as c:
            names={r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            intake=c.execute('SELECT * FROM civora_design_intake_v220 WHERE project_id=? ORDER BY updated_at DESC',(pid,)).fetchall() if 'civora_design_intake_v220' in names else []
            elems=c.execute('SELECT * FROM civora_structural_v210 WHERE project_id=?',(pid,)).fetchall() if 'civora_structural_v210' in names else []
            bars=c.execute('SELECT * FROM civora_bbs_v210 WHERE project_id=?',(pid,)).fetchall() if 'civora_bbs_v210' in names else []
            rates=c.execute('SELECT * FROM civora_rates_v210 WHERE project_id=?',(pid,)).fetchone() if 'civora_rates_v210' in names else None
        return intake,elems,bars,dict(rates) if rates else {}
    def summaries(pid):
        intake,elems,bars,rates=records(pid)
        q={'rcc':0.,'pcc':0.,'excavation':0.,'backfill':0.,'formwork':0.,'steel':0.}
        for e in elems:
            p=json.loads(e['payload']); r=p['result']; kind=e['kind']; v=float(r['net_m3'])
            if kind=='pcc':q['pcc']+=v
            elif kind in ('excavation','backfill'):q[kind]+=v
            else:q['rcc']+=v
            q['formwork']+=float(r.get('formwork_m2',0))
        for b in bars:
            p=json.loads(b['payload']);q['steel']+=float(p['result']['steel_kg'])
        return intake,elems,bars,rates,q
    def diagram(kind):
        # Conceptual shapes, not engineering detailing.
        common='<rect x="30" y="25" width="210" height="125" rx="5" fill="none" stroke="currentColor" stroke-width="2"/>'
        if kind=='footing':
            body='<rect x="15" y="100" width="240" height="55" fill="#9db6c9" opacity=".4" stroke="currentColor"/><rect x="108" y="15" width="55" height="100" fill="#9db6c9" opacity=".4" stroke="currentColor"/>'
        elif kind=='column':
            body=common+''.join(f'<circle cx="{x}" cy="{y}" r="6" fill="#a36b36"/>' for x in (50,220) for y in (45,130))+'<rect x="43" y="38" width="184" height="99" rx="8" fill="none" stroke="#a36b36" stroke-dasharray="6 5" stroke-width="2"/>'
        elif kind=='beam':
            body='<rect x="12" y="38" width="248" height="95" fill="#9db6c9" opacity=".35" stroke="currentColor"/>'+''.join(f'<line x1="20" x2="250" y1="{y}" y2="{y}" stroke="#a36b36" stroke-width="4"/>' for y in (52,118))
        else:
            body=common+''.join(f'<line x1="{x}" x2="{x}" y1="25" y2="150" stroke="#a36b36" opacity=".7"/>' for x in range(50,240,30))+''.join(f'<line x1="30" x2="240" y1="{y}" y2="{y}" stroke="#a36b36" opacity=".7"/>' for y in range(45,150,25))
        return f'<svg viewBox="0 0 275 175" width="100%" style="max-width:360px;border:1px solid #999;border-radius:8px" role="img" aria-label="Conceptual {h(kind)} diagram">{body}</svg>'
    def show(request,pid):
        owned_project(request,pid)
        intake,elems,bars,rates,q=summaries(pid)
        table=''.join(f'<tr><td>{h(r["element_mark"])}</td><td>{h(r["element_type"])}</td><td>DESIGN INCOMPLETE</td><td><a href="/projects/{h(pid)}/structural/design/{h(r["id"])}">Inputs</a></td></tr>' for r in intake)
        codes=''.join(f'<tr><td>{h(k)}</td><td>{h(v)}</td><td>Edition / amendments require verification</td></tr>' for k,v in STANDARDS)
        diagrams=''.join(f'<div class="card" style="min-width:200px;flex:1"><h3>{h(kind.title())}</h3>{diagram(kind)}<p>Concept only. Bar size, spacing, hooks and laps are <b>not designed</b>.</p></div>' for kind in CHECKS)
        checklist=''.join(f'<h3>{h(kind.title())}</h3><ul>'+''.join(f'<li>{h(label)} — <b>NOT CHECKED</b></li>' for _,label in items)+'</ul>' for kind,items in CHECKS.items())
        body=f'''<span class="eyebrow">CIVORA AI v2.3 · STRUCTURAL REVIEW</span><h1>Structural Review & Quantity Reconciliation</h1>
        <p><a href="/projects/{h(pid)}">← Project</a> | <a href="/projects/{h(pid)}/structural/advanced">Structural Hub</a> | <a href="/projects/{h(pid)}/structural/design">Design Inputs</a></p>
        <div class="notice"><b>NOT FOR CONSTRUCTION.</b> No structural design calculations, code compliance certification, bar-size selection, lap recommendations or engineer approvals are performed here. The diagrams are conceptual, not reinforcement drawings.</div>
        <div class="card"><h2>Project overview</h2><p>Design input drafts: <b>{len(intake)}</b> · v2.1 measured elements: <b>{len(elems)}</b> · v2.1 BBS entries: <b>{len(bars)}</b></p>
        <p>RCC {q['rcc']:.3f} m³ · PCC {q['pcc']:.3f} m³ · Excavation {q['excavation']:.3f} m³ · Backfill {q['backfill']:.3f} m³ · Formwork {q['formwork']:.2f} m² · Scheduled steel {q['steel']:.2f} kg</p>
        <p><b>Reconciliation rule:</b> these totals include v2.1 records only; original v2.0 and Drawing BOQ are excluded to prevent automatic double counting. No automatic merge into main BOQ.</p></div>
        <div class="card"><h2>Saved engineering inputs</h2><div class="scroll"><table><tr><th>Mark</th><th>Element</th><th>Status</th><th>Record</th></tr>{table or '<tr><td colspan="4">No design inputs saved yet</td></tr>'}</table></div></div>
        <div class="card"><h2>Conceptual element illustrations</h2><div style="display:flex;flex-wrap:wrap;gap:12px">{diagrams}</div></div>
        <div class="card"><h2>Design verification checklist</h2><p>All items remain NOT CHECKED. These are review prompts, not claims of IS compliance.</p>{checklist}</div>
        <div class="card"><h2>Applicable standards register — verify editions</h2><div class="scroll"><table><tr><th>Standard</th><th>Subject</th><th>Verification</th></tr>{codes}</table></div></div>
        <div class="card"><h2>Download project review reports</h2><p><a href="{base(pid)}/export.csv">Download CSV quantity summary</a> | <a href="{base(pid)}/report.html">Printable HTML report (Print → Save as PDF)</a></p><p>For the existing measured BBS and priced structural Excel/PDF reports, use <a href="/projects/{h(pid)}/structural/advanced">Structural Hub</a>.</p></div>'''
        return layout(request,'Structural Review Studio',body)
    @app.get('/projects/{pid}/structural/review')
    def review(request:Request,pid:str): return show(request,pid)
    @app.get('/projects/{pid}/structural/review/export.csv')
    def export_csv(request:Request,pid:str):
        owned_project(request,pid);_,elems,bars,_,q=summaries(pid)
        s=io.StringIO();w=csv.writer(s);w.writerow(['CIVORA AI - MEASURED STRUCTURAL QUANTITY SUMMARY - NOT A DESIGN APPROVAL']);w.writerow(['Quantity','Unit','Value'])
        for k,unit in [('rcc','m3'),('pcc','m3'),('excavation','m3'),('backfill','m3'),('formwork','m2'),('steel','kg')]:w.writerow([k,unit,round(q[k],3)])
        w.writerow([]);w.writerow(['Source','v2.1 only; v2.0 and drawing BOQ excluded']);w.writerow(['Design status','NOT CHECKED - NOT FOR CONSTRUCTION'])
        return Response(s.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="civora_structural_review.csv"'})
    @app.get('/projects/{pid}/structural/review/report.html')
    def report_html(request:Request,pid:str):
        owned_project(request,pid);intake,elems,bars,_,q=summaries(pid)
        rows=''.join(f'<tr><td>{h(k)}</td><td>{v:.3f}</td></tr>' for k,v in q.items())
        code_rows=''.join(f'<li>{h(k)} — {h(label)} (edition and amendments NOT VERIFIED)</li>' for k,label in STANDARDS)
        html=f'''<!doctype html><html><head><meta charset="utf-8"><title>Civora Structural Review</title><style>body{{font:15px Arial;max-width:900px;margin:36px auto;line-height:1.6}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #aaa;padding:8px}}.warn{{border:2px solid #b66;padding:12px}}@media print{{button{{display:none}}}}</style></head><body><h1>Civora AI — Structural Review Report</h1><div class="warn"><b>NOT FOR CONSTRUCTION — DESIGN NOT CHECKED.</b><p>This is a quantity and review-status report, not a structural design calculation or reinforcement approval.</p></div><p>Project ID: {h(pid)}</p><p>Design drafts: {len(intake)}; measured elements: {len(elems)}; BBS records: {len(bars)}.</p><h2>Measured quantities (v2.1 only)</h2><table>{rows}</table><h2>Potential Indian Standards</h2><ul>{code_rows}</ul><p>Existing v2.0 and Drawing BOQ not included. No automatic merging or double-counting.</p><button onclick="window.print()">Print / Save as PDF</button></body></html>'''
        return Response(html,media_type='text/html')
