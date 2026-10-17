"""Civora v2.2 engineering design intake. NOT a structural analysis/design engine."""
import json, time, uuid, math
from html import escape
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

# Input completeness is not engineering adequacy. No bar or member sizes are selected.
ELEMENT_FIELDS = {
 'footing': [('length_m','Footing length (m)'),('width_m','Footing width (m)'),('thickness_m','Footing thickness (m)'),('column_load_kn','Service column load (kN)'),('soil_bearing_kpa','Geotechnical bearing value (kPa)'),('concrete_grade_mpa','Concrete characteristic strength (MPa)'),('steel_grade_mpa','Rebar yield strength (MPa)')],
 'column': [('width_m','Column width (m)'),('depth_m','Column depth (m)'),('height_m','Unbraced height (m)'),('axial_load_kn','Factored axial load (kN)'),('moment_x_knm','Factored Mx (kN·m)'),('moment_y_knm','Factored My (kN·m)'),('concrete_grade_mpa','Concrete characteristic strength (MPa)'),('steel_grade_mpa','Rebar yield strength (MPa)')],
 'beam': [('span_m','Analysis span (m)'),('width_m','Beam width (m)'),('depth_m','Beam overall depth (m)'),('moment_knm','Factored design moment (kN·m)'),('shear_kn','Factored design shear (kN)'),('concrete_grade_mpa','Concrete characteristic strength (MPa)'),('steel_grade_mpa','Rebar yield strength (MPa)')],
 'slab': [('span_x_m','Clear span X (m)'),('span_y_m','Clear span Y (m)'),('thickness_m','Slab thickness (m)'),('dead_load_kpa','Additional dead load (kN/m²)'),('live_load_kpa','Imposed load (kN/m²)'),('concrete_grade_mpa','Concrete characteristic strength (MPa)'),('steel_grade_mpa','Rebar yield strength (MPa)')],
}
COMMON=[('drawing_revision','Drawing / revision'),('support_conditions','Support / restraint description'),('load_source','Load calculation / analysis reference'),('code_edition','Verified applicable IS code editions and amendments'),('engineer_notes','Design engineer notes')]
CODE_CANDIDATES={'footing':'IS 456; IS 1904; IS 875; IS 1893 as applicable','column':'IS 456; IS 13920 and IS 1893 where applicable','beam':'IS 456; IS 13920 and IS 1893 where applicable','slab':'IS 456; IS 875; IS 1893 where applicable'}

def validate(kind, values):
 if kind not in ELEMENT_FIELDS: raise ValueError('Unsupported structural element')
 errors=[]; clean={}
 for key,label in ELEMENT_FIELDS[kind]:
  raw=str(values.get(key,'')).strip()
  if not raw: errors.append(f'{label}: required'); continue
  try: value=float(raw)
  except (ValueError, OverflowError): errors.append(f'{label}: invalid number'); continue
  if not math.isfinite(value) or abs(value)>1e9: errors.append(f'{label}: invalid range'); continue
  if key not in ('moment_x_knm','moment_y_knm','moment_knm') and value<=0:
   if key=='dead_load_kpa' and value==0: pass
   else: errors.append(f'{label}: must be positive'); continue
  clean[key]=value
 for key,label in COMMON:
  value=str(values.get(key,'')).strip()
  if not value: errors.append(f'{label}: required')
  elif len(value)>1200: errors.append(f'{label}: too long')
  else: clean[key]=value
 return clean,errors

def register_structural_design_v220(app,db,owned_project,csrf,check_csrf,layout,esc):
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS civora_design_intake_v220
   (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, element_type TEXT NOT NULL,
    element_mark TEXT NOT NULL, inputs_json TEXT NOT NULL, status TEXT NOT NULL,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)''')
 def base(pid):return f'/projects/{pid}/structural/design'
 def page(request,pid,message=''):
  owned_project(request,pid)
  with db() as c:
   rows=c.execute('SELECT * FROM civora_design_intake_v220 WHERE project_id=? ORDER BY updated_at DESC',(pid,)).fetchall()
  token=escape(csrf(request))
  opts=''.join(f'<option value="{escape(k)}">{escape(k.title())}</option>' for k in ELEMENT_FIELDS)
  formfields=[]
  for kind, fields in ELEMENT_FIELDS.items():
   inputs=''.join(f'<label>{escape(label)}<input type="number" name="{escape(key)}" step="any" placeholder="Enter verified value"></label>' for key,label in fields)
   formfields.append(f'<section data-kind="{kind}" class="card design-fields" style="display:{"block" if kind=="footing" else "none"}"><h3>{kind.title()} design inputs</h3>{inputs}</section>')
  common=''.join(f'<label>{escape(label)}<input name="{escape(key)}" maxlength="1200" placeholder="Source and revision required"></label>' for key,label in COMMON)
  items=''.join(f'<tr><td>{escape(r["element_mark"])}</td><td>{escape(r["element_type"].title())}</td><td>{escape(r["status"])}</td><td><a href="{base(pid)}/{r["id"]}">View inputs</a></td></tr>' for r in rows)
  body=f'''<span class="eyebrow">CIVORA AI v2.2 · ENGINEERING INTAKE</span><h1>IS Code Design Input & Verification</h1>
  <p><a href="/projects/{pid}/structural/advanced">← Structural Quantity Hub</a></p>
  <div class="notice"><b>NOT FOR CONSTRUCTION.</b> This module captures and validates engineering inputs only. It does not perform structural analysis, verify code clauses, size members, select reinforcement, or approve designs. All records remain DESIGN INCOMPLETE until a separately validated engineering engine and professional review are available.</div>
  {f'<div class="msg">{escape(message)}</div>' if message else ''}
  <div class="card"><h2>New design input record</h2><form method="post" action="{base(pid)}/save"><input type="hidden" name="csrf_token" value="{token}">
  <label>Element mark<input name="element_mark" maxlength="100" required placeholder="F1 / C1 / B1 / S1"></label>
  <label>Element type<select name="element_type" id="design-element" onchange="document.querySelectorAll(\'.design-fields\').forEach(x=>x.style.display=x.dataset.kind===this.value?\'block\':\'none\')">{opts}</select></label>
  {''.join(formfields)}<div class="card"><h3>Shared engineering evidence</h3>{common}</div><button>Validate & Save Draft</button></form></div>
  <div class="card"><h2>Saved design input records ({len(rows)})</h2><div class="scroll"><table><tr><th>Mark</th><th>Element</th><th>State</th><th>Details</th></tr>{items or '<tr><td colspan="4">No design inputs saved</td></tr>'}</table></div></div>'''
  return layout(request,'Structural Design Intake',body)
 @app.get('/projects/{pid}/structural/design')
 def design_home(request:Request,pid:str):return page(request,pid)
 @app.post('/projects/{pid}/structural/design/save')
 async def design_save(request:Request,pid:str):
  owned_project(request,pid); form=await request.form();check_csrf(request,str(form.get('csrf_token','')))
  kind=str(form.get('element_type',''));mark=str(form.get('element_mark','')).strip()
  if not mark or len(mark)>100:raise HTTPException(400,'Valid element mark required')
  clean,errors=validate(kind,form)
  if errors: return page(request,pid,'Not saved: '+'; '.join(errors))
  import preview_v370
  if not preview_v370.confirmed(form):
   summ=preview_v370.values_table([('Element mark',mark),('Element type',kind)]+[(k,v) for k,v in (clean.items() if isinstance(clean,dict) else [])])
   return preview_v370.gate(request,form,layout,csrf(request),'Design input record',summ,base(pid)+'/save',esc,'Save draft')
  now=int(time.time());rid=str(uuid.uuid4())
  with db() as c:
   c.execute('INSERT INTO civora_design_intake_v220 VALUES(?,?,?,?,?,?,?,?)',(rid,pid,kind,mark,json.dumps({'inputs':clean,'code_candidates':CODE_CANDIDATES[kind],'validation':'INPUT PRESENCE AND TYPE ONLY; NO IS CODE CHECK'}),'DESIGN INCOMPLETE',now,now))
  return RedirectResponse(base(pid)+'/'+rid,status_code=303)
 @app.get('/projects/{pid}/structural/design/{rid}')
 def design_detail(request:Request,pid:str,rid:str):
  owned_project(request,pid)
  with db() as c: row=c.execute('SELECT * FROM civora_design_intake_v220 WHERE id=? AND project_id=?',(rid,pid)).fetchone()
  if row is None:raise HTTPException(404,'Design record not found')
  p=json.loads(row['inputs_json'])
  trs=''.join(f'<tr><td>{escape(k)}</td><td>{escape(v)}</td></tr>' for k,v in p['inputs'].items())
  body=f'''<h1>Design input: {escape(row['element_mark'])}</h1><p><a href="{base(pid)}">← All design records</a></p>
  <div class="notice"><b>DESIGN INCOMPLETE — NOT FOR CONSTRUCTION.</b> Recorded inputs are not checked against Indian Standards. No reinforcement or safety approval is implied.</div>
  <div class="card"><p><b>Element:</b> {escape(row['element_type'])}</p><p><b>Potential code references (edition unverified):</b> {escape(p['code_candidates'])}</p><div class="scroll"><table><tr><th>Input</th><th>Entered value</th></tr>{trs}</table></div></div>'''
  return layout(request,'Design Input Record',body)
