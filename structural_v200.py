"""Civora v2.0 optional structural quantity worksheet. No design inference."""
import csv, io, json, math, time, uuid
from html import escape
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, Response

KINDS = {'footing':'Footing', 'column':'Column', 'beam':'Beam', 'slab':'Slab', 'other':'Other RCC'}
STEEL_KG_PER_M = {6:.222,8:.395,10:.617,12:.888,16:1.58,20:2.47,25:3.85,28:4.83,32:6.31,36:7.99,40:9.87}

def compute(kind,count,length,width,depth,openings=0,waste=5,steel_diameter=None,steel_length=None,steel_bars=None):
    if kind not in KINDS: raise ValueError('Unsupported structural element')
    vals=[count,length,width,depth,openings,waste]
    if not all(math.isfinite(float(v)) for v in vals): raise ValueError('Invalid non-finite number')
    if not (1<=count<=100000 and int(count)==count): raise ValueError('Count must be a positive whole number')
    if not all(0<v<=1000 for v in (length,width,depth)):raise ValueError('Dimensions must be positive metres')
    gross=count*length*width*depth
    if not (0<=openings<gross):raise ValueError('Deduction must be less than gross concrete volume')
    if not (0<=waste<=30):raise ValueError('Wastage must be 0–30%')
    net=gross-openings
    result={'gross_m3':gross,'deduction_m3':openings,'net_m3':net,'concrete_with_waste_m3':net*(1+waste/100)}
    provided=[steel_diameter is not None,steel_length is not None,steel_bars is not None]
    if any(provided):
        if not all(provided):raise ValueError('Provide steel diameter, cut length and bar count together')
        dia=int(steel_diameter)
        if dia not in STEEL_KG_PER_M:raise ValueError('Unsupported steel diameter')
        if not (0<float(steel_length)<=1000 and 1<=int(steel_bars)<=100000 and float(steel_bars)==int(steel_bars)):
            raise ValueError('Invalid steel cutting length or bar count')
        result['steel_kg']=STEEL_KG_PER_M[dia]*float(steel_length)*int(steel_bars)
        result['steel_basis']='Theoretical weight only; laps, bends, hooks, anchorage and cutting waste NOT included'
    return result

def register_structural_v200(app,db,owned_project,csrf,check_csrf,layout,esc):
    def init():
        with db() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS civora_structural_v200 (
            id TEXT PRIMARY KEY,project_id TEXT NOT NULL,element TEXT NOT NULL,
            payload TEXT NOT NULL,created INTEGER NOT NULL)''')
    init()
    def url(pid):return f'/projects/{pid}/structural'
    def validate(request,pid):owned_project(request,pid)
    def render(request,pid,notice=''):
        validate(request,pid)
        with db() as c: rows=c.execute('SELECT * FROM civora_structural_v200 WHERE project_id=? ORDER BY created DESC',(pid,)).fetchall()
        body=[];totals={'net_m3':0,'concrete_with_waste_m3':0,'steel_kg':0}
        for r in rows:
            data=json.loads(r['payload']);res=data['result']
            for k in totals:totals[k]+=res.get(k,0)
            body.append(f'<tr><td>{esc(KINDS.get(r["element"],r["element"]))}</td><td>{esc(data["reference"])}</td><td>{res["gross_m3"]:.3f}</td><td>{res["deduction_m3"]:.3f}</td><td>{res["net_m3"]:.3f}</td><td>{res["concrete_with_waste_m3"]:.3f}</td><td>{res.get("steel_kg",0):.2f}</td><td><form method="post" action="{url(pid)}/{r["id"]}/delete"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button type="submit" onclick="return confirm(\'Delete this item?\')">Delete</button></form></td></tr>')
        options=''.join(f'<option value="{k}">{v}</option>' for k,v in KINDS.items())
        html=f'''<span class="eyebrow">CIVORA v2.0 · ENGINEERING WORKSHEET</span><h1>Structural Quantity Worksheet</h1>
        <p class="warn">Measurement-based estimation only. Does NOT design structures or infer reinforcement from architectural drawings. Verify against approved structural drawings.</p>
        {f'<p class="warn">{esc(notice)}</p>' if notice else ''}
        <div class="card"><h2>Add verified structural element</h2><form method="post" action="{url(pid)}/add">
        <input type="hidden" name="csrf_token" value="{csrf(request)}">
        <label>Reference / drawing mark <input name="reference" maxlength="100" required placeholder="F1 / C2 / B1"></label>
        <label>Element <select name="kind">{options}</select></label>
        <label>Number of elements <input type="number" name="count" min="1" step="1" value="1" required></label>
        <label>Length (m) <input type="number" name="length" min="0.001" step="any" required></label>
        <label>Width (m) <input type="number" name="width" min="0.001" step="any" required></label>
        <label>Depth / thickness (m) <input type="number" name="depth" min="0.001" step="any" required></label>
        <label>Concrete deductions (m³) <input type="number" name="openings" min="0" step="any" value="0"></label>
        <label>Concrete wastage (%) <input type="number" name="waste" min="0" max="30" step="any" value="5"></label>
        <h3>Optional reinforcement schedule (enter all three or leave blank)</h3>
        <label>Bar diameter (mm) <select name="steel_diameter"><option value="">Not supplied</option>{''.join(f'<option value="{d}">{d} mm</option>' for d in STEEL_KG_PER_M)}</select></label>
        <label>Cut length per bar (m) <input type="number" name="steel_length" min="0" step="any"></label>
        <label>Number of bars (total) <input type="number" name="steel_bars" min="1" step="1"></label>
        <button type="submit">Calculate & Save Structural Item</button></form></div>
        <div class="card"><h2>Saved structural quantities</h2><div class="scroll"><table><thead><tr><th>Element</th><th>Mark</th><th>Gross m³</th><th>Deduct m³</th><th>Net m³</th><th>Concrete incl. waste m³</th><th>Steel kg*</th><th></th></tr></thead><tbody>{''.join(body) or '<tr><td colspan="8">No structural measurements yet.</td></tr>'}</tbody></table></div>
        <p><b>Total net RCC:</b> {totals['net_m3']:.3f} m³ · <b>Concrete incl. waste:</b> {totals['concrete_with_waste_m3']:.3f} m³ · <b>Specified reinforcement:</b> {totals['steel_kg']:.2f} kg</p>
        <p class="muted">*Steel only for entered bar schedules; 0 kg means not specified, NOT that steel is unnecessary. Totals exclude unspecified elements.</p>
        <a href="{url(pid)}/export.csv">Export structural worksheet CSV</a></div><p><a href="/projects/{pid}">← Back to project</a></p>'''
        return layout(request,'Structural Quantity Worksheet',html)
    @app.get('/projects/{pid}/structural')
    def index(request:Request,pid:str):return render(request,pid)
    @app.post('/projects/{pid}/structural/add')
    async def add(request:Request,pid:str):
        validate(request,pid);f=await request.form();check_csrf(request,str(f.get('csrf_token','')))
        try:
            reference=str(f.get('reference','')).strip()
            if not reference or len(reference)>100:raise ValueError('Valid drawing mark is required')
            kind=str(f.get('kind',''))
            steel=[f.get(k) for k in ('steel_diameter','steel_length','steel_bars')]
            steel=[None if v is None or str(v).strip()=='' else float(v) for v in steel]
            count=float(f['count']);length=float(f['length']);width=float(f['width']);depth=float(f['depth'])
            openings=float(f.get('openings') or 0);waste=float(f.get('waste') or 0)
            result=compute(kind,count,length,width,depth,openings,waste,*steel)
        except (ValueError,KeyError,TypeError,OverflowError) as e:raise HTTPException(400,str(e))
        import preview_v370
        if not preview_v370.confirmed(f):
            summ=preview_v370.values_table([('Mark',reference),('Element',kind)]+[(k.replace('_',' ').capitalize(),(f'{v:,.3f}' if isinstance(v,float) else v)) for k,v in result.items() if not isinstance(v,(dict,list))],esc)
            return preview_v370.gate(request,f,layout,csrf(request),'Structural worksheet item',summ,f'{url(pid)}/add',esc,'Save item')
        payload={'reference':reference,'count':int(count),'length_m':length,'width_m':width,'depth_m':depth,'openings_m3':openings,'waste_pct':waste,'steel_diameter_mm':steel[0],'steel_length_m':steel[1],'steel_bars':steel[2],'result':result,'status':'USER ENTERED – REQUIRES DRAWING VERIFICATION'}
        with db() as c:c.execute('INSERT INTO civora_structural_v200 VALUES(?,?,?,?,?)',(str(uuid.uuid4()),pid,kind,json.dumps(payload),int(time.time())))
        return RedirectResponse(url(pid),status_code=303)
    @app.post('/projects/{pid}/structural/{sid}/delete')
    async def delete(request:Request,pid:str,sid:str):
        validate(request,pid);f=await request.form();check_csrf(request,str(f.get('csrf_token','')))
        with db() as c:c.execute('DELETE FROM civora_structural_v200 WHERE id=? AND project_id=?',(sid,pid))
        return RedirectResponse(url(pid),status_code=303)
    @app.get('/projects/{pid}/structural/export.csv')
    def export_csv(request:Request,pid:str):
        validate(request,pid)
        with db() as c:rows=c.execute('SELECT * FROM civora_structural_v200 WHERE project_id=? ORDER BY created',(pid,)).fetchall()
        out=io.StringIO();writer=csv.writer(out)
        writer.writerow(['Element','Reference','Count','Length m','Width m','Depth m','Gross m3','Deduction m3','Net m3','Concrete incl waste m3','Specified steel kg','Verification status'])
        for r in rows:
            d=json.loads(r['payload']);v=d['result'];writer.writerow([KINDS.get(r['element'],r['element']),d['reference'],d['count'],d['length_m'],d['width_m'],d['depth_m'],round(v['gross_m3'],5),round(v['deduction_m3'],5),round(v['net_m3'],5),round(v['concrete_with_waste_m3'],5),round(v.get('steel_kg',0),5),d['status']])
        return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="civora_structural_worksheet.csv"'})
