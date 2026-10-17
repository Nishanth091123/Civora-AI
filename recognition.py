"""Civora v1.2: image-based geometry candidates, NOT semantic architectural recognition."""
import io, math, re
from pathlib import Path
from fastapi import Request, Form, HTTPException
from fastapi.responses import Response

EXT={'.png','.jpg','.jpeg','.pdf','.dxf'}

def raster(path, page=0):
    import cv2, numpy as np
    ext=Path(path).suffix.lower()
    if ext=='.pdf':
        import fitz
        with fitz.open(str(path)) as doc:
            if not 0<=page<len(doc):raise ValueError('Invalid PDF page')
            pix=doc[page].get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False)
            raw=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3)
            arr=cv2.cvtColor(raw,cv2.COLOR_RGB2BGR)
    elif ext=='.dxf':
        import ezdxf
        doc=ezdxf.readfile(str(path));entities=[];pts=[]
        for e in doc.modelspace():
            try:
                typ=e.dxftype()
                if typ=='LINE':
                    a,b=e.dxf.start,e.dxf.end;v=[(a.x,a.y),(b.x,b.y)]
                elif typ=='LWPOLYLINE':v=[(p[0],p[1]) for p in e.get_points()]
                elif typ=='POLYLINE':v=[(p.dxf.location.x,p.dxf.location.y) for p in e.vertices]
                else:continue
                if len(v)<2 or len(v)>2000:continue
                entities.append((v,bool(getattr(e,'closed',False))));pts+=v
                if len(entities)>20000:break
            except (ValueError,AttributeError,TypeError):continue
        if not pts:raise ValueError('No supported DXF linework found')
        xx=[p[0] for p in pts];yy=[p[1] for p in pts];xmin,xmax=min(xx),max(xx);ymin,ymax=min(yy),max(yy)
        s=min(1300/max(xmax-xmin,1e-6),1300/max(ymax-ymin,1e-6),10**6)
        w=int((xmax-xmin)*s)+60;h=int((ymax-ymin)*s)+60
        if w*h>12_000_000:s*=math.sqrt(12_000_000/(w*h));w=int((xmax-xmin)*s)+60;h=int((ymax-ymin)*s)+60
        arr=np.full((max(h,100),max(w,100),3),255,np.uint8)
        for points,closed in entities:
            coords=np.array([[(x-xmin)*s+30,(ymax-y)*s+30] for x,y in points],dtype=np.int32)
            cv2.polylines(arr,[coords],closed,(30,30,30),2)
    else:
        arr=cv2.imread(str(path))
        if arr is None:raise ValueError('Image cannot be decoded')
    h,w=arr.shape[:2]
    if w*h>8_000_000:
        scale=math.sqrt(8_000_000/(w*h));arr=cv2.resize(arr,(max(1,int(w*scale)),max(1,int(h*scale))))
    return arr

def analyze_image(arr):
    import cv2
    h,w=arr.shape[:2]
    gray=cv2.cvtColor(arr,cv2.COLOR_BGR2GRAY)
    _,binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    # Close small gaps in floor-plan linework; do not assume contours are rooms.
    kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(3,3))
    binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,kernel,iterations=1)
    contours,_=cv2.findContours(binary,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for c in contours:
        x,y,cw,ch=cv2.boundingRect(c)
        area=cw*ch
        if area<max(1000,w*h*.002) or area>w*h*.72 or cw<25 or ch<25:continue
        actual=cv2.contourArea(c)
        if actual<100:continue
        # Near-rectangular boundaries are candidates only; text boxes can also match.
        approx=cv2.approxPolyDP(c,.025*cv2.arcLength(c,True),True)
        if not 4<=len(approx)<=12:continue
        score=actual/max(area,1)
        if not .025<=score<=1.05:continue
        candidates.append((x,y,cw,ch,round(score,3)))
    candidates.sort(key=lambda c:c[2]*c[3],reverse=True)
    kept=[]
    for c in candidates:
        x,y,cw,ch,_=c
        if any(abs(x-a)<12 and abs(y-b)<12 and abs(cw-ww)<18 and abs(ch-hh)<18 for a,b,ww,hh,_ in kept):continue
        kept.append(c)
        if len(kept)>=20:break
    return kept

def annotated_png(arr,candidates):
    import cv2
    output=arr.copy()
    for i,(x,y,w,h,_) in enumerate(candidates,1):
        cv2.rectangle(output,(x,y),(x+w,y+h),(0,125,255),2)
        cv2.putText(output,str(i),(x+4,y+19),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,80,220),2)
    ok,buf=cv2.imencode('.png',output)
    if not ok:raise ValueError('Image rendering failed')
    return bytes(buf)

def register_recognition(app,db,owned_project,csrf,check_csrf,layout,esc,FILES,takeoff):
    def source(request,pid,fid):
        owned_project(request,pid)
        with db() as c:r=c.execute('SELECT * FROM uploads WHERE id=? AND project_id=?',(fid,pid)).fetchone()
        if not r:raise HTTPException(404,'Drawing not found')
        p=FILES/r['stored_name']
        if p.suffix.lower() not in EXT or not p.is_file():raise HTTPException(400,'Unsupported drawing')
        return r,p
    def inspect(request,pid,fid,page):
        _,p=source(request,pid,fid)
        try:
            arr=raster(p,page)
            return arr,analyze_image(arr)
        except Exception as e:raise HTTPException(422,'Drawing analysis unavailable: '+str(e)[:180])
    @app.get('/projects/{pid}/drawings/{fid}/recognition/overlay')
    def overlay(request:Request,pid:str,fid:str,page:int=0):
        arr,candidates=inspect(request,pid,fid,page)
        return Response(annotated_png(arr,candidates),media_type='image/png',headers={'Cache-Control':'no-store'})
    @app.get('/projects/{pid}/drawings/{fid}/recognition')
    def review(request:Request,pid:str,fid:str,page:int=0):
        r,p=source(request,pid,fid)
        try:
            arr,found=inspect(request,pid,fid,page);w=arr.shape[1];h=arr.shape[0]
            boxes=''.join(f'<tr><td><input style="width:auto" type="checkbox" name="region" value="{i}" {"checked" if i==1 else ""}></td><td>Region {i}</td><td>{cw} × {ch} px</td><td>{x}, {y}</td></tr>' for i,(x,y,cw,ch,_) in enumerate(found,1))
            info=f'<p>Image resolution: {w} × {h} px · {len(found)} possible enclosed regions. <b>Orange rectangles are geometry candidates, not verified rooms.</b></p>'
            visual=f'<img style="max-width:100%;height:auto;border:1px solid #dce6ef" src="/projects/{pid}/drawings/{fid}/recognition/overlay?page={page}">'
        except HTTPException as e:
            found=[];boxes='';info=f'<p class="msg">{esc(e.detail)}. You can still enter verified quantities manually.</p>';visual=''
        inputs=[('floor','Confirmed total floor area (m²)',''),('slab','Confirmed RCC slab area (m²)',''),('wall','Confirmed total net masonry wall face (m²)',''),('wall_depth','Wall thickness (m)','0.23'),('plaster','Confirmed net plaster area (m²)',''),('paint','Confirmed net paint area (m²)',''),('wall_tile','Confirmed wall tile area (m²)',''),('slab_depth','Slab thickness (m)','0.125'),('scale','Scale (metres per pixel) — only for selected regions',''),('waste','Wastage (%)','5')]
        fields=''.join(f'<label>{esc(label)}</label><input name="{key}" type="number" min="0" step="any" value="{default}" placeholder="Optional">' for key,label,default in inputs)
        return layout(request,'AI Drawing Recognition',f'''<span class="eyebrow">CIVORA AI / RECOGNITION STAGE</span><h1>{esc(r['original_name'])}</h1><p class="muted">Batch review: inspect possible regions, confirm real dimensions, then generate all available work quantities in one preview. Nothing is auto-saved.</p><div class="card">{info}{visual}</div><div class="card" style="margin-top:18px"><h2>Recognized region candidates</h2><p class="hint">Select only real floor regions. Labels, title blocks and furniture may be falsely identified. Region areas need a verified drawing scale.</p><form method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><input type="hidden" name="page" value="{page}"><div class="scroll"><table><tr><th>Include</th><th>Candidate</th><th>Bounding box</th><th>Top-left</th></tr>{boxes or '<tr><td colspan="4">No enclosed candidates found; manual entries remain available.</td></tr>'}</table></div><label><input style="width:auto" type="checkbox" name="use_candidate_floor" value="yes"> I reviewed the selected regions and confirm their combined bounding-box area represents the floor area (requires scale)</label><h2 style="margin-top:20px">Optional confirmed values</h2><p class="hint">Leave unknown fields empty. Only calculable works appear in preview. Values are not guessed from another project.</p>{fields}<label>RCC supply</label><select name="mode"><option value="rmc">RMC</option><option value="site">Illustrative site mix</option><option value="both">Show both</option></select><div class="actions"><button type="submit">Generate Combined Quantity Preview →</button><a href="/projects/{pid}/drawings/{fid}">← Drawing Viewer</a></div></form></div>''')
    @app.post('/projects/{pid}/drawings/{fid}/recognition')
    async def result(request:Request,pid:str,fid:str):
        r,p=source(request,pid,fid)
        data=await request.form();check_csrf(request,str(data.get('csrf_token','')))
        def num(key):
            v=str(data.get(key,'')).strip()
            if not v:return None
            try:n=float(v)
            except ValueError:return None
            return n if math.isfinite(n) and 0<=n<=1e7 else None
        values={k:num(k) for k in ('floor','slab','wall','wall_depth','plaster','paint','wall_tile','slab_depth','scale','waste')}
        scale=values['scale'];selected=data.getlist('region');notes=[]
        if scale and selected:
            try:
                arr,found=inspect(request,pid,fid,int(data.get('page','0')))
                ids=set(int(v) for v in selected if v.isdigit());area=sum(w*h*scale*scale for i,(_,_,w,h,_) in enumerate(found,1) if i in ids)
                notes.append(f'Selected bounding-box candidate area: {area:.2f} m² (may overlap or include non-room regions).')
                if str(data.get('use_candidate_floor',''))=='yes' and values['floor'] is None and area>0:
                    values['floor']=area
                    notes.append('Floor area accepted from selected candidate bounding boxes after user confirmation.')
            except Exception as e:notes.append('Selected region calculation unavailable: '+str(e)[:100])
        rows=[];skipped=[]
        def job(label,work,area,depth,mode='rmc'):
            if area is None or area<=0 or depth is None or depth<=0:
                skipped.append(label);return
            try:
                res=takeoff(work=work,length=area,width=1,depth=depth,unit='m',waste=values['waste'] if values['waste'] is not None else 5,rcc_mode=mode,rcc_grade='M20',rcc_site_method='nominal',rcc_nominal_ratio='1:1.5:3')
                items='; '.join(f'{esc(i["material"])}: {float(i["quantity"]):,.2f} {esc(i["unit"])}' for i in res['items'])
                rows.append(f'<tr><td>{esc(label)}</td><td>{area:,.2f} m²</td><td>{items}</td></tr>')
            except (ValueError,KeyError,TypeError) as e:skipped.append(label+' ('+str(e)[:90]+')')
        job('Masonry','brickwork',values['wall'],values['wall_depth'])
        job('Plaster','plaster',values['plaster'],.012)
        job('Painting','painting',values['paint'],.001)
        job('Floor tiles 2 × 2 ft','flooring',values['floor'],.01)
        job('Wall tiles 1 × 1 ft','flooring',values['wall_tile'],.01)
        job('Floor screed','screed',values['floor'],.05)
        job('Slab formwork','shuttering',values['slab'],.01)
        mode=str(data.get('mode','rmc'))
        if mode in ('rmc','both'):job('RCC slab – RMC','rcc',values['slab'],values['slab_depth'])
        if mode in ('site','both'):job('RCC slab – indicative site mix','rcc',values['slab'],values['slab_depth'],'site')
        if values['floor']:
            pieces=math.ceil(values['floor']*(1+(values['waste'] or 0)/100)/(.6096**2))
            rows.append(f'<tr><td>Floor tiles – pieces</td><td>{values["floor"]:.2f} m²</td><td>{pieces} Nos, 2 × 2 ft, rectangular area approximation</td></tr>')
        if values['wall_tile']:
            pieces=math.ceil(values['wall_tile']*(1+(values['waste'] or 0)/100)/(.3048**2))
            rows.append(f'<tr><td>Wall tiles – pieces</td><td>{values["wall_tile"]:.2f} m²</td><td>{pieces} Nos, 1 × 1 ft, rectangular area approximation</td></tr>')
        notes_html=''.join('<p class="hint">'+esc(n)+'</p>' for n in notes)
        skipped_html=', '.join(esc(x) for x in skipped)
        return layout(request,'Recognition BOQ Preview',f'''<span class="eyebrow">NOT SAVED · REVIEW REQUIRED</span><h1>Drawing Recognition – Combined Quantity Preview</h1><p>{esc(r['original_name'])}</p><div class="card"><div class="scroll"><table><tr><th>Work</th><th>Basis</th><th>Material quantities</th></tr>{''.join(rows) or '<tr><td colspan="3">No verified quantities supplied. Enter at least one applicable area to calculate.</td></tr>'}</table></div></div>{notes_html}<p class="hint">Skipped (missing inputs): {skipped_html or 'None'}</p><p class="hint">Image analysis provides region candidates only. It does not verify rooms, openings, structural members or BBS. Concrete quantities require approved structural specifications. No records were saved.</p><a class="primary" href="/projects/{pid}/drawings/{fid}/recognition">← Edit and review</a>''')
