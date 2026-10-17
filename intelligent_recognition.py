# Civora v1.3.0: conservative wall-line / room-region candidates with review-first quantities.
import math,io,json,base64
from pathlib import Path
from fastapi import Request,HTTPException
from fastapi.responses import Response
from recognition import raster,analyze_image
from drawing_schedule import extract
from measurement import BASES, normalise_basis, wall_faces, grid_partition_length

EXT={'.pdf','.png','.jpg','.jpeg','.dxf'}

def detect(arr):
    import cv2,numpy as np
    h,w=arr.shape[:2]
    gray=cv2.cvtColor(arr,cv2.COLOR_BGR2GRAY)
    _,ink=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    # Horizontal/vertical line candidates only: annotation lines can be mistaken for walls.
    min_len=max(25,int(min(h,w)*.065))
    raw=cv2.HoughLinesP(ink,1,math.pi/180,threshold=max(25,min_len//2),minLineLength=min_len,maxLineGap=6)
    lines=[]
    if raw is not None:
        for x1,y1,x2,y2 in np.asarray(raw).reshape(-1,4):
            dx,dy=int(x2-x1),int(y2-y1)
            if abs(dx)>=abs(dy)*5:orientation='horizontal'
            elif abs(dy)>=abs(dx)*5:orientation='vertical'
            else:continue
            length=math.hypot(dx,dy)
            if length>=min_len:lines.append((int(x1),int(y1),int(x2),int(y2),round(length,1),orientation))
    # Merge near-duplicate detections from thick lines. Do not merge disconnected wall parts.
    lines.sort(key=lambda a:a[4],reverse=True)
    chosen=[]
    for item in lines:
        x1,y1,x2,y2,_,o=item
        mid=((x1+x2)/2,(y1+y2)/2)
        if any(o==z[5] and abs(mid[0]-(z[0]+z[2])/2)<8 and abs(mid[1]-(z[1]+z[3])/2)<8 and abs(item[4]-z[4])<25 for z in chosen):continue
        chosen.append(item)
        if len(chosen)>=80:break
    regions=analyze_image(arr)[:20]
    return {'lines':chosen,'regions':regions,'width':w,'height':h}

def overlay_image(arr,result):
    import cv2
    image=arr.copy()
    for i,(x,y,w,h,_) in enumerate(result['regions'],1):
        cv2.rectangle(image,(x,y),(x+w,y+h),(0,130,240),2)
        cv2.putText(image,'R'+str(i),(x+3,y+17),cv2.FONT_HERSHEY_SIMPLEX,.52,(0,90,180),2)
    for i,(x1,y1,x2,y2,_,_) in enumerate(result['lines'][:40],1):
        cv2.line(image,(x1,y1),(x2,y2),(40,165,50),2)
        if i<=20:cv2.putText(image,'L'+str(i),(x1,y1),cv2.FONT_HERSHEY_SIMPLEX,.42,(20,115,30),1)
    ok,buf=cv2.imencode('.png',image)
    if not ok:raise ValueError('Overlay render failed')
    return bytes(buf)

def calculate(values, selected_regions, selected_lines, detected, takeoff):
    """Calculate supported quantities from confirmed or annotation-derived inputs.
    Never interpret Hough lines as real walls without explicit selection and scale.
    """
    scale=values.get('scale');height=values.get('height');thickness=values.get('wall_thickness')
    opening=values.get('opening_area') or 0
    floor=values.get('floor_area');slab=values.get('slab_area')
    notes=[];results=[];skipped=[];breakdown=[]
    if floor is None and scale and selected_regions:
        boxes=[detected['regions'][i] for i in selected_regions if 0<=i<len(detected['regions'])]
        if boxes:
            floor=union_area([(x,y,w,h) for x,y,w,h,_ in boxes])*scale*scale
            notes.append('Floor area estimated from union of selected bounding boxes; verify true room outlines.')
    length=values.get('wall_length')
    if length is None and scale and selected_lines:
        length=sum(detected['lines'][i][4] for i in selected_lines if 0<=i<len(detected['lines']))*scale
        notes.append('Wall length estimated from selected line candidates; verify duplicate wall faces.')
    wall_gross=length*height if length and height else None
    wall_area=None
    if wall_gross is not None:
        if opening>wall_gross:
            notes.append('Opening deduction exceeds gross wall area; masonry skipped.')
        else:wall_area=wall_gross-opening
    if slab is None and floor is not None and values.get('use_floor_for_slab'):
        slab=floor;notes.append('Slab area taken from floor area; verify slab boundary.')
    def run(label,work,area,depth,mode='rmc'):
        if area is None or area<=0 or depth is None or depth<=0:
            skipped.append(label);return
        try:
            res=takeoff(work=work,length=area,width=1,depth=depth,unit='m',waste=values.get('waste',5),rcc_mode=mode,rcc_grade='M20',rcc_site_method='nominal',rcc_nominal_ratio='1:1.5:3')
            results.append((label,area,res['items']))
        except Exception as e:skipped.append(label+': '+str(e)[:90])
    # External perimeter is an indicative geometric estimate from annotated outside dimensions.
    # Deduct only external-classified openings; never deduct internal doors from outer walls.
    ext_length=values.get('overall_length');ext_width=values.get('overall_width')
    ext_opening=values.get('external_opening_area')
    # v2.4.1: explicit measurement basis. Masonry follows the chosen basis;
    # external plaster is always the outer face (the surface actually plastered).
    basis=normalise_basis(values.get('measurement_basis'))
    if wall_area is None and ext_length and ext_width and height and thickness and ext_opening is not None:
        try:
            outer=wall_faces(ext_length,ext_width,thickness,height,ext_opening,'external')
            faces=outer if basis=='external' else wall_faces(ext_length,ext_width,thickness,height,ext_opening,basis)
        except ValueError as ex:
            outer=faces=None;notes.append('External walls skipped: '+str(ex))
        if faces:
            label='External masonry – indicative (net openings)' if basis=='external' else f'External masonry – indicative (net openings, {faces["basis_label"].lower()})'
            run(label,'brickwork',faces['net'],thickness)
            run('External plaster – indicative (outer face)','plaster',outer['net'],values.get('external_plaster_thickness') or .015)
            breakdown.extend([('External perimeter (outer dimensions)',outer['perimeter'],'m'),
                              ('External wall gross face',outer['gross'],'m²'),
                              ('External opening deduction (assumed placement)',ext_opening,'m²'),
                              ('External wall net face (indicative)',outer['net'],'m²')])
            if basis!='external':
                breakdown.extend([(f'Masonry perimeter – {faces["basis_label"]}',faces['perimeter'],'m'),
                                  (f'Masonry gross face – {faces["basis_label"]}',faces['gross'],'m²'),
                                  (f'Masonry net face – {faces["basis_label"]}',faces['net'],'m²')])
            notes.append(f'Measurement basis for external masonry: {faces["basis_label"]}. Perimeter = {faces["formula"]}. Face: {faces["face_formula"]}.')
            notes.append(f'External plaster measured on the external face: {outer["face_formula"]}.')
            notes.append('Window/vent/main-door placement on external walls is assumed from the schedule and requires review. Internal partitions are calculated separately only when a provisional or confirmed length is available.')
    # v1.6: optional, transparently labelled room-grid estimate. This is NOT
    # a measured centreline or a substitute for a dimensioned partition plan.
    ilen=values.get('internal_wall_length')
    ithick=values.get('internal_thickness')
    iopening=values.get('internal_opening_area')
    if ilen and ithick and height and iopening is not None:
        igross=ilen*height
        if iopening>igross:
            notes.append('Internal opening area exceeds estimated internal wall face; internal work skipped.')
        else:
            inet=igross-iopening
            run('Internal masonry – provisional (net doors)','brickwork',inet,ithick)
            breakdown.extend([('Internal wall centreline – provisional',ilen,'m'),
                              ('Internal wall gross face – provisional',igross,'m²'),
                              ('Internal door deduction',iopening,'m²'),
                              ('Internal wall net face – provisional',inet,'m²')])
            ipthick=values.get('internal_plaster_thickness') or .012
            # Both partition faces, after deducting door openings on both sides.
            run('Internal partition plaster – both faces, provisional','plaster',2*inet,ipthick)
            run('Internal partition painting – both faces, provisional','painting',2*inet,.001)
            breakdown.append(('Internal plaster/paint coverage – provisional',2*inet,'m²'))
            if values.get('internal_grid_warning'):
                notes.append(values['internal_grid_warning'])
                notes.append('Internal partition lengths are inferred from a regular room grid, NOT measured wall geometry. Verify partition positions, openings and finishes before use.')
            else:
                notes.append('Internal partition length as entered by the user; verify against the drawing.')
    elif values.get('internal_grid_warning'):
        notes.append(values['internal_grid_warning'])
    run('Brick masonry (net of openings)','brickwork',wall_area,thickness)
    plaster=values.get('plaster_area')
    paint=values.get('paint_area')
    if plaster is None and wall_area is not None and values.get('finish_faces'):
        plaster=wall_area*values['finish_faces'];notes.append('Plaster uses net masonry wall area × confirmed finish faces.')
    if paint is None and plaster is not None and values.get('paint_from_plaster'):
        paint=plaster;notes.append('Painting coverage copied from plaster coverage by user choice.')
    run('Plaster','plaster',plaster,.012)
    run('Painting','painting',paint,.001)
    run('Floor tiles','flooring',floor,.01)
    run('Wall tiles','flooring',values.get('wall_tile_area'),.01)
    run('Floor screed','screed',floor,.05)
    run('Slab formwork','shuttering',slab,.01)
    for mode in (['rmc','site'] if values.get('rcc_mode')=='both' else [values.get('rcc_mode','rmc')]):
        run('RCC slab ('+mode+')','rcc',slab,values.get('slab_thickness'),mode)
    if wall_gross is not None:breakdown.append(('Wall gross area',wall_gross,'m²'))
    if wall_gross is not None:breakdown.append(('Door/window opening deduction',opening,'m²'))
    if wall_area is not None:breakdown.append(('Net wall area',wall_area,'m²'))
    if length is not None:breakdown.append(('Wall length (verify centreline)',length,'m'))
    if floor is not None:breakdown.append(('Floor area',floor,'m²'))
    if slab is not None:breakdown.append(('Slab area',slab,'m²'))
    if slab and values.get('slab_thickness'):breakdown.append(('RCC slab concrete volume',slab*values['slab_thickness'],'m³'))
    return {'measurement_basis':basis,'measurement_basis_label':BASES[basis],'rows':results,'skipped':skipped,'notes':notes,'floor':floor,'slab':slab,'wall_area':wall_area,'wall_length':length,'breakdown':breakdown}

def union_area(rects):
    xs=sorted(set([x for x,y,w,h in rects]+[x+w for x,y,w,h in rects]));area=0
    for left,right in zip(xs,xs[1:]):
        intervals=sorted((y,y+h) for x,y,w,h in rects if x<right and x+w>left)
        if not intervals:continue
        start,end=intervals[0];covered=0
        for a,b in intervals[1:]:
            if a>end:covered+=end-start;start,end=a,b
            else:end=max(end,b)
        area+=(covered+end-start)*(right-left)
    return area

def register_intelligent_recognition(app,db,owned_project,csrf,check_csrf,layout,esc,FILES,takeoff):
    from boq_reporting_v170 import register_boq_reporting, make_signed_preview
    register_boq_reporting(app,db,owned_project,csrf,check_csrf,layout,esc)
    def source(request,pid,fid):
        owned_project(request,pid)
        with db() as c:r=c.execute('SELECT * FROM uploads WHERE id=? AND project_id=?',(fid,pid)).fetchone()
        if not r:raise HTTPException(404,'Drawing not found')
        path=FILES/r['stored_name']
        if path.suffix.lower() not in EXT or not path.is_file():raise HTTPException(400,'Unsupported drawing file')
        return r,path
    def inspect(request,pid,fid,page):
        r,p=source(request,pid,fid)
        try:
            arr=raster(p,page);return r,arr,detect(arr)
        except Exception as e:raise HTTPException(422,'Recognition unavailable: '+str(e)[:170])
    @app.get('/projects/{pid}/drawings/{fid}/intelligence/overlay')
    def overlay(request:Request,pid:str,fid:str,page:int=0):
        _,arr,result=inspect(request,pid,fid,page)
        return Response(overlay_image(arr,result),media_type='image/png',headers={'Cache-Control':'no-store'})
    @app.get('/projects/{pid}/drawings/{fid}/intelligence')
    def form(request:Request,pid:str,fid:str,page:int=0):
        r,p=source(request,pid,fid)
        try:
            schedule=extract(p,page)
        except Exception as exc:
            schedule={'evidence':{},'rooms':[],'openings':[],'warnings':['Annotation extraction unavailable: '+str(exc)[:120]],'method':'unavailable'}
        try:
            _,arr,det=inspect(request,pid,fid,page)
            img=f'<img style="width:100%;max-width:1150px;border:1px solid #ddd" src="/projects/{pid}/drawings/{fid}/intelligence/overlay?page={page}">'
            regions=''.join(f'<tr><td><input type="checkbox" name="region" value="{i}" style="width:auto"></td><td>R{i+1}</td><td>{w} × {h} px</td><td>Candidate region; verify floor boundary</td></tr>' for i,(x,y,w,h,score) in enumerate(det['regions']))
            lines=''.join(f'<tr><td><input type="checkbox" name="line" value="{i}" style="width:auto"></td><td>L{i+1}</td><td>{length:.0f} px</td><td>{esc(orientation)}</td></tr>' for i,(*_,length,orientation) in enumerate(det['lines']))
            status=f'{len(det["regions"])} region candidates, {len(det["lines"])} straight-line candidates. Green = line, orange = region.'
        except HTTPException as e:img='';regions='';lines='';status=esc(e.detail)+'; manual confirmed dimensions can still be entered.'
        def field(name,label,value='',help=''):
            return f'<label>{esc(label)}</label><input type="number" step="any" min="0" name="{name}" value="{value}" placeholder="Optional">'+(f'<p class="hint">{esc(help)}</p>' if help else '')
        ev=schedule['evidence']
        def auto(k,default=''):
            return str(ev[k]['value']) if k in ev else default
        inputs=''.join([field('scale','Verified metres per pixel','','Use known drawing dimension / pixel length; leave blank to skip candidate-derived geometry.'),field('floor_area','Drawing floor area (m²)',auto('floor_area',str(schedule.get('room_area_sum','')))),field('slab_area','Drawing slab area (m²)',auto('slab_area')),field('height','Wall height (m)',auto('height','')),field('wall_thickness','Wall thickness (m)',auto('external_thickness','')),field('wall_length','Confirmed total wall centreline length (m)',auto('wall_length',''),'If not provided, selected lines + calibrated scale can estimate it.'),field('internal_wall_length','Optional internal partition centreline length (m)','','Overrides provisional regular-room-grid estimate.'),field('opening_area','Detected door/window opening area (m²)',str(schedule.get('opening_area_sum',''))),field('plaster_area','Confirmed plaster area (m²)'),field('paint_area','Confirmed painting area (m²)'),field('finish_faces','Confirmed plaster finish faces (1 or 2)','','Used only when wall length, height and opening area are available.'),field('wall_tile_area','Confirmed wall tiling area (m²)'),field('slab_thickness','Slab thickness (m)',auto('slab_thickness','')),field('waste','Wastage (%)',auto('waste','5'))])
        basis_html=('<label>Measurement basis for external masonry</label><select name="measurement_basis">'
            +''.join(f'<option value="{k}"{" selected" if k=="external" else ""}>{v}</option>' for k,v in BASES.items())
            +'</select><p class="hint">External face = 2×(L+W). Centreline = 2×(L+W) − 4×wall thickness (usual for brickwork volume). '
            'Internal face = 2×(L+W) − 8×wall thickness. External plaster always uses the external face. The chosen basis and formula appear in the report.</p>')
        details=''.join(f'<tr><td>{esc(k.replace('_',' ').title())}</td><td>{v['value']}</td><td>{esc(v['source'])}</td></tr>' for k,v in ev.items())
        rooms=''.join(f'<tr><td>{esc(v['name'])}</td><td>{v['length']:.2f} × {v['width']:.2f} m</td><td>{v['area']:.2f} m²</td></tr>' for v in schedule['rooms'])
        openings=''.join(f'<tr><td>{esc(v['label'])}</td><td>{v['count']}</td><td>{v['width']:.2f} × {v['height']:.2f} m</td><td>{v['area']:.2f} m²</td></tr>' for v in schedule['openings'])
        auto_html=f'''<div class="card" style="margin-top:16px"><h2>Automatic annotation extraction</h2><p class="hint">Source: {esc(schedule['method'])}. These are drawing labels, not independently verified measurements. Review before ordering materials.</p><div class="scroll"><table><tr><th>Extracted field</th><th>Value</th><th>Drawing evidence</th></tr>{details or '<tr><td colspan="3">No dimension annotations extracted</td></tr>'}</table></div><h3>Room schedule</h3><div class="scroll"><table><tr><th>Room</th><th>Dimensions</th><th>Area</th></tr>{rooms or '<tr><td colspan="3">No room schedule found</td></tr>'}</table></div><h3>Door / Window / Ventilator schedule</h3><div class="scroll"><table><tr><th>Opening</th><th>Count</th><th>Dimensions</th><th>Total opening area</th></tr>{openings or '<tr><td colspan="4">No opening schedule found</td></tr>'}</table></div><p class="hint">Opening total: {schedule.get('opening_area_sum','Not available')} m². Net masonry requires actual wall lengths and opening allocation; gross perimeter is not sufficient to establish internal walls.</p></div>'''
        return layout(request,'Intelligent Drawing Review',f'''<span class="eyebrow">CIVORA AI · v1.6.0 TEST BUILD</span><h1>Drawing Intelligence – Batch Review</h1><p><b>{esc(r['original_name'])}</b></p><p class="hint">{status} These are visual candidates, NOT verified architectural walls, doors or rooms. Confirm before quantity preview. No auto-save.</p>{img}{auto_html}<div class="card" style="margin-top:16px"><form method="post"><input type="hidden" name="csrf_token" value="{csrf(request)}"><input type="hidden" name="page" value="{page}"><div class="actions"><button type="submit">⚡ Auto calculate from extracted schedule (no manual entry)</button></div><p class="hint">Automatically extracted values are prefilled below. Candidate wall lines and region boxes are NOT auto-selected because they can include annotations and duplicate faces.</p><h2>1. Candidate floor regions</h2><div class="actions"><button type="button" onclick="document.querySelectorAll('input[name=region]').forEach(x=>x.checked=true)">Select all regions</button><button type="button" onclick="document.querySelectorAll('input[name=region]').forEach(x=>x.checked=false)">Clear regions</button></div><p class="hint">Select genuine room/floor regions only. Bounding boxes can include walls and labels.</p><div class="scroll"><table><tr><th>Select</th><th>ID</th><th>Bounds</th><th>Interpretation</th></tr>{regions or '<tr><td colspan="4">No regions detected</td></tr>'}</table></div><h2>2. Candidate wall lines</h2><div class="actions"><button type="button" onclick="document.querySelectorAll('input[name=line]').forEach(x=>x.checked=true)">Select all lines</button><button type="button" onclick="document.querySelectorAll('input[name=line]').forEach(x=>x.checked=false)">Clear lines</button></div><p class="hint">Select one centerline per wall; parallel wall faces can double count.</p><div class="scroll"><table><tr><th>Select</th><th>ID</th><th>Length</th><th>Orientation</th></tr>{lines or '<tr><td colspan="4">No straight lines detected</td></tr>'}</table></div><h2>3. Verified / optional specifications</h2>{basis_html}{inputs}<label><input type="checkbox" name="disable_grid" value="yes" style="width:auto"> Disable provisional 3×2 internal room-grid inference</label><label><input type="checkbox" name="use_floor_for_slab" value="yes" style="width:auto"> Use confirmed floor area as slab area (verify first)</label><label><input type="checkbox" name="paint_from_plaster" value="yes" style="width:auto"> Use computed/confirmed plaster area for painting (verify)</label><label>Concrete supply</label><select name="rcc_mode"><option value="rmc">RMC</option><option value="site">Indicative site mix</option><option value="both">Compare both</option></select><div class="actions"><button>Calculate all available drawing quantities →</button><a href="/projects/{pid}/drawings/{fid}">← Drawing Viewer</a></div></form></div>''')
    @app.post('/projects/{pid}/drawings/{fid}/intelligence')
    async def preview(request:Request,pid:str,fid:str):
        r,p=source(request,pid,fid);data=await request.form();check_csrf(request,str(data.get('csrf_token','')))
        def number(key):
            s=str(data.get(key,'')).strip()
            if not s:return None
            try:v=float(s)
            except ValueError:return None
            return v if math.isfinite(v) and 0<=v<=1e7 else None
        try:
            schedule=extract(p,int(data.get('page','0')))
        except Exception:
            schedule={'evidence':{},'rooms':[],'openings':[]}
        values={key:number(key) for key in ('scale','floor_area','slab_area','height','wall_thickness','opening_area','plaster_area','paint_area','wall_tile_area','slab_thickness','waste','wall_length','finish_faces')}
        values['floor_area']=values.pop('floor_area');values['slab_area']=values.pop('slab_area')
        # Only backfill explicitly annotated fields, never fabricate missing structural data.
        mapping={'floor_area':'floor_area','slab_area':'slab_area','height':'height','wall_thickness':'external_thickness','slab_thickness':'slab_thickness','waste':'waste'}
        for key,source_key in mapping.items():
            if values[key] is None and source_key in schedule['evidence']:
                values[key]=schedule['evidence'][source_key]['value']
        if values['opening_area'] is None and schedule['openings']:
            values['opening_area']=schedule['opening_area_sum']
        # Outside dimensions from the drawing are usable for an indicative perimeter only.
        values['external_plaster_thickness']=schedule['evidence'].get('external_plaster_thickness',{}).get('value')
        values['overall_length']=schedule['evidence'].get('overall_length',{}).get('value')
        values['overall_width']=schedule['evidence'].get('overall_width',{}).get('value')
        # Opening location is not independently detected. All non-internal openings
        # are tentatively allocated to the external face, and clearly labelled.
        values['external_opening_area']=round(sum(o['area'] for o in schedule['openings']
            if not ('D2' in o['label'].upper() or 'INTERNAL' in o['source'].upper())),5) if schedule['openings'] else None
        # Extracted schedule supplies internal thickness and door classification.
        values['internal_thickness']=schedule['evidence'].get('internal_thickness',{}).get('value')
        values['internal_plaster_thickness']=schedule['evidence'].get('internal_plaster_thickness',{}).get('value')
        values['internal_opening_area']=round(sum(o['area'] for o in schedule['openings']
            if 'D2' in o['label'].upper() or 'INTERNAL' in o['source'].upper()),5) if schedule['openings'] else None
        values['internal_wall_length']=number('internal_wall_length')
        try:values['measurement_basis']=normalise_basis(data.get('measurement_basis'))
        except ValueError as ex:raise HTTPException(400,str(ex))
        # Regular grid inference only when six room labels and uniform row sizes
        # agree with outside dimensions. User may override the provisional length.
        if values['internal_wall_length'] is None and data.get('disable_grid')!='yes':
            rooms=schedule['rooms']; L=values.get('overall_length');W=values.get('overall_width')
            if L and W and len(rooms)==6 and len({round(x['length'],2) for x in rooms})==1:
                a=rooms[0]['length']
                if abs(3*a-L)<.15 and abs(sum(x['area'] for x in rooms)-L*W)<.5:
                    t=values.get('wall_thickness')
                    if t:
                        grid=grid_partition_length(L,W,t,values['measurement_basis'])
                        values['internal_wall_length']=grid['length']
                        values['internal_grid_warning']=f'Regular 3×2 room grid assumed ({BASES[values["measurement_basis"]]}): {grid["formula"]}. Provisional internal wall length must be checked.'
                    elif values['measurement_basis']=='external':
                        values['internal_wall_length']=2*W+L
                        values['internal_grid_warning']='Regular 3×2 room grid assumed (external face); provisional internal wall length must be checked.'
        values['use_floor_for_slab']=data.get('use_floor_for_slab')=='yes'
        values['paint_from_plaster']=data.get('paint_from_plaster')=='yes'
        if values['finish_faces'] not in (1,2):values['finish_faces']=None
        values['rcc_mode']=data.get('rcc_mode') if data.get('rcc_mode') in ('rmc','site','both') else 'rmc'
        if values['waste'] is None:values['waste']=5
        if values['waste']>30:raise HTTPException(400,'Wastage must be at most 30%')
        try:
            _,arr,det=inspect(request,pid,fid,int(data.get('page','0')))
        except HTTPException:det={'regions':[],'lines':[]}
        region_ids={int(s) for s in data.getlist('region') if str(s).isdigit() and int(s)<len(det['regions'])}
        line_ids={int(s) for s in data.getlist('line') if str(s).isdigit() and int(s)<len(det['lines'])}
        result=calculate(values,region_ids,line_ids,det,takeoff)
        breakdown_html=''.join(f'<tr><td>{esc(k)}</td><td>{v:,.3f} {esc(u)}</td></tr>' for k,v,u in result['breakdown'])
        diagnostics=''.join(f'<tr><td>{esc(k)}</td><td>{esc(str(v))}</td></tr>' for k,v in values.items())
        rows=''.join('<tr><td>'+esc(name)+'</td><td>'+f'{area:,.2f} m²'+'</td><td>'+esc('; '.join(f'{i["material"]}: {float(i["quantity"]):,.2f} {i["unit"]}' for i in items))+'</td></tr>' for name,area,items in result['rows'])
        notes=''.join('<p class="hint">'+esc(n)+'</p>' for n in result['notes'] + schedule.get('warnings',[]))
        skipped=', '.join(esc(x) for x in result['skipped'])
        openings_html=''.join(f'<tr><td>{esc(o['label'])}</td><td>{o['count']}</td><td>{o['width']:.2f} × {o['height']:.2f} m</td><td>{o['area']:.2f} m²</td></tr>' for o in schedule['openings'])
        rooms_html=''.join(f'<tr><td>{esc(o['name'])}</td><td>{o['area']:.2f} m²</td></tr>' for o in schedule['rooms'])
        report_extra=f'''<div class="card" style="margin-top:16px"><h2>Extracted room & opening schedules</h2><div class="scroll"><table><tr><th>Room</th><th>Area</th></tr>{rooms_html or '<tr><td colspan="2">Not extracted</td></tr>'}</table></div><div class="scroll"><table><tr><th>Door / Window / Vent</th><th>Count</th><th>Size</th><th>Opening area</th></tr>{openings_html or '<tr><td colspan="4">Not extracted</td></tr>'}</table></div><p class="hint">Missing: independently verified internal wall centrelines, accurate opening placement, finish coverage, reinforcement/BBS, footing/column/beam schedules unless separately supplied. These are not guessed.</p></div>'''
        # Signed, stateless preview: no records are created until explicit confirmation.
        payload={'drawing_id':fid,'drawing_name':r['original_name'],'project_id':pid,
                 'measurement_basis':result['measurement_basis'],'measurement_basis_label':result['measurement_basis_label'],
                 'rows':[{'work':name,'area':area,'items':items} for name,area,items in result['rows']],
                 'breakdown':[{'measurement':name,'quantity':v,'unit':unit} for name,v,unit in result['breakdown']],
                 'rooms':schedule.get('rooms',[]),'openings':schedule.get('openings',[]),
                 'notes':result['notes']+schedule.get('warnings',[]),'skipped':result['skipped'],
                 'provisional':any('provisional' in name.lower() or 'indicative' in name.lower() for name,_,_ in result['rows'])}
        signed=make_signed_preview(db,payload)
        save_html=f'''<div class="card" style="margin-top:16px"><h2>4. Confirm & save BOQ</h2>
          <p class="hint">Preview is NOT saved. Confirm any provisional/indicative assumptions before saving. Rates are optional and editable after saving; all initial rates are 0 (not market quotations).</p>
          <form method="post" action="/projects/{pid}/drawings/{fid}/boq/save">
          <input type="hidden" name="csrf_token" value="{csrf(request)}">
          <input type="hidden" name="signed_preview" value="{esc(signed)}">
          <label><input type="checkbox" name="confirm_assumptions" value="yes" required style="width:auto"> I reviewed the drawing measurements, assumptions and deductions. Save as a draft BOQ.</label>
          <button type="submit">Save Draft BOQ & Edit Rates →</button></form>
          <p><a href="/projects/{pid}/drawings/{fid}/boq">View saved BOQ reports →</a></p></div>'''
        return layout(request,'Intelligent BOQ Preview',f'''<span class="eyebrow">PREVIEW ONLY · NOT SAVED</span><h1>Combined Drawing Quantity Preview</h1><p>{esc(r['original_name'])}</p><p class="notice">Measurement basis: <b>{esc(result['measurement_basis_label'])}</b> (masonry). External plaster: external face.</p><div class="card"><div class="scroll"><table><tr><th>Work</th><th>Area</th><th>Estimated materials</th></tr>{rows or '<tr><td colspan="3">No quantities calculated. Check the submitted values shown below; for images without readable dimensions, provide a confirmed area or calibrated scale.</td></tr>'}</table></div></div><div class="card" style="margin-top:16px"><h2>Calculation basis & deductions</h2><table><tr><th>Measurement</th><th>Quantity</th></tr>{breakdown_html or '<tr><td colspan="2">No measurable basis available</td></tr>'}</table><details><summary>Submitted values – troubleshooting</summary><table>{diagnostics}</table></details></div>{report_extra}{notes}{save_html}<p class="hint">Skipped due to missing confirmed values: {skipped or 'None'}</p><p class="hint">Green lines / orange regions are geometric candidates only. Doors/windows, room labels and BBS are NOT reliably recognized. Do not use unverified results for construction or ordering. No records saved.</p><a class="primary" href="/projects/{pid}/drawings/{fid}/intelligence">← Review / Edit</a>''')
