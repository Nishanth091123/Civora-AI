'Civora drawing workspace. Measurements are manual and calibrated; never inferred from unverified drawing annotations.'
import io,math,html,json,uuid,time,csv,re
from pathlib import Path
from fastapi import Request,Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse,Response,StreamingResponse

UNIT={'m':1.,'ft':.3048,'mm':.001}
EXT={'.pdf','.png','.jpg','.jpeg','.dxf'}

def finite(x,lo=None,hi=None):
    x=float(x)
    if not math.isfinite(x) or (lo is not None and x<lo) or (hi is not None and x>hi):raise ValueError('Invalid or out-of-range drawing measurement')
    return x

def polygon_area(pts):
    return abs(sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts)))/2)

def measured_geometry(payload):
    if not isinstance(payload,dict):raise ValueError('Invalid measurement')
    pts=payload.get('points'); cal=payload.get('calibration')
    if not isinstance(pts,list) or not 2<=len(pts)<=100 or not isinstance(cal,list) or len(cal)!=2:raise ValueError('Select calibrated points and a measurement')
    def point(v):
        if not isinstance(v,list) or len(v)!=2:raise ValueError('Invalid point')
        return [finite(v[0],0,100000),finite(v[1],0,100000)]
    pts=[point(x) for x in pts];c1,c2=[point(x) for x in cal]
    pixels=math.hypot(c1[0]-c2[0],c1[1]-c2[1]);known=finite(payload.get('known_length'),.000001,1e7)
    unit=payload.get('unit')
    if unit not in UNIT or pixels<2:raise ValueError('Calibrate using two distinct points')
    factor=known*UNIT[unit]/pixels
    mode=payload.get('mode')
    if mode=='length' and len(pts)==2:amount=math.dist(pts[0],pts[1])*factor;dimension='m'
    elif mode=='area' and len(pts)>=3:amount=polygon_area(pts)*factor**2;dimension='m²'
    elif mode=='rectangle' and len(pts)==2:amount=abs(pts[0][0]-pts[1][0])*abs(pts[0][1]-pts[1][1])*factor**2;dimension='m²'
    else:raise ValueError('Length/rectangle need 2 points; polygon area needs at least 3 points')
    if not 0<amount<1e9:raise ValueError('Invalid measured quantity')
    return {'amount':amount,'dimension':dimension,'mode':mode,'calibration_m_per_pixel':factor,'points':pts,'calibration': [c1,c2], 'known_length':known,'unit':unit}

def dxf_svg(path):
    import ezdxf
    doc=ezdxf.readfile(str(path));m=doc.modelspace();shapes=[];coords=[]
    for e in m:
        if len(shapes)>12000:break
        typ=e.dxftype()
        try:
            if typ=='LINE':
                a=e.dxf.start;b=e.dxf.end; coords.extend([(a.x,a.y),(b.x,b.y)]);shapes.append(('line',[(a.x,a.y),(b.x,b.y)]))
            elif typ in ('LWPOLYLINE','POLYLINE'):
                if typ=='LWPOLYLINE':pts=[(x,y) for x,y,*_ in e.get_points()]
                else:pts=[(v.dxf.location.x,v.dxf.location.y) for v in e.vertices]
                if len(pts)>1 and len(pts)<3000:coords.extend(pts);shapes.append(('poly',pts))
            elif typ=='CIRCLE':
                c=e.dxf.center;r=float(e.dxf.radius)
                if 0<r<1e8:coords.extend([(c.x-r,c.y-r),(c.x+r,c.y+r)]);shapes.append(('circle',(c.x,c.y,r)))
            elif typ=='ARC':
                c=e.dxf.center;r=float(e.dxf.radius);a=math.radians(e.dxf.start_angle);b=math.radians(e.dxf.end_angle)
                if b<a:b+=2*math.pi
                pts=[(c.x+r*math.cos(a+(b-a)*i/48),c.y+r*math.sin(a+(b-a)*i/48)) for i in range(49)]
                coords.extend(pts);shapes.append(('poly',pts))
        except (ValueError,TypeError,AttributeError):continue
    if not coords:raise ValueError('No supported DXF geometry. Supported: LINE, LWPOLYLINE, POLYLINE, CIRCLE, ARC. Complex blocks/XREF require flattening.')
    xs=[p[0] for p in coords];ys=[p[1] for p in coords];xmin=min(xs);xmax=max(xs);ymin=min(ys);ymax=max(ys)
    w=max(1,xmax-xmin);h=max(1,ymax-ymin);scale=min(1600/w,1200/h);margin=25;W=w*scale+margin*2;H=h*scale+margin*2
    def cv(p):return (margin+(p[0]-xmin)*scale,margin+(ymax-p[1])*scale)
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.1f}" height="{H:.1f}" viewBox="0 0 {W:.1f} {H:.1f}"><rect width="100%" height="100%" fill="white"/><g fill="none" stroke="#143c5d" stroke-width="1.5">']
    for typ,pts in shapes:
        if typ=='circle':
            x,y=cv((pts[0],pts[1]));lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{pts[2]*scale:.2f}"/>')
        else:
            s=' '.join(f'{x:.2f},{y:.2f}' for x,y in (cv(p) for p in pts));lines.append(f'<polyline points="{s}"/>')
    lines.append('</g></svg>')
    return ''.join(lines)



def inspect_dxf(path):
    """Conservative vector extraction: dimensions only, never labels walls automatically."""
    import ezdxf
    doc=ezdxf.readfile(str(path))
    units=int(doc.header.get('$INSUNITS',0))
    scale={1:.0254,2:.3048,4:.001,5:.01,6:1.,14:.1}.get(units)
    if scale is None: return {'error':'DXF drawing units are unspecified or unsupported. Confirm dimensions manually.'}
    segments=[];polygons=[];text=[]
    for e in doc.modelspace():
        kind=e.dxftype()
        if kind=='LINE':
            a=e.dxf.start;b=e.dxf.end
            segments.append(((float(a.x)*scale,float(a.y)*scale),(float(b.x)*scale,float(b.y)*scale),str(e.dxf.layer)))
        elif kind=='LWPOLYLINE':
            pts=[(float(x)*scale,float(y)*scale) for x,y,*_ in e.get_points()]
            if len(pts)>1:
                for a,b in zip(pts,pts[1:]):segments.append((a,b,str(e.dxf.layer)))
                if e.closed:
                    segments.append((pts[-1],pts[0],str(e.dxf.layer)))
                    polygons.append((abs(polygon_area(pts)),str(e.dxf.layer)))
        elif kind in ('TEXT','MTEXT'):
            text.append(str(e.dxf.text if kind=='TEXT' else e.text)[:100])
    if not segments:return {'error':'No supported LINE/LWPOLYLINE geometry detected; use manual measurements.'}
    xs=[v[0] for a,b,_ in segments for v in (a,b)];ys=[v[1] for a,b,_ in segments for v in (a,b)]
    layers={}
    for a,b,layer in segments:
        if layer not in layers:layers[layer]={'length':0.,'segments':0}
        layers[layer]['length']+=math.dist(a,b);layers[layer]['segments']+=1
    return {'length':max(xs)-min(xs),'width':max(ys)-min(ys),'layers':layers,'closed_areas':polygons,'labels':text[:20],'segments':len(segments),'units':units}

def register_drawing_routes(app,db,owned_project,require,csrf,check_csrf,layout,esc,FILES,takeoff,WORKS):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS drawing_measurements(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),upload_id TEXT NOT NULL REFERENCES uploads(id),page INTEGER NOT NULL,work TEXT NOT NULL,measurement_json TEXT NOT NULL,result_json TEXT NOT NULL,created INTEGER NOT NULL)''')

    def drawing_file(request,pid,fid):
        owned_project(request,pid)
        with db() as c:r=c.execute('SELECT * FROM uploads WHERE id=? AND project_id=?',(fid,pid)).fetchone()
        if not r:raise HTTPException(404,'Drawing not found')
        path=FILES/r['stored_name']
        if path.suffix.lower() not in EXT or not path.is_file():raise HTTPException(400,'Unsupported drawing')
        return r,path

    @app.get('/projects/{pid}/drawings')
    def drawings_home(request:Request,pid:str):
        p=owned_project(request,pid)
        with db() as c:
            fs=c.execute('SELECT * FROM uploads WHERE project_id=? ORDER BY created DESC',(pid,)).fetchall()
            records=c.execute('SELECT d.*,u.original_name FROM drawing_measurements d JOIN uploads u ON u.id=d.upload_id WHERE d.project_id=? ORDER BY d.created DESC',(pid,)).fetchall()
        links=''.join(f'<tr><td>{esc(r["original_name"])}</td><td><a class="primary small" href="/projects/{pid}/drawings/{r["id"]}">View drawing →</a> <form method="post" action="/projects/{pid}/uploads/{r["id"]}/delete" style="display:inline" onsubmit="return confirm(&quot;Permanently delete this uploaded drawing and its saved drawing measurements? This cannot be undone.&quot;)"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button type="submit" style="background:#a33333">Delete</button></form></td></tr>' for r in fs if Path(r['stored_name']).suffix.lower() in EXT)
        saved=''.join(f'<tr><td>{esc(r["original_name"])}</td><td>{esc(r["work"])}</td><td><a href="/projects/{pid}/drawings/saved/{r["id"]}">View →</a> <form method="post" action="/projects/{pid}/drawings/saved/{r["id"]}/delete" style="display:inline" onsubmit="return confirm(&quot;Permanently delete this saved quantity? This cannot be undone.&quot;)"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button type="submit" style="background:#9c3030">Delete</button></form></td></tr>' for r in records)
        return layout(request,'Drawing Workspace',f'''<span class="eyebrow">CIVORA / DRAWING WORKSPACE</span><h1>{esc(p['name'])} · Drawings</h1><p class="muted">Upload PDF/JPG/PNG/DXF in your Project page. Open here, calibrate a known dimension, measure, calculate, preview and optionally save.</p><div class="card"><h2>Upload drawing</h2><form action="/projects/{pid}/upload" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{csrf(request)}"><input type="file" name="file" accept=".pdf,.jpg,.jpeg,.png,.dxf" required><div class="actions"><button>Upload Drawing →</button></div></form><p class="hint">After upload, the drawing opens automatically in the viewer.</p></div><div class="card" style="margin-top:18px"><h2>Project drawings</h2><div class="scroll"><table><thead><tr><th>Drawing</th><th>Viewer</th></tr></thead><tbody>{links or '<tr><td colspan="2">No supported drawings uploaded yet</td></tr>'}</tbody></table></div></div><div class="card" style="margin-top:18px"><h2>Saved drawing takeoffs</h2><div class="scroll"><table><thead><tr><th>Drawing</th><th>Work</th><th>Result</th></tr></thead><tbody>{saved or '<tr><td colspan="3">Nothing saved yet</td></tr>'}</tbody></table></div><div class="actions"><a class="primary" href="/projects/{pid}/drawings/boq">Consolidated BOQ →</a><a href="/projects/{pid}">← Project / Upload</a></div></div>''')

    @app.get('/projects/{pid}/drawings/{fid}/auto')
    def auto_form(request:Request,pid:str,fid:str):
        r,path=drawing_file(request,pid,fid)
        detected=''
        initial_length=10;initial_width=5
        if path.suffix.lower()=='.dxf':
            try:
                info=inspect_dxf(path)
                if 'error' in info: detected=f'<p class="hint">{esc(info["error"])}</p>'
                else:
                    initial_length=round(info['length'],3);initial_width=round(info['width'],3)
                    layer_rows=''.join(f'<tr><td>{esc(layer)}</td><td>{v["segments"]}</td><td>{v["length"]:.2f} m</td></tr>' for layer,v in list(info['layers'].items())[:30])
                    detected=f'<div class="card"><h2>Extracted DXF geometry · verify before calculation</h2><p>Candidate extent: <b>{initial_length:.3f} × {initial_width:.3f} m</b> · {info["segments"]} segments</p><div class="scroll"><table><tr><th>CAD layer</th><th>Segments</th><th>Combined line length</th></tr>{layer_rows}</table></div><p class="hint">Layer line lengths may include room edges, annotations, repeated wall faces and openings. Not automatically classified as walls. Confirm plan dimensions and wall count.</p></div>'
            except Exception as ex:detected=f'<p class="hint">DXF inspection unavailable: {esc(str(ex)[:180])}</p>'
        return layout(request,'Multi-work Quantity',f'''<span class="eyebrow">DRAWING · MULTI-WORK QUANTITY</span><h1>{esc(r['original_name'])}</h1><p class="muted">One calculation for all work types after confirming measurements. DXF geometry is extracted as candidate dimensions and CAD layer totals. Image/PDF/sketch recognition and door/window classification require verification; no unsupported AI detection is claimed.</p>{detected}<div class="card form"><form method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><label>Room / plan length (m)</label><input type="number" name="length" min="0.01" max="10000" step="any" value="{initial_length}" required><label>Room / plan width (m)</label><input type="number" name="width" min="0.01" max="10000" step="any" value="{initial_width}" required><label>Wall height (m)</label><input type="number" name="height" min="0.1" max="100" step="any" value="3" required><label>Number of walls to include (1–4)</label><input type="number" name="walls" min="1" max="4" step="1" value="4" required><label>Wall thickness (m)</label><input type="number" name="wall_thickness" min="0.05" max="1" step="any" value="0.23" required><label>Total door/window openings area (m²)</label><input type="number" name="openings" min="0" max="100000" step="any" value="0" required><label>Kitchen wall tile length (m)</label><input type="number" name="kitchen_tile_length" min="0" max="10000" step="any" value="0"><label>Kitchen wall tile height (m)</label><input type="number" name="kitchen_tile_height" min="0" max="100" step="any" value="0.6"><label>Kitchen wall tile openings (m²)</label><input type="number" name="kitchen_tile_openings" min="0" max="10000" step="any" value="0"><label>Concrete supply mode</label><select name="rcc_mode"><option value="rmc">RMC (concrete volume)</option><option value="site">Site mix (illustrative M20 nominal materials)</option><option value="both">Compare both options</option></select><label>Slab thickness (m)</label><input type="number" name="slab_thickness" min="0.05" max="2" step="any" value="0.15" required><label>Wastage (%)</label><input type="number" name="waste" min="0" max="30" step="any" value="5" required><div class="actions"><button>Calculate all work quantities →</button><a href="/projects/{pid}/drawings/{fid}">← Manual polygon selection</a></div></form></div><p class="hint">For exact BBS upload approved reinforcement details; no automatic bar schedule is inferred from a floor plan.</p>''')

    @app.post('/projects/{pid}/drawings/{fid}/auto')
    def auto_report(request:Request,pid:str,fid:str,length:float=Form(...),width:float=Form(...),height:float=Form(...),walls:int=Form(...),wall_thickness:float=Form(...),openings:float=Form(0),slab_thickness:float=Form(...),waste:float=Form(5),kitchen_tile_length:float=Form(0),kitchen_tile_height:float=Form(.6),kitchen_tile_openings:float=Form(0),rcc_mode:str=Form("rmc"),csrf_token:str=Form(...)):
        r,path=drawing_file(request,pid,fid);check_csrf(request,csrf_token)
        L=finite(length,.01,1e4);W=finite(width,.01,1e4);H=finite(height,.1,100);T=finite(wall_thickness,.05,1);S=finite(slab_thickness,.05,2);O=finite(openings,0,1e6);finite(waste,0,30)
        if walls not in (1,2,3,4):raise HTTPException(400,'Walls must be 1–4')
        # First two walls length L, next two width W; partial walls are user-selected approximation.
        lengths=[L,L,W,W][:walls];gross=sum(lengths)*H
        if O>=gross:raise HTTPException(400,'Openings must be less than gross wall area')
        wall_area=gross-O;floor=L*W
        KL=finite(kitchen_tile_length,0,1e4);KH=finite(kitchen_tile_height,0,100);KO=finite(kitchen_tile_openings,0,1e4)
        kitchen_area=max(0.,KL*KH-KO)
        if rcc_mode not in ('rmc','site','both'):raise HTTPException(400,'Invalid RCC supply mode')
        plans=[('brickwork',wall_area,T,'Wall area minus openings'),('plaster',2*wall_area,.012,'Both wall faces; openings deducted; reveals not included'),('painting',2*wall_area,.001,'Both wall faces; opening deductions'),('flooring',floor,.01,'Floor footprint'),('wall_tiling',kitchen_area,.01,'Kitchen wall tiles; confirmed length × height less openings'),('rcc',floor,S,'Slab footprint; structural details not inferred'),('pcc',floor,.1,'Illustrative 100 mm PCC only'),('shuttering',floor,.01,'Slab soffit only; edges excluded'),('waterproofing',floor,.001,'Slab footprint'),('screed',floor,.05,'Illustrative 50 mm screed')]
        rows=[];errors=[]
        for work,area,depth,basis in plans:
            if work=='wall_tiling' and kitchen_area<=0:continue
            try:
                result=takeoff(work=('flooring' if work=='wall_tiling' else work),length=area,width=1,depth=depth,unit='m',waste=waste,rcc_mode=('site' if work=='rcc' and rcc_mode=='site' else 'rmc'),rcc_grade='M20',rcc_site_method='nominal',rcc_nominal_ratio='1:1.5:3')
                material='; '.join(f'{esc(str(x["material"]))}: {x["quantity"]:,.2f} {esc(str(x["unit"]))}' for x in result['items'])
                rows.append(f'<tr><td>{esc(('Kitchen wall tiles' if work=='wall_tiling' else WORKS[work]))}</td><td>{area:,.2f} m²</td><td>{depth:.3f} m</td><td>{material}</td><td>{esc(basis)}</td></tr>')
            except (ValueError,KeyError) as ex:errors.append(f'{work}: {ex}')
        if rcc_mode=='both':
            try:
                site=takeoff(work='rcc',length=floor,width=1,depth=S,unit='m',waste=waste,rcc_mode='site',rcc_grade='M20',rcc_site_method='nominal',rcc_nominal_ratio='1:1.5:3')
                materials='; '.join(f'{esc(str(x["material"]))}: {x["quantity"]:,.2f} {esc(str(x["unit"]))}' for x in site['items'])
                rows.append(f'<tr><td>RCC site mix · comparison</td><td>{floor:,.2f} m²</td><td>{S:.3f} m</td><td>{materials}</td><td>Illustrative nominal M20; engineering mix design required</td></tr>')
            except (ValueError,KeyError) as ex:errors.append(f'RCC site comparison: {ex}')
        warning=''.join(f'<p class="hint">{esc(x)}</p>' for x in errors)
        return layout(request,'Multi-work Preview',f'''<span class="eyebrow">ESTIMATE ONLY · NOT SAVED</span><h1>Multi-work Quantity Preview</h1><p>Floor area: <b>{floor:,.3f} m²</b> · Wall count: <b>{walls}</b> · Gross wall face: <b>{gross:,.3f} m²</b> · Openings: <b>{O:,.3f} m²</b> · Net wall face: <b>{wall_area:,.3f} m²</b></p><div class="card"><div class="scroll"><table><thead><tr><th>Work</th><th>Area</th><th>Depth</th><th>Materials</th><th>Basis / limitation</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>{warning}<p class="hint">DXF candidate dimensions (where available) and USER-CONFIRMED values, not validated AI room/wall detection. This is an indicative takeoff, not a structural design or exact BBS. No quantities were saved.</p><div class="actions"><a class="primary" href="/projects/{pid}/drawings/{fid}/auto">← Edit dimensions</a><a href="/projects/{pid}/drawings/{fid}">Manual selection →</a></div>''')


    @app.get('/projects/{pid}/drawings/{fid}/adaptive')
    def adaptive_form(request:Request,pid:str,fid:str):
        r,path=drawing_file(request,pid,fid)
        from adaptive_analysis import inspect_document, adaptive_form_html
        report=inspect_document(path)
        return layout(request,'Adaptive Drawing Analysis',adaptive_form_html(pid,fid,r['original_name'],report,csrf(request),esc))

    @app.post('/projects/{pid}/drawings/{fid}/adaptive')
    async def adaptive_report(request:Request,pid:str,fid:str):
        r,path=drawing_file(request,pid,fid)
        data=await request.form()
        check_csrf(request,str(data.get('csrf_token','')))
        from adaptive_analysis import inspect_document, adaptive_report_html
        report=inspect_document(path)
        return layout(request,'Adaptive Material BOQ',adaptive_report_html(pid,fid,r['original_name'],report,data,takeoff,esc))

    @app.get('/projects/{pid}/drawings/{fid}/residential')
    def residential_form(request:Request,pid:str,fid:str):
        r,path=drawing_file(request,pid,fid)
        def inp(key,title,value,step='any'):
            return f'<label>{esc(title)}</label><input name="{key}" type="number" min="0" max="100000" step="{step}" value="{value}" required>'
        fields=[('slab_sqft','Covered/slab area (sq.ft) · from supplied plan',1137.5),('floor_sqft','Floor/plinth area (sq.ft) · from supplied plan',1080),('outer_perimeter_ft','Outer wall centerline perimeter (ft) · provisional',130),('inner_wall_length_ft','Interior wall total centerline length (ft) · provisional',145),('wall_height_ft','Wall height (ft)',10),('ext_thickness_in','External wall thickness (in)',9),('int_thickness_in','Internal wall thickness (in)',4.5),('main_doors','Main doors count',1),('internal_doors','Internal doors count',5),('toilet_doors','Toilet doors count',4),('windows','Windows count',6),('vents','Ventilators count',4),('slab_thickness_mm','RCC slab thickness (mm)',125),('floor_tile_waste','Tile wastage (%)',5),('toilet_tile_height_ft','Toilet wall tile height (ft)',7),('toilet_wall_perimeter_ft','Combined toilet interior perimeter (ft) · provisional',80),('kitchen_tile_length_ft','Kitchen backsplash length (ft) · provisional',12),('kitchen_tile_height_ft','Kitchen backsplash height (ft)',2),('plaster_mm','Plaster thickness (mm)',12)]
        htmlfields=''.join(inp(*x) for x in fields)
        return layout(request,'Residential Material Schedule',f'''<span class="eyebrow">TEST MODE · RESIDENTIAL DRAWING</span><h1>{esc(r['original_name'])} · Complete Materials</h1><p class="muted">Pre-filled from the shared first-floor plan and editable test assumptions. This page does NOT claim image recognition or verified wall lengths. Confirm quantities before use.</p><div class="card form"><form method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}">{htmlfields}<label>RCC concrete supply</label><select name="rcc_mode"><option value="both">Show RMC and illustrative site mix</option><option value="rmc">RMC only</option><option value="site">Site mix only</option></select><div class="actions"><button>Generate complete material schedule →</button><a href="/projects/{pid}/drawings/{fid}">← Viewer</a></div></form></div>''')

    @app.post('/projects/{pid}/drawings/{fid}/residential')
    async def residential_report(request:Request,pid:str,fid:str):
        r,path=drawing_file(request,pid,fid)
        data=await request.form();check_csrf(request,str(data.get('csrf_token','')))
        keys=['slab_sqft','floor_sqft','outer_perimeter_ft','inner_wall_length_ft','wall_height_ft','ext_thickness_in','int_thickness_in','main_doors','internal_doors','toilet_doors','windows','vents','slab_thickness_mm','floor_tile_waste','toilet_tile_height_ft','toilet_wall_perimeter_ft','kitchen_tile_length_ft','kitchen_tile_height_ft','plaster_mm']
        try:
            x={k:finite(data[k],0,100000) for k in keys}
            if x['slab_sqft']<=0 or x['floor_sqft']<=0 or x['wall_height_ft']<=0 or x['slab_thickness_mm']<=0:raise ValueError('Area, height and slab thickness must be positive')
            mode=str(data.get('rcc_mode','both'))
            if mode not in ('rmc','site','both'):raise ValueError('Invalid RCC supply mode')
        except (KeyError,ValueError,TypeError) as ex:raise HTTPException(400,f'Invalid test inputs: {ex}')
        ft=.3048; sqft=ft*ft
        # Opening sizes are provisional, NOT image-detected.
        opening_sqft=(x['main_doors']*3.5*7+x['internal_doors']*3*7+x['toilet_doors']*2.5*7+x['windows']*4*4+x['vents']*2*1.5)
        wall_gross=(x['outer_perimeter_ft']+x['inner_wall_length_ft'])*x['wall_height_ft']*sqft
        ext_gross=x['outer_perimeter_ft']*x['wall_height_ft']*sqft
        int_gross=x['inner_wall_length_ft']*x['wall_height_ft']*sqft
        # Distribute openings by wall category based on provisional door/window categories.
        ext_open=(x['main_doors']*3.5*7+x['windows']*4*4+x['vents']*2*1.5)*sqft
        int_open=(x['internal_doors']*3*7+x['toilet_doors']*2.5*7)*sqft
        ext_net=max(0,ext_gross-ext_open);int_net=max(0,int_gross-int_open)
        if ext_open>ext_gross or int_open>int_gross:raise HTTPException(400,'Openings exceed gross wall area; check dimensions and counts')
        wall_net=ext_net+int_net;floor=x['floor_sqft']*sqft;slab=x['slab_sqft']*sqft
        slab_depth=x['slab_thickness_mm']/1000;waste=x['floor_tile_waste']
        toilet_tiling=max(0,(x['toilet_wall_perimeter_ft']*x['toilet_tile_height_ft']-x['toilet_doors']*2.5*min(7,x['toilet_tile_height_ft']))*sqft)
        kitchen_tiling=x['kitchen_tile_length_ft']*x['kitchen_tile_height_ft']*sqft
        # Separate plaster internal/external surfaces, minus tiled area to avoid double counting finish.
        # v3.7.0: external walls are plastered on BOTH faces (outside + inside), partitions on both faces
        plaster_area=max(0,2*ext_net+2*int_net-toilet_tiling-kitchen_tiling)
        paint_area=plaster_area
        rows=[];warnings=[]
        def line(title,qty,unit,basis,materials=''):
            rows.append(f'<tr><td>{esc(title)}</td><td>{qty:,.2f} {esc(unit)}</td><td>{esc(materials)}</td><td>{esc(basis)}</td></tr>')
        def run(title,work,area,depth,basis,kwargs=None):
            if area<=0:return
            try:
                args=dict(work=work,length=area,width=1,depth=depth,unit='m',waste=5,rcc_mode='rmc',rcc_grade='M20',rcc_site_method='nominal',rcc_nominal_ratio='1:1.5:3')
                if kwargs:args.update(kwargs)
                result=takeoff(**args)
                materials='; '.join(f'{item["material"]}: {item["quantity"]:,.2f} {item["unit"]}' for item in result['items'])
                line(title,area,'m²',basis,materials)
            except (KeyError,ValueError,TypeError) as ex:warnings.append(f'{title}: {ex}')
        run('External 9-inch brick masonry','brickwork',ext_net,x['ext_thickness_in']*.0254,'Outer wall length and opening sizes are provisional')
        run('Internal 4.5-inch brick masonry','brickwork',int_net,x['int_thickness_in']*.0254,'Internal wall length and door count are provisional')
        run('Wall plaster','plaster',plaster_area,x['plaster_mm']/1000,'External walls both faces + internal walls both faces, less tiled surfaces')
        run('Wall painting','painting',paint_area,.001,'Provisional plastered wall faces only')
        run('Floor tiles 2×2 ft','flooring',floor,.01,'Floor area from drawing; tile size assumed')
        run('Toilet wall tiles 1×1 ft','flooring',toilet_tiling,.01,'Tile height/perimeter assumed; door openings deducted')
        run('Kitchen wall tiles 1×1 ft','flooring',kitchen_tiling,.01,'Backsplash length/height assumed')
        run('RCC slab – RMC','rcc',slab,slab_depth,'Slab-only concrete volume; beams/columns excluded',{'rcc_mode':'rmc'}) if mode in ('rmc','both') else None
        run('RCC slab – site mix (illustrative)','rcc',slab,slab_depth,'Illustrative nominal ratio, not approved structural mix',{'rcc_mode':'site'}) if mode in ('site','both') else None
        run('Slab formwork soffit','shuttering',slab,.01,'Slab underside only; beam sides/edges excluded')
        run('Floor screed (50 mm test)','screed',floor,.05,'Optional work; do not add if not in project scope')
        # Explicit tile count based on requested sizes, waste included
        floor_tiles=math.ceil(floor*(1+waste/100)/(4*sqft));toilet_tiles=math.ceil(toilet_tiling*(1+waste/100)/sqft);kitchen_tiles=math.ceil(kitchen_tiling*(1+waste/100)/sqft)
        line('Floor tile pieces · 2×2 ft',floor_tiles,'Nos',f'{waste:g}% wastage; no layout optimization')
        line('Toilet wall tile pieces · 1×1 ft',toilet_tiles,'Nos',f'{waste:g}% wastage; openings deducted')
        line('Kitchen wall tile pieces · 1×1 ft',kitchen_tiles,'Nos',f'{waste:g}% wastage')
        errors=''.join(f'<p class="hint">{esc(w)}</p>' for w in warnings)
        return layout(request,'Residential Quantity Preview',f'''<span class="eyebrow">PRELIMINARY · NOT SAVED · TEST ONLY</span><h1>Residential Complete Material Schedule</h1><p><b>{esc(r['original_name'])}</b> · Slab: {slab:.2f} m² · Floor: {floor:.2f} m² · Net wall faces: {wall_net:.2f} m² · Openings: {opening_sqft*sqft:.2f} m²</p><div class="card"><div class="scroll"><table><thead><tr><th>Work</th><th>Measured/assumed quantity</th><th>Materials from takeoff engine</th><th>Basis</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>{errors}<p class="hint">TEST ASSUMPTIONS: wall lengths, opening counts, tile coverage and thicknesses were entered or defaulted, not detected from the image. Masonry/plaster assumptions and nominal site mix need professional verification. Roof reinforcement/BBS cannot be determined from this architectural floor plan. No structural design or final quote is implied.</p><div class="actions"><a class="primary" href="/projects/{pid}/drawings/{fid}/residential">← Edit test values</a><a href="/projects/{pid}/drawings/{fid}">Viewer →</a></div>''')

    @app.get('/projects/{pid}/drawings/{fid}/media')
    def drawing_media(request:Request,pid:str,fid:str,page:int=0):
        r,path=drawing_file(request,pid,fid);ext=path.suffix.lower()
        if ext in ('.png','.jpg','.jpeg'):
            return Response(path.read_bytes(),media_type='image/png' if ext=='.png' else 'image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
        if ext=='.pdf':
            try:
                import fitz
                with fitz.open(str(path)) as doc:
                    if doc.needs_pass:raise HTTPException(400,'Password-protected PDF not supported')
                    if page<0 or page>=len(doc):raise HTTPException(404,'Page not found')
                    pix=doc[page].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
                    return Response(pix.tobytes('png'),media_type='image/png',headers={'Cache-Control':'private, no-store'})
            except HTTPException:raise
            except Exception as ex:raise HTTPException(400,f'PDF rendering failed: {str(ex)[:140]}')
        try:return Response(dxf_svg(path),media_type='image/svg+xml',headers={'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'",'Cache-Control':'private, no-store'})
        except Exception as ex:raise HTTPException(400,f'DXF preview failed: {type(ex).__name__}: {str(ex)[:180]}. Install ezdxf with requirements-drawing.txt')

    @app.get('/projects/{pid}/drawings/{fid}')
    def drawing_view(request:Request,pid:str,fid:str,page:int=0):
        r,path=drawing_file(request,pid,fid)
        count=1
        if path.suffix.lower()=='.pdf':
            try:
                import fitz
                with fitz.open(str(path)) as d:count=len(d)
            except Exception as ex:
                count=1  # Let viewer show dependency/render error rather than aborting page.
        if page<0 or page>=count:raise HTTPException(404,'Page not found')
        page_select=''.join(f'<option value="{i}" {"selected" if i==page else ""}>Page {i+1}</option>' for i in range(min(count,200)))
        work_opts=''.join(f'<option value="{esc(k)}">{esc(v)}</option>' for k,v in WORKS.items() if k!='steel')
        src=f'/projects/{pid}/drawings/{fid}/media?page={page}'
        body=f'''<span class="eyebrow">DRAWING → CALIBRATE → MEASURE → QUANTITY</span><h1>{esc(r['original_name'])}</h1><p class="muted">Manual point-based measurement. Set a known dimension first. Verify drawing revision, scale, and geometry before saving.</p>
<div class="grid" style="grid-template-columns:minmax(300px,2fr) minmax(290px,1fr);align-items:start"><div class="card" style="min-width:0"><div class="actions" style="margin-top:0"><label>Page <select id="page">{page_select}</select></label><button type="button" id="zoomout">− Zoom</button><button type="button" id="zoomin">＋ Zoom</button><button type="button" id="reset">Reset points</button></div><div id="viewport" style="overflow:auto;max-height:75vh;border:1px solid #c7d9e8;background:#dce7ef;margin-top:12px"><div id="drawing-stage" style="position:relative;display:inline-block;line-height:0;transform-origin:top left"><img id="drawing" src="{src}" alt="Drawing" style="max-width:none;display:block"/><svg id="overlay" xmlns="http://www.w3.org/2000/svg" style="position:absolute;left:0;top:0;width:100%;height:100%;cursor:crosshair;touch-action:none"></svg></div></div><p id="status" class="hint">Loading drawing…</p><p class="hint"><a href="{src}" target="_blank">Open rendered drawing directly ↗</a> (use this to diagnose blank previews)</p></div>
<div class="card"><h2>Drawing Intelligence v1.3 · Batch Review</h2><p class="hint">Review detected line and region candidates, confirm dimensions, and preview available work-wise quantities. No automatic saving.</p><a class="primary" href="/projects/{pid}/drawings/{fid}/intelligence">Open Drawing Intelligence →</a></div><div class="card"><h2>Drawing Recognition · Batch Review</h2><p class="hint">Identify possible enclosed regions in PDF, JPG, PNG, hand sketches or DXF; review scale and confirmed dimensions before combined material preview.</p><a class="primary" href="/projects/{pid}/drawings/{fid}/recognition">Open Recognition →</a></div><div class="card"><h2>Adaptive Drawing Analysis · Any Drawing</h2><p class="hint">Extract supported CAD/PDF annotations; ask for missing dimensions before preparing a work-wise BOQ. Image and sketch recognition requires manual confirmation.</p><a class="primary" href="/projects/{pid}/drawings/{fid}/adaptive">Analyze this drawing →</a></div><div class="card"><h2>Residential Drawing Test · Complete Material Schedule</h2><p class="hint">Sample plan preset: 1137.50 sq.ft slab, 1080 sq.ft plinth, 3 bedrooms, 4 toilets. This is a verified-input test preset, NOT automatic image recognition.</p><a class="primary" href="/projects/{pid}/drawings/{fid}/residential">Residential Material Schedule →</a></div><div class="card"><h2>Automatic multi-work estimate</h2><p class="hint">One-click all-work calculation after confirming room dimensions, wall count and openings. Full AI drawing recognition is not yet available.</p><a class="primary" href="/projects/{pid}/drawings/{fid}/auto">Multi-work Calculation →</a><h2>1. Calibrate scale</h2><p class="hint">Click two points on a dimension line, then enter its ACTUAL known length. PDF drawing scale labels alone are not reliable after printing/resizing.</p><button type="button" id="calmode">Select calibration points</button><label>Known length</label><input id="known" type="number" min="0.000001" step="any" value="1"><label>Known length unit</label><select id="unit"><option value="m">Metres</option><option value="ft">Feet</option><option value="mm">Millimetres</option></select><p id="calstatus" class="hint">Not calibrated</p><h2>2. Measure</h2><div class="actions"><button type="button" id="line">Length (2 points)</button><button type="button" id="rectangle">Rectangle (2 corners)</button><button type="button" id="polygon">Area (polygon)</button><button type="button" id="finish">Finish polygon</button></div><p id="measurestatus" class="hint">Choose a tool after calibration</p><h2>3. Quantity</h2><form id="calc" method="post" action="/projects/{pid}/drawings/{fid}/preview"><input type="hidden" name="csrf_token" value="{csrf(request)}"><input type="hidden" name="page" value="{page}"><input type="hidden" name="geometry_json" id="geometry_json"><label>Measurement source</label><select name="measurement_source" id="measurement_source"><option value="drawing">Drawing selection</option><option value="manual">Enter verified dimensions manually (no point selection)</option></select><div id="manual_dims" style="display:none"><p class="hint">Use drawing dimension annotations or approved structural schedule. This bypasses drawing click selection.</p><label>Measured length (m)</label><input name="manual_length" type="number" min="0.001" step="any" value="10"><label>Measured width (m)</label><input name="manual_width" type="number" min="0.001" step="any" value="5"></div><label>Work type</label><select name="work">{work_opts}</select><label>Width for line measurements (m)</label><input name="line_width" type="number" min="0.001" step="any" value="1"><label>Thickness / depth (m) — slab example 0.15 m</label><input name="depth" type="number" min="0.001" step="any" value="0.2"><label>Wastage (%)</label><input name="waste" type="number" min="0" max="30" step="any" value="5"><label>RCC supply mode</label><select name="rcc_mode"><option value="rmc">RMC (volume only)</option><option value="site">Site Mix – illustrative M20 1:1.5:3</option></select><p class="hint">For detailed RCC mix design and BBS use Material Takeoff. Drawing quantity uses selected geometry and default material specifications.</p><div class="actions"><button type="submit">Calculate & Preview →</button></div></form></div></div><div class="actions"><a href="/projects/{pid}/drawings">← All Drawings</a><a href="/projects/{pid}/drawings/boq">Saved Drawing BOQ →</a></div>
<script>
(()=>{{const img=document.getElementById('drawing'),svg=document.getElementById('overlay'),stage=document.getElementById('drawing-stage'),stat=document.getElementById('status'),calstat=document.getElementById('calstatus'),mstat=document.getElementById('measurestatus');let tool='cal',cal=[],pts=[],mode='',scale=1,finished=false;
const known=document.getElementById('known'),unit=document.getElementById('unit');
function point(e){{const r=svg.getBoundingClientRect();return [Math.max(0,Math.min(img.naturalWidth,(e.clientX-r.left)/r.width*img.naturalWidth)),Math.max(0,Math.min(img.naturalHeight,(e.clientY-r.top)/r.height*img.naturalHeight))]}}
function paint(){{svg.setAttribute('viewBox',`0 0 ${{img.naturalWidth}} ${{img.naturalHeight}}`);svg.replaceChildren();function draw(points,color,closed){{if(!points.length)return;const p=document.createElementNS('http://www.w3.org/2000/svg','polyline');p.setAttribute('points',points.map(x=>x.join(',')).join(' '));p.setAttribute('fill',closed?'#22c55e22':'none');p.setAttribute('stroke',color);p.setAttribute('stroke-width',Math.max(2,img.naturalWidth/600));if(closed)p.setAttribute('points',points.concat([points[0]]).map(x=>x.join(',')).join(' '));svg.appendChild(p);for(const x of points){{const c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('cx',x[0]);c.setAttribute('cy',x[1]);c.setAttribute('r',Math.max(3,img.naturalWidth/350));c.setAttribute('fill',color);svg.appendChild(c)}}}}draw(cal,'#ef4444',false);draw(pts,'#16a34a',finished&&mode==='area')}}
function calibrated(){{if(cal.length!==2)return false;const d=Math.hypot(cal[0][0]-cal[1][0],cal[0][1]-cal[1][1]);const n=Number(known.value),f={{m:1,ft:.3048,mm:.001}}[unit.value];if(d<2||!Number.isFinite(n)||n<=0)return false;calstat.textContent=`Calibrated: ${{(n*f/d).toPrecision(5)}} metres / image pixel`;return true}}
function measure(){{if(!calibrated()||pts.length<2)return;const px=Math.hypot(cal[0][0]-cal[1][0],cal[0][1]-cal[1][1]),factor=Number(known.value)*{{m:1,ft:.3048,mm:.001}}[unit.value]/px;if(mode==='length'&&pts.length===2)mstat.textContent=`Measured length: ${{(Math.hypot(pts[0][0]-pts[1][0],pts[0][1]-pts[1][1])*factor).toFixed(3)}} m`;if(mode==='rectangle'&&pts.length===2){{finished=true;measure();paint();return;}}if(mode==='area'&&pts.length>=3){{let a=0;for(let i=0;i<pts.length;i++){{let j=(i+1)%pts.length;a+=pts[i][0]*pts[j][1]-pts[j][0]*pts[i][1]}}mstat.textContent=`Measured area: ${{(Math.abs(a)/2*factor*factor).toFixed(3)}} m²`}}}}
svg.addEventListener('click',e=>{{if(!img.naturalWidth)return;const p=point(e);if(tool==='cal'){{if(cal.length===2)cal=[];cal.push(p);pts=[];finished=false;calibrated()}}else if(calibrated()&&!finished){{if(mode==='length'||mode==='rectangle'){{if(pts.length===2)pts=[];pts.push(p);if(pts.length===2)finished=true}}else if(pts.length<100)pts.push(p);measure()}}paint()}});
document.getElementById('calmode').onclick=()=>{{tool='cal';cal=[];pts=[];finished=false;calstat.textContent='Click two calibration points';paint()}};
document.getElementById('line').onclick=()=>{{if(!calibrated())return alert('Calibrate first');tool='measure';mode='length';pts=[];finished=false;mstat.textContent='Click start and end points';paint()}};
document.getElementById('rectangle').onclick=()=>{{if(!calibrated())return alert('Calibrate first');tool='measure';mode='rectangle';pts=[];finished=false;mstat.textContent='Click opposite two corners of slab / room';paint()}};
document.getElementById('polygon').onclick=()=>{{if(!calibrated())return alert('Calibrate first');tool='measure';mode='area';pts=[];finished=false;mstat.textContent='Click polygon corners then Finish';paint()}};
document.getElementById('finish').onclick=()=>{{if(mode==='rectangle'&&pts.length===2){{finished=true;measure();paint();return;}}if(mode==='area'&&pts.length>=3){{finished=true;measure();paint()}}else alert('Select at least three polygon corners')}};
document.getElementById('reset').onclick=()=>{{pts=[];finished=false;mstat.textContent='Measurement cleared';paint()}};
known.oninput=()=>{{calibrated();measure()}};unit.onchange=()=>{{calibrated();measure()}};
img.onload=()=>{{img.style.width=img.naturalWidth+'px';img.style.height=img.naturalHeight+'px';svg.setAttribute('viewBox',`0 0 ${{img.naturalWidth}} ${{img.naturalHeight}}`);stat.textContent=`Drawing image ${{img.naturalWidth}} × ${{img.naturalHeight}} px. Click two known-distance points.`;paint()}};img.onerror=async()=>{{let msg='Preview failed';try{{const r=await fetch(img.src);const t=await r.text();try{{msg=JSON.parse(t).detail||msg}}catch{{msg='Media HTTP '+r.status}}}}catch{{}}stat.textContent=msg+' — See server CMD logs';}};
function zoom(n){{scale=Math.max(.25,Math.min(4,scale*n));stage.style.zoom=String(scale)}}document.getElementById('zoomin').onclick=()=>zoom(1.25);document.getElementById('zoomout').onclick=()=>zoom(.8);
document.getElementById('page').onchange=e=>location.href=`/projects/{pid}/drawings/{fid}?page=${{encodeURIComponent(e.target.value)}}`;
document.getElementById('measurement_source').onchange=e=>{{document.getElementById('manual_dims').style.display=e.target.value==='manual'?'block':'none'}};
document.getElementById('calc').onsubmit=e=>{{if(document.getElementById('measurement_source').value==='manual')return;if(!calibrated()||!finished||mode==='area'&&pts.length<3||(mode==='length'||mode==='rectangle')&&pts.length!==2){{e.preventDefault();alert('Finish calibrated length or area measurement before calculating');return}}document.getElementById('geometry_json').value=JSON.stringify({{points:pts,calibration:cal,known_length:Number(known.value),unit:unit.value,mode:mode}})}};
}})();
</script>'''
        return layout(request,'Drawing Viewer',body)

    @app.post('/projects/{pid}/drawings/{fid}/preview')
    def drawing_preview(request:Request,pid:str,fid:str,geometry_json:str=Form(''),page:int=Form(0),work:str=Form(...),line_width:float=Form(1),depth:float=Form(.2),waste:float=Form(5),rcc_mode:str=Form('rmc'),measurement_source:str=Form('drawing'),manual_length:float=Form(10),manual_width:float=Form(5),csrf_token:str=Form(...)):
        drawing_file(request,pid,fid);check_csrf(request,csrf_token)
        if len(geometry_json)>12000:raise HTTPException(400,'Measurement too large')
        try:
            if measurement_source=='manual':
                ml=finite(manual_length,.001,1e5);mw=finite(manual_width,.001,1e5)
                g={'amount':ml*mw,'dimension':'m²','mode':'manual','points':[],'calibration':[],'known_length':0,'unit':'m','manual_length':ml,'manual_width':mw}
            elif measurement_source=='drawing':
                if not geometry_json.strip():
                    raise ValueError('Select drawing points and finish measurement, or choose Manual Dimensions.')
                g=measured_geometry(json.loads(geometry_json))
            else:raise ValueError('Invalid measurement source')
            finite(depth,.001,1000);finite(waste,0,30);finite(line_width,.001,1e5)
            if work not in WORKS or work=='steel':raise ValueError('Choose supported work; steel requires a BBS')
            if rcc_mode not in ('rmc','site'):raise ValueError('Invalid RCC mode')
            # Area measured directly; line measurements require an entered width.
            area=g['amount'] if g['dimension']=='m²' else g['amount']*line_width
            if area<=0:raise ValueError('Invalid area')
            result=takeoff(work=work,length=area,width=1,depth=depth,unit='m',waste=waste,rcc_mode=rcc_mode,rcc_grade='M20',rcc_site_method='nominal',rcc_nominal_ratio='1:1.5:3',joint=.004 if work=='blockwork' else .01,brick_length=.6 if work=='blockwork' else .19,brick_height=.2 if work=='blockwork' else .09,brick_width=.2 if work=='blockwork' else .09)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as ex:raise HTTPException(400,str(ex))
        data={'fid':fid,'pid':pid,'page':page,'geometry':g,'work':work,'line_width':line_width,'depth':depth,'waste':waste,'rcc_mode':rcc_mode,'result':result}
        request.session['pending_drawing']=data
        return RedirectResponse(f'/projects/{pid}/drawings/preview',303)

    def render_result(data):
        result=data['result'];rows=''.join(f'<tr><td>{html.escape(x["material"])}</td><td>{x["quantity"]:,.3f}</td><td>{html.escape(x["unit"])}</td><td>{html.escape(x["basis"])}</td></tr>' for x in result['items'])
        notes=''.join(f'<p class="hint">{html.escape(str(n))}</p>' for n in result.get('notes',[]))
        return f'''<div class="card"><p>Drawing measurement: <b>{data['geometry']['amount']:.3f} {data['geometry']['dimension']}</b> · Page {data['page']+1}</p><p>Computed work area: <b>{result['net_area_m2']:.3f} m²</b> · Volume: <b>{result['net_volume_m3']:.3f} m³</b></p><p>Work: <b>{html.escape(result['work'])}</b></p><div class="scroll"><table><thead><tr><th>Material</th><th>Qty</th><th>Unit</th><th>Assumption</th></tr></thead><tbody>{rows}</tbody></table></div>{notes}</div>'''

    @app.get('/projects/{pid}/drawings/preview')
    def preview_page(request:Request,pid:str):
        owned_project(request,pid);data=request.session.get('pending_drawing')
        if not data or data['pid']!=pid:return RedirectResponse(f'/projects/{pid}/drawings',303)
        return layout(request,'Drawing Quantity Preview',f'''<span class="eyebrow">NOT SAVED · DRAWING QUANTITY PREVIEW</span><h1>Review before saving</h1>{render_result(data)}<div class="actions"><form method="post" action="/projects/{pid}/drawings/save"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button>Save Drawing Quantity →</button></form><a href="/projects/{pid}/drawings/{data['fid']}?page={data['page']}">← Back without saving</a></div>''')

    @app.post('/projects/{pid}/drawings/save')
    def save_drawing(request:Request,pid:str,csrf_token:str=Form(...)):
        owned_project(request,pid);check_csrf(request,csrf_token)
        data=request.session.get('pending_drawing')
        if not data or data['pid']!=pid:raise HTTPException(400,'No pending drawing preview')
        drawing_file(request,pid,data['fid']);ident=str(uuid.uuid4())
        with db() as c:c.execute('INSERT INTO drawing_measurements VALUES(?,?,?,?,?,?,?,?)',(ident,pid,data['fid'],data['page'],data['work'],json.dumps({k:v for k,v in data.items() if k!='result'}),json.dumps(data['result']),int(time.time())))
        request.session.pop('pending_drawing',None)
        return RedirectResponse(f'/projects/{pid}/drawings/saved/{ident}',303)

    @app.get('/projects/{pid}/drawings/saved/{mid}')
    def saved_drawing(request:Request,pid:str,mid:str):
        owned_project(request,pid)
        with db() as c:r=c.execute('SELECT * FROM drawing_measurements WHERE id=? AND project_id=?',(mid,pid)).fetchone()
        if not r:raise HTTPException(404,'Saved drawing estimate not found')
        data=json.loads(r['measurement_json']);data['result']=json.loads(r['result_json'])
        return layout(request,'Saved Drawing Quantity',f'<span class="eyebrow">SAVED DRAWING QUANTITY</span><h1>Saved measurement</h1>{render_result(data)}<div class="actions"><a class="primary" href="/projects/{pid}/drawings/boq">BOQ →</a><a href="/projects/{pid}/drawings">All Drawings →</a><form method="post" action="/projects/{pid}/drawings/saved/{mid}/delete" onsubmit="return confirm(&quot;Permanently delete this saved quantity?&quot;)"><input type="hidden" name="csrf_token" value="{csrf(request)}"><button style="background:#9c3030">Delete permanently</button></form></div>')

    @app.post('/projects/{pid}/drawings/saved/{mid}/delete')
    def delete_saved_drawing(request:Request,pid:str,mid:str,csrf_token:str=Form(...)):
        owned_project(request,pid)
        check_csrf(request,csrf_token)
        with db() as c:
            r=c.execute('SELECT id FROM drawing_measurements WHERE id=? AND project_id=?',(mid,pid)).fetchone()
            if not r:raise HTTPException(404,'Saved drawing quantity not found')
            c.execute('DELETE FROM drawing_measurements WHERE id=? AND project_id=?',(mid,pid))
        return RedirectResponse(f'/projects/{pid}/drawings',303)

    def boq_rows(pid):
        with db() as c:rows=c.execute('SELECT * FROM drawing_measurements WHERE project_id=? ORDER BY created',(pid,)).fetchall()
        out=[]
        for r in rows:
            result=json.loads(r['result_json'])
            for item in result['items']:
                out.append((r['id'],r['work'],item['material'],float(item['quantity']),item['unit'],item['basis']))
        return out

    @app.get('/projects/{pid}/drawings/boq')
    def boq_page(request:Request,pid:str):
        p=owned_project(request,pid);rows=boq_rows(pid);totals={}
        for _,work,name,qty,unit,basis in rows:
            # Alternative quantities (e.g., cement kg and bags) are separate representations.
            key=(work,name,unit)
            totals[key]=totals.get(key,0)+qty
        trs=''.join(f'<tr><td>{esc(k[0])}</td><td>{esc(k[1])}</td><td>{v:,.3f}</td><td>{esc(k[2])}</td></tr>' for k,v in sorted(totals.items()))
        return layout(request,'Drawing BOQ',f'''<span class="eyebrow">SAVED DRAWING ESTIMATES ONLY</span><h1>{esc(p['name'])} · Drawing BOQ</h1><p class="hint">Aggregated by work + material + unit. Alternative quantities (cement kg and bags) are not additive; avoid duplicate purchasing. This is a preliminary material summary, not a priced BOQ.</p><div class="card"><div class="scroll"><table><thead><tr><th>Work</th><th>Material</th><th>Total</th><th>Unit</th></tr></thead><tbody>{trs or '<tr><td colspan="4">No saved drawing quantities yet</td></tr>'}</tbody></table></div><div class="actions"><a class="primary" href="/projects/{pid}/drawings/boq.csv">Export CSV →</a><a href="/projects/{pid}/drawings">← Drawings</a></div></div>''')

    @app.get('/projects/{pid}/drawings/boq.csv')
    def boq_csv(request:Request,pid:str):
        owned_project(request,pid);buf=io.StringIO();w=csv.writer(buf);w.writerow(['Measurement ID','Work','Material','Quantity','Unit','Basis']);w.writerows(boq_rows(pid))
        return Response('\ufeff'+buf.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="civora_drawing_boq.csv"'})

    # Static paths such as /preview, /boq and /saved must precede the {fid} viewer.
    drawing_routes=[r for r in app.router.routes if getattr(r,'path','').startswith('/projects/{pid}/drawings')]
    app.router.routes[:]=[r for r in app.router.routes if r not in drawing_routes]+sorted(drawing_routes,key=lambda r:(-sum(not x.startswith('{') for x in r.path.split('/')), -len(r.path.split('/'))))
