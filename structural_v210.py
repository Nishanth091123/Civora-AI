"""Civora v2.1 consolidated, measurement-led structural quantity, BBS and cost workspace.
No structural design or automatic interpretation of drawing geometry is claimed.
"""
import csv, io, json, math, time, uuid
from html import escape as h
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, Response

ELEMENTS = {
 'excavation':('Excavation','m3','box'), 'backfill':('Backfill','m3','box'),
 'pcc':('Plain Cement Concrete','m3','box'), 'isolated_footing':('Isolated Footing','m3','box'),
 'combined_footing':('Combined Footing','m3','box'), 'raft':('Raft Foundation','m3','box'),
 'pedestal':('Pedestal','m3','box'), 'column':('RCC Column','m3','box'),
 'plinth_beam':('Plinth Beam','m3','box'), 'grade_beam':('Grade Beam','m3','box'),
 'roof_beam':('Roof Beam','m3','box'), 'lintel':('Lintel','m3','box'),
 'slab':('RCC Slab','m3','box'), 'sunshade':('Sunshade / Chajja','m3','box'),
 'staircase':('Staircase - Measured Concrete','m3','box'),
 'retaining_wall':('Retaining Wall','m3','box'), 'shear_wall':('Shear Wall','m3','box'),
 'rcc_wall':('RCC Wall','m3','box'), 'parapet':('Parapet','m3','box'),
 'sump':('Sump - Component Volume','m3','box'), 'septic_tank':('Septic Tank - Component Volume','m3','box'),
 'other_rcc':('Other RCC','m3','box'),
 # v3.8.0: every common building element (cyl = round: enter diameter as length AND width)
 'strip_footing':('Strip / Wall Footing','m3','box'), 'stepped_footing':('Stepped Footing','m3','box'),
 'pile':('Pile (bored, round)','m3','cyl'), 'pile_cap':('Pile Cap','m3','box'),
 'grade_slab':('Floor Slab on Grade','m3','box'), 'circular_column':('Circular Column','m3','cyl'),
 'tie_beam':('Tie Beam','m3','box'), 'ring_beam':('Ring / Band Beam','m3','box'),
 'cantilever_beam':('Cantilever Beam','m3','box'), 'secondary_beam':('Secondary Beam','m3','box'),
 'flat_slab':('Flat Slab','m3','box'), 'sunken_slab':('Sunken Slab (toilet)','m3','box'),
 'cantilever_slab':('Balcony / Cantilever Slab','m3','box'), 'porch_slab':('Portico / Car Porch Slab','m3','box'),
 'loft':('Loft / Shelf Slab','m3','box'), 'waist_slab':('Staircase Waist Slab','m3','box'),
 'stair_landing':('Staircase Landing','m3','box'), 'stair_steps':('Staircase Steps (triangles)','m3','tri'),
 'ramp':('Ramp','m3','box'), 'overhead_tank':('Overhead Water Tank - Component','m3','box'),
 'lift_pit':('Lift Pit','m3','box'), 'lift_wall':('Lift Wall','m3','box'),
 'manhole':('Manhole / Inspection Chamber','m3','box'), 'compound_wall_beam':('Compound Wall Beam / Column','m3','box'),
 'coping':('Coping / Kerb','m3','box'), 'fins':('Vertical Fins / Mullions','m3','box'),
}
SHAPE_FACTOR={'box':1.0,'cyl':math.pi/4,'tri':0.5}
SHAPE_HINT={'cyl':'Round: enter the diameter as BOTH length and width; depth = height / length of the pile. Volume = count × π/4 × D² × depth.',
            'tri':'Stair steps: count = number of steps, length = tread, width = stair width, depth = riser. Volume = ½ × tread × riser × width.'}
DIAMETERS=(6,8,10,12,16,20,25,28,32,36,40)

def num(v, label, low=0, high=1e8, strictly=False):
 try: x=float(v)
 except (ValueError,TypeError,OverflowError): raise ValueError(f'{label}: enter a valid number')
 if not math.isfinite(x) or x<low or x>high or (strictly and x<=low):raise ValueError(f'{label}: value out of range')
 return x

def whole(v,label,high=100000):
 x=num(v,label,1,high)
 if not x.is_integer():raise ValueError(f'{label}: whole number required')
 return int(x)

def quantity(kind,count,length,width,depth,deduction=0,waste=5,formwork=0):
 if kind not in ELEMENTS:raise ValueError('Unsupported element')
 c=whole(count,'Count');l=num(length,'Length (m)',0,1000,True);w=num(width,'Width (m)',0,1000,True);d=num(depth,'Depth (m)',0,1000,True)
 gross=c*l*w*d*SHAPE_FACTOR[ELEMENTS[kind][2]]; deduct=num(deduction,'Deduction (m3)',0,gross)
 if deduct>=gross:raise ValueError('Deduction must be smaller than gross volume')
 waste=num(waste,'Wastage (%)',0,30);shutter=num(formwork,'Verified formwork area (m2)',0,1e8)
 return {'gross_m3':gross,'deduction_m3':deduct,'net_m3':gross-deduct,'order_m3':(gross-deduct)*(1+waste/100),'formwork_m2':shutter}

def bar_schedule(diameter,bar_count,straight_length,bend_allowance=0,hook_allowance=0,lap_allowance=0,waste=0):
 dia=whole(diameter,'Bar diameter',40)
 if dia not in DIAMETERS:raise ValueError('Unsupported bar diameter')
 count=whole(bar_count,'Bar count')
 straight=num(straight_length,'Straight bar length (m)',0,1000,True)
 bend=num(bend_allowance,'Bend deduction (m)',0,100)
 hook=num(hook_allowance,'Hook allowance (m)',0,100)
 lap=num(lap_allowance,'Lap allowance (m)',0,100)
 waste=num(waste,'Steel wastage (%)',0,30)
 # v3.7.0: bends SHORTEN the cut length (IS 2502 practice: 45° = 1d, 90° = 2d, 135° = 3d per bend); hooks and laps add.
 cut=straight+hook+lap-bend
 if cut<=0:raise ValueError('Bend deduction is larger than the bar length')
 unit_weight=dia*dia/162.0
 weight=count*cut*unit_weight
 return {'cut_length_m':cut,'total_length_m':count*cut,'steel_kg':weight,'order_steel_kg':weight*(1+waste/100),'unit_weight_kg_m':unit_weight}

def register_structural_v210(app,db,owned_project,csrf,check_csrf,layout,esc):
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS civora_structural_v210 (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL, reference TEXT NOT NULL, drawing_ref TEXT NOT NULL DEFAULT '', payload TEXT NOT NULL, created INTEGER NOT NULL)''')
  c.execute('''CREATE TABLE IF NOT EXISTS civora_bbs_v210 (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, reference TEXT NOT NULL, payload TEXT NOT NULL, created INTEGER NOT NULL)''')
  c.execute('''CREATE TABLE IF NOT EXISTS civora_rates_v210 (project_id TEXT PRIMARY KEY, concrete_rate REAL NOT NULL DEFAULT 0, steel_rate REAL NOT NULL DEFAULT 0, formwork_rate REAL NOT NULL DEFAULT 0, excavation_rate REAL NOT NULL DEFAULT 0, backfill_rate REAL NOT NULL DEFAULT 0, pcc_rate REAL NOT NULL DEFAULT 0, updated INTEGER NOT NULL)''')
 def root(pid):return f'/projects/{pid}/structural/advanced'
 def read(pid):
  with db() as c:
   items=c.execute('SELECT * FROM civora_structural_v210 WHERE project_id=? ORDER BY created,id',(pid,)).fetchall()
   bars=c.execute('SELECT * FROM civora_bbs_v210 WHERE project_id=? ORDER BY created,id',(pid,)).fetchall()
   rates=c.execute('SELECT * FROM civora_rates_v210 WHERE project_id=?',(pid,)).fetchone()
   legacy=c.execute("SELECT * FROM civora_structural_v200 WHERE project_id=?" ,(pid,)).fetchall() if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='civora_structural_v200'").fetchone() else []
  return items,bars,dict(rates) if rates else {},legacy
 def report(pid):
  items,bars,rates,legacy=read(pid)
  totals={'rcc_m3':0.,'pcc_m3':0.,'excavation_m3':0.,'backfill_m3':0.,'formwork_m2':0.,'steel_kg':0.,'rcc_order_m3':0.}
  for item in items:
   p=json.loads(item['payload']);q=p['result'];k=item['kind'];vol=q['net_m3']
   if k=='excavation':totals['excavation_m3']+=vol
   elif k=='backfill':totals['backfill_m3']+=vol
   elif k=='pcc':totals['pcc_m3']+=vol
   else:totals['rcc_m3']+=vol;totals['rcc_order_m3']+=q['order_m3']
   totals['formwork_m2']+=q['formwork_m2']
  for b in bars:totals['steel_kg']+=json.loads(b['payload'])['result']['steel_kg']
  amounts={
   'RCC concrete':totals['rcc_order_m3']*rates.get('concrete_rate',0),
   'PCC':totals['pcc_m3']*rates.get('pcc_rate',0),
   'Excavation':totals['excavation_m3']*rates.get('excavation_rate',0),
   'Backfill':totals['backfill_m3']*rates.get('backfill_rate',0),
   'Formwork':totals['formwork_m2']*rates.get('formwork_rate',0),
   'Reinforcement':totals['steel_kg']*rates.get('steel_rate',0),
  }
  return items,bars,rates,legacy,totals,amounts
 def postform(request):return request.form()
 def safe_ref(v):
  s=str(v or '').strip()
  if not s or len(s)>100:raise ValueError('Reference required (max 100 characters)')
  return s
 def nav(pid):return f'<p><a href="/projects/{pid}">← Project Dashboard</a> &nbsp; | &nbsp; <a href="/projects/{pid}/drawings">Drawings</a> &nbsp; | &nbsp; <a href="/projects/{pid}/structural">Original v2.0 worksheet</a></p>'
 def render(request,pid):
  owned_project(request,pid)
  items,bars,rates,legacy,totals,amounts=report(pid)
  options=''.join(f'<option value="{k}">{h(v[0])}</option>' for k,v in ELEMENTS.items())
  diameter_options=''.join(f'<option value="{d}">{d} mm</option>' for d in DIAMETERS)
  token=h(csrf(request));base=root(pid)
  table=[]
  for i in items:
   p=json.loads(i['payload']);q=p['result'];table.append(f'<tr><td>{h(ELEMENTS[i["kind"]][0])}</td><td>{h(i["reference"])}</td><td>{h(i["drawing_ref"])}</td><td>{q["net_m3"]:.3f}</td><td>{q["formwork_m2"]:.2f}</td><td><a href="{base}/{i["id"]}/edit">Edit</a> <form style="display:inline" method="post" action="{base}/{i["id"]}/delete"><input type="hidden" name="csrf_token" value="{token}"><button onclick="return confirm(\'Delete this measurement?\')">Delete</button></form></td></tr>')
  btable=[]
  for b in bars:
   p=json.loads(b['payload']);q=p['result'];btable.append(f'<tr><td>{h(b["reference"])}</td><td>{p["diameter_mm"]}</td><td>{p["count"]}</td><td>{q["cut_length_m"]:.3f}</td><td>{q["steel_kg"]:.2f}</td><td><form method="post" action="{base}/bbs/{b["id"]}/delete"><input type="hidden" name="csrf_token" value="{token}"><button onclick="return confirm(\'Delete bar entry?\')">Delete</button></form></td></tr>')
  ratefields=[('concrete_rate','RCC concrete / m³'),('pcc_rate','PCC / m³'),('steel_rate','Steel / kg'),('formwork_rate','Formwork / m²'),('excavation_rate','Excavation / m³'),('backfill_rate','Backfill / m³')]
  rf=''.join(f'<label>{label} (₹)<input type="number" name="{key}" min="0" max="100000000" step="any" value="{rates.get(key,0)}" required></label>' for key,label in ratefields)
  costrows=''.join(f'<tr><td>{h(k)}</td><td>₹ {v:,.2f}</td></tr>' for k,v in amounts.items())
  html=f'''<span class="eyebrow">CIVORA AI v2.1 · STRUCTURAL QUANTITY HUB</span><h1>Structural Elements, BBS & Cost</h1>{nav(pid)}
  <div class="notice">Quantities are measurement-led, not structural design. Drawing references are entered manually and require verification against approved drawings. Do not add the same work again in Drawing BOQ or original v2.0 totals.</div>
  <div class="grid"><div class="card"><h2>Structural Measurement</h2><form method="post" action="{base}/add"><input type="hidden" name="csrf_token" value="{token}">
  <label>Drawing / element mark<input name="reference" maxlength="100" placeholder="F1 / C1 / B1" required></label>
  <label>Drawing source / sheet reference (optional)<input name="drawing_ref" maxlength="150" placeholder="S-02 / engineer verified"></label>
  <label>Structural element<select name="kind">{options}</select></label>
  <label>Count<input name="count" type="number" min="1" max="100000" value="1" step="1" required></label>
  <label>Length (m)<input name="length" type="number" min="0.0001" step="any" required></label>
  <label>Width (m)<input name="width" type="number" min="0.0001" step="any" required></label>
  <label>Depth / thickness (m)<input name="depth" type="number" min="0.0001" step="any" required></label>
  <label>Verified deductions (m³)<input name="deduction" type="number" min="0" step="any" value="0"></label>
  <label>Concrete wastage (%)<input name="waste" type="number" min="0" max="30" step="any" value="5"></label>
  <label>Verified formwork (m²) – 0 if unknown<input name="formwork" type="number" min="0" step="any" value="0"></label>
  <button>Calculate & Save Element</button></form><p class="muted">For staircase, tanks and irregular shapes, split into separately measured rectangular components. Do not treat an enclosing box as actual concrete volume.</p></div>
  <div class="card"><h2>Reinforcement Bar Bending Schedule</h2><form method="post" action="{base}/bbs/add"><input type="hidden" name="csrf_token" value="{token}">
  <label>Bar mark / element reference<input name="reference" maxlength="100" required placeholder="C1-MAIN"></label><label>Diameter<select name="diameter">{diameter_options}</select></label>
  <label>Total bar count<input name="count" type="number" min="1" step="1" required></label><label>Straight length / bar (m)<input name="length" type="number" min="0.001" step="any" required></label>
  <label>Bend deduction / bar (m) – 90° bend = 2 × bar dia<input name="bend" type="number" min="0" step="any" value="0"></label><label>Hook allowance / bar (m)<input name="hook" type="number" min="0" step="any" value="0"></label>
  <label>Lap allowance / bar (m)<input name="lap" type="number" min="0" step="any" value="0"></label><label>Steel wastage (%)<input name="waste" type="number" min="0" max="30" step="any" value="3"></label>
  <button>Calculate & Save Bar Schedule</button></form><p class="muted">Theoretical steel weight = d²/162 kg/m. Enter approved bend, lap and hook lengths; no automatic code-compliant detailing is inferred.</p></div></div>
  <div class="card"><h2>Saved Structural Elements ({len(items)})</h2><div class="scroll"><table><thead><tr><th>Element</th><th>Mark</th><th>Drawing</th><th>Net m³</th><th>Formwork m²</th><th>Action</th></tr></thead><tbody>{''.join(table) or '<tr><td colspan="6">No v2.1 elements yet</td></tr>'}</tbody></table></div></div>
  <div class="card"><h2>Saved BBS ({len(bars)})</h2><div class="scroll"><table><thead><tr><th>Mark</th><th>Dia mm</th><th>Count</th><th>Cut m/bar</th><th>Steel kg</th><th>Action</th></tr></thead><tbody>{''.join(btable) or '<tr><td colspan="6">No BBS rows yet</td></tr>'}</tbody></table></div></div>
  <div class="grid"><div class="card"><h2>Structural Quantity Abstract</h2><p>RCC net: <b>{totals['rcc_m3']:.3f} m³</b> · RCC incl. wastage: <b>{totals['rcc_order_m3']:.3f} m³</b></p><p>PCC: <b>{totals['pcc_m3']:.3f} m³</b> · Excavation: <b>{totals['excavation_m3']:.3f} m³</b> · Backfill: <b>{totals['backfill_m3']:.3f} m³</b></p><p>Verified formwork: <b>{totals['formwork_m2']:.2f} m²</b> · Scheduled steel: <b>{totals['steel_kg']:.2f} kg</b></p><p class="muted">Existing v2.0 rows: {len(legacy)} (retained, not double-counted in this v2.1 abstract).</p></div>
  <div class="card"><h2>Project Structural Rates</h2><form method="post" action="{base}/rates"><input type="hidden" name="csrf_token" value="{token}">{rf}<button>Save Rates</button></form></div></div>
  <div class="card"><h2>Structural BOQ / Cost Abstract</h2><div class="scroll"><table><thead><tr><th>Work</th><th>Amount</th></tr></thead><tbody>{costrows}<tr><th>Estimated total (entered rates only)</th><th>₹ {sum(amounts.values()):,.2f}</th></tr></tbody></table></div><p class="muted">Zero rates mean not priced. This is a separate structural cost view; it is NOT automatically added to the existing drawing BOQ, to prevent duplicate billing.</p>
  <div class="actions"><a class="primary" href="{base}/export.xlsx">Download Complete Excel</a><a class="primary" href="{base}/export.pdf">Download PDF</a><a href="{base}/export.csv">Download CSV</a></div></div>'''
  return layout(request,'Structural Quantity Hub',html)
 @app.get('/projects/{pid}/structural/advanced')
 def index(request:Request,pid:str):return render(request,pid)
 async def save_item(request,pid,item_id=None):
  owned_project(request,pid);f=await postform(request);check_csrf(request,str(f.get('csrf_token','')))
  try:
   kind=str(f.get('kind',''));reference=safe_ref(f.get('reference'))
   drawing_ref=str(f.get('drawing_ref') or '').strip()[:150]
   args={k:f.get(k) for k in ('count','length','width','depth','deduction','waste','formwork')}
   result=quantity(kind,*(args[k] for k in ('count','length','width','depth')),args['deduction'] or 0,args['waste'] or 0,args['formwork'] or 0)
   payload={'count':whole(args['count'],'Count'),'length_m':float(args['length']),'width_m':float(args['width']),'depth_m':float(args['depth']),'deduction_m3':float(args['deduction'] or 0),'waste_pct':float(args['waste'] or 0),'formwork_m2':float(args['formwork'] or 0),'result':result,'verification':'USER ENTERED; CHECK APPROVED DRAWING'}
  except (ValueError,TypeError,KeyError) as e:raise HTTPException(400,str(e))
  import preview_v370
  if not preview_v370.confirmed(f):   # v3.7.0: show the quantity first, save only on confirm
   summ=preview_v370.values_table([('Element',ELEMENTS[kind][0]),('Mark',reference),('Count × L × W × D',f"{payload['count']} × {payload['length_m']:g} × {payload['width_m']:g} × {payload['depth_m']:g} m"),
     ('Gross volume',f"{result['gross_m3']:,.3f} m³"),('Deduction',f"{result['deduction_m3']:,.3f} m³"),('Net volume',f"{result['net_m3']:,.3f} m³"),
     ('Order quantity (with wastage)',f"{result['order_m3']:,.3f} m³"),('Formwork (as entered)',f"{result['formwork_m2']:,.2f} m²")],h)
   act=f'{root(pid)}/{item_id}/edit' if item_id else f'{root(pid)}/add'
   return preview_v370.gate(request,f,layout,csrf(request),'Structural element',summ,act,h,'Save element')
  with db() as c:
   if item_id:
    cur=c.execute('UPDATE civora_structural_v210 SET kind=?,reference=?,drawing_ref=?,payload=? WHERE id=? AND project_id=?',(kind,reference,drawing_ref,json.dumps(payload),item_id,pid))
    if not cur.rowcount:raise HTTPException(404,'Item not found')
   else:c.execute('INSERT INTO civora_structural_v210 VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),pid,kind,reference,drawing_ref,json.dumps(payload),int(time.time())))
  return RedirectResponse(root(pid),303)
 @app.post('/projects/{pid}/structural/advanced/add')
 async def add(request:Request,pid:str):return await save_item(request,pid)
 @app.get('/projects/{pid}/structural/advanced/{item_id}/edit')
 def edit(request:Request,pid:str,item_id:str):
  owned_project(request,pid)
  with db() as c:item=c.execute('SELECT * FROM civora_structural_v210 WHERE id=? AND project_id=?',(item_id,pid)).fetchone()
  if not item:raise HTTPException(404,'Item not found')
  p=json.loads(item['payload']);token=h(csrf(request));base=root(pid)
  fields=''.join(f'<label>{label}<input type="number" step="any" name="{key}" value="{p[key]}"></label>' for key,label in [('count','Count'),('length_m','Length'),('width_m','Width'),('depth_m','Depth'),('deduction_m3','Deduction'),('waste_pct','Wastage %'),('formwork_m2','Formwork m²')])
  opts=''.join(f'<option value="{k}" {"selected" if k==item["kind"] else ""}>{h(v[0])}</option>' for k,v in ELEMENTS.items())
  # Map stored names to form field names without relying on JS.
  fields=fields.replace('name="length_m"','name="length"').replace('name="width_m"','name="width"').replace('name="depth_m"','name="depth"').replace('name="deduction_m3"','name="deduction"').replace('name="waste_pct"','name="waste"').replace('name="formwork_m2"','name="formwork"')
  return layout(request,'Edit Structural Element',f'<h1>Edit Structural Element</h1><div class="card"><form method="post" action="{base}/{item_id}/edit"><input type="hidden" name="csrf_token" value="{token}"><label>Mark<input name="reference" value="{h(item["reference"])}" required></label><label>Drawing ref<input name="drawing_ref" value="{h(item["drawing_ref"])}"></label><label>Element<select name="kind">{opts}</select></label>{fields}<button>Save Changes</button></form></div><p><a href="{base}">← Cancel</a></p>')
 @app.post('/projects/{pid}/structural/advanced/{item_id}/edit')
 async def update(request:Request,pid:str,item_id:str):return await save_item(request,pid,item_id)
 @app.post('/projects/{pid}/structural/advanced/{item_id}/delete')
 async def delete(request:Request,pid:str,item_id:str):
  owned_project(request,pid);f=await postform(request);check_csrf(request,str(f.get('csrf_token','')))
  with db() as c:c.execute('DELETE FROM civora_structural_v210 WHERE project_id=? AND id=?',(pid,item_id))
  return RedirectResponse(root(pid),303)
 @app.post('/projects/{pid}/structural/advanced/bbs/add')
 async def add_bbs(request:Request,pid:str):
  owned_project(request,pid);f=await postform(request);check_csrf(request,str(f.get('csrf_token','')))
  try:
   ref=safe_ref(f.get('reference'));d=whole(f.get('diameter'),'Diameter',40);n=whole(f.get('count'),'Count')
   vals={k:num(f.get(k) or 0,k,0,1000) for k in ('length','bend','hook','lap','waste')}
   res=bar_schedule(d,n,vals['length'],vals['bend'],vals['hook'],vals['lap'],vals['waste'])
  except (ValueError,TypeError) as e:raise HTTPException(400,str(e))
  payload={'diameter_mm':d,'count':n,**vals,'result':res,'verification':'USER ENTERED; CHECK APPROVED BBS'}
  import preview_v370
  if not preview_v370.confirmed(f):
   summ=preview_v370.values_table([('Bar mark',ref),('Bars',f'{n} nos × {d} mm'),('Cut length per bar',f"{vals['length']:g} + hook {vals['hook']:g} + lap {vals['lap']:g} − bends {vals['bend']:g} = {res['cut_length_m']:,.3f} m"),
     ('Total length',f"{res['total_length_m']:,.2f} m"),('Unit weight',f"{res['unit_weight_kg_m']:.3f} kg/m (d²/162)"),('Steel weight',f"{res['steel_kg']:,.2f} kg"),('Order weight (with wastage)',f"{res['order_steel_kg']:,.2f} kg")],h)
   return preview_v370.gate(request,f,layout,csrf(request),'Bar bending schedule line',summ,f'{root(pid)}/bbs/add',h,'Save bar')
  with db() as c:c.execute('INSERT INTO civora_bbs_v210 VALUES(?,?,?,?,?)',(str(uuid.uuid4()),pid,ref,json.dumps(payload),int(time.time())))
  return RedirectResponse(root(pid),303)
 @app.post('/projects/{pid}/structural/advanced/bbs/{bar_id}/delete')
 async def del_bbs(request:Request,pid:str,bar_id:str):
  owned_project(request,pid);f=await postform(request);check_csrf(request,str(f.get('csrf_token','')))
  with db() as c:c.execute('DELETE FROM civora_bbs_v210 WHERE project_id=? AND id=?',(pid,bar_id))
  return RedirectResponse(root(pid),303)
 @app.post('/projects/{pid}/structural/advanced/rates')
 async def save_rates(request:Request,pid:str):
  owned_project(request,pid);f=await postform(request);check_csrf(request,str(f.get('csrf_token','')))
  keys=('concrete_rate','steel_rate','formwork_rate','excavation_rate','backfill_rate','pcc_rate')
  try:values=[num(f.get(k),k,0,1e8) for k in keys]
  except ValueError as e:raise HTTPException(400,str(e))
  with db() as c:c.execute('INSERT INTO civora_rates_v210 VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET '
    'concrete_rate=excluded.concrete_rate,steel_rate=excluded.steel_rate,formwork_rate=excluded.formwork_rate,excavation_rate=excluded.excavation_rate,'
    'backfill_rate=excluded.backfill_rate,pcc_rate=excluded.pcc_rate,updated=excluded.updated',(pid,*values,int(time.time())))
  return RedirectResponse(root(pid),303)
 def csv_data(pid):
  items,bars,rates,legacy,totals,amounts=report(pid)
  out=io.StringIO();w=csv.writer(out)
  w.writerow(['STRUCTURAL ELEMENTS – verified dimensions required']);w.writerow(['Element','Reference','Drawing reference','Count','Length m','Width m','Depth m','Deduction m3','Net m3','Concrete with wastage m3','Formwork m2'])
  for i in items:
   p=json.loads(i['payload']);q=p['result'];w.writerow([ELEMENTS[i['kind']][0],i['reference'],i['drawing_ref'],p['count'],p['length_m'],p['width_m'],p['depth_m'],p['deduction_m3'],q['net_m3'],q['order_m3'],q['formwork_m2']])
  w.writerow([]);w.writerow(['BAR BENDING SCHEDULE – theoretical weight; engineer verification required']);w.writerow(['Bar mark','Diameter mm','Count','Cut length m','Steel kg','Order kg'])
  for b in bars:
   p=json.loads(b['payload']);q=p['result'];w.writerow([b['reference'],p['diameter_mm'],p['count'],q['cut_length_m'],q['steel_kg'],q['order_steel_kg']])
  w.writerow([]);w.writerow(['STRUCTURAL ABSTRACT']);w.writerow(['Quantity','Value'])
  for k,v in totals.items():w.writerow([k,v])
  w.writerow([]);w.writerow(['COST ABSTRACT']);w.writerow(['Work','Amount INR'])
  for k,v in amounts.items():w.writerow([k,v])
  w.writerow(['Total',sum(amounts.values())]);w.writerow(['Legacy v2.0 rows retained, excluded from v2.1 totals',len(legacy)])
  return out.getvalue()
 @app.get('/projects/{pid}/structural/advanced/export.csv')
 def export_csv(request:Request,pid:str):
  owned_project(request,pid)
  return Response('\ufeff'+csv_data(pid),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="civora_structural_v210.csv"'})
 @app.get('/projects/{pid}/structural/advanced/export.xlsx')
 def export_xlsx(request:Request,pid:str):
  owned_project(request,pid)
  try:from openpyxl import Workbook
  except ImportError:raise HTTPException(503,'Install openpyxl: pip install openpyxl')
  items,bars,rates,legacy,totals,amounts=report(pid);wb=Workbook();ws=wb.active;ws.title='Structural Elements'
  ws.append(['Element','Mark','Drawing','Count','Length m','Width m','Depth m','Deduction m3','Net m3','Order m3','Formwork m2'])
  for i in items:
   p=json.loads(i['payload']);q=p['result'];ws.append([ELEMENTS[i['kind']][0],i['reference'],i['drawing_ref'],p['count'],p['length_m'],p['width_m'],p['depth_m'],p['deduction_m3'],q['net_m3'],q['order_m3'],q['formwork_m2']])
  ws=wb.create_sheet('BBS');ws.append(['Mark','Diameter mm','Count','Straight m','Bend m','Hook m','Lap m','Cut m','Steel kg','Order kg'])
  for b in bars:
   p=json.loads(b['payload']);q=p['result'];ws.append([b['reference'],p['diameter_mm'],p['count'],p['length'],p['bend'],p['hook'],p['lap'],q['cut_length_m'],q['steel_kg'],q['order_steel_kg']])
  ws=wb.create_sheet('Quantity Abstract');ws.append(['Quantity','Value'])
  for k,v in totals.items():ws.append([k,v])
  ws=wb.create_sheet('Rates and Cost');ws.append(['Work','Amount INR'])
  for k,v in amounts.items():ws.append([k,v])
  ws.append(['Total',sum(amounts.values())]);ws.append(['v2.0 legacy rows excluded',len(legacy)])
  for sheet in wb:
   sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
   for col in sheet.columns:
    letter=col[0].column_letter;sheet.column_dimensions[letter].width=min(42,max(15,max(len(str(cell.value or '')) for cell in col)+2))
  buf=io.BytesIO();wb.save(buf)
  return Response(buf.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="civora_structural_v210.xlsx"'})
 @app.get('/projects/{pid}/structural/advanced/export.pdf')
 def export_pdf(request:Request,pid:str):
  owned_project(request,pid)
  try:
   from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
   from reportlab.lib.styles import getSampleStyleSheet
   from reportlab.lib import colors
  except ImportError:raise HTTPException(503,'Install reportlab: pip install reportlab')
  items,bars,rates,legacy,totals,amounts=report(pid);buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=(595,842));styles=getSampleStyleSheet()
  story=[Paragraph('CIVORA AI - STRUCTURAL QUANTITY REPORT',styles['Title']),Paragraph('Measurement-based estimate. Verify approved structural drawings and BBS. v2.0 entries are excluded from these totals.',styles['Normal']),Spacer(1,14)]
  for heading,rows in [('Quantity Abstract',[(k,f'{v:,.3f}') for k,v in totals.items()]),('Cost Abstract (INR)',[(k,f'{v:,.2f}') for k,v in amounts.items()])]:
   story.append(Paragraph(heading,styles['Heading2']));t=Table([['Item','Value']]+rows,colWidths=[330,160]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.3,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP')]));story.append(t);story.append(Spacer(1,12))
  story.append(Paragraph('Structural Elements',styles['Heading2']))
  for i in items:
   p=json.loads(i['payload']);story.append(Paragraph(h(f'{ELEMENTS[i["kind"]][0]} | {i["reference"]} | {p["result"]["net_m3"]:.3f} m3 | drawing: {i["drawing_ref"]}'),styles['Normal']))
  story.append(Spacer(1,10));story.append(Paragraph('Bar Bending Schedule',styles['Heading2']))
  for b in bars:
   p=json.loads(b['payload']);story.append(Paragraph(h(f'{b["reference"]} | {p["diameter_mm"]} mm | {p["count"]} bars | {p["result"]["steel_kg"]:.2f} kg'),styles['Normal']))
  doc.build(story)
  return Response(buf.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="civora_structural_v210.pdf"'})
