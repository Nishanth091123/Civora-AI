import re,math
from pathlib import Path

def inspect_document(path):
    ext=Path(path).suffix.lower();e=[];v={};notes=[];text=''
    if ext=='.pdf':
        try:
            import fitz
            with fitz.open(path) as d:
                text='\n'.join(p.get_text() for p in list(d)[:8])
                if len(text.strip())<30:
                    try:
                        import pytesseract
                        from PIL import Image
                        import io
                        for page in list(d)[:3]:
                            pix=page.get_pixmap(matrix=fitz.Matrix(1.7,1.7))
                            text+='\n'+pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes('png'))),config='--psm 11')
                        e.append('Scanned PDF: OCR text candidates (verify)')
                    except Exception as ocr_ex:notes.append('Scanned PDF OCR unavailable: '+str(ocr_ex)[:90])
        except Exception as ex:notes.append('PDF text extraction unavailable: '+str(ex)[:100])
    elif ext=='.dxf':
        try:
            from drawing_workspace import inspect_dxf
            d=inspect_dxf(path)
            if 'error' in d:notes.append(d['error'])
            else:
                e.append('CAD bounding extents %.2f × %.2f m; NOT verified room dimensions'%(d['length'],d['width']))
                e.extend('%s: %s segments, %.2f m linework (unclassified)'%(k,a['segments'],a['length']) for k,a in list(d['layers'].items())[:12])
                text='\n'.join(d['labels'])
        except Exception as ex:notes.append('DXF extraction unavailable: '+str(ex)[:100])
    elif ext in ('.png','.jpg','.jpeg','.webp'):
        try:
            import pytesseract
            from PIL import Image,ImageOps,ImageEnhance
            im=Image.open(path).convert('RGB')
            if max(im.size)>2600:im.thumbnail((2600,2600))
            im=ImageEnhance.Contrast(ImageOps.grayscale(im)).enhance(2)
            text=pytesseract.image_to_string(im,config='--psm 11')
            e.append('Image OCR: extracted text candidates for review; NOT reliable geometry/wall recognition')
        except Exception as ex:
            notes.append('Image OCR unavailable ('+str(ex)[:90]+'); optional Tesseract OCR installation needed')
    else:notes.append('Unsupported recognition format; enter verified values if available.')
    # Units are normalized to SI only after explicit suffix detection.
    def to_m2(value,unit):
        u=unit.lower().replace(' ','').replace('.','').replace('²','2')
        if 'ft' in u or 'feet' in u or u.startswith('sf') or 'sqft' in u:return value*0.09290304
        if 'mm' in u:return value/1_000_000
        if 'cm' in u:return value/10_000
        return value
    area_units=r'(?:sq\.?\s*ft|sq\.?\s*feet|s\.?\s*ft|sqft|ft[²2]|sf|sq\.?\s*m|m[²2]|sqm|sq\.?\s*mm|mm[²2]|sq\.?\s*cm|cm[²2])'
    for key,pat in [('slab',r'covered\s*/?\s*slab|slab\s*area|covered\s*area'),('floor',r'plinth\s*area|floor\s*area|carpet\s*area')]:
        m=re.search(r'(?i)(?:'+pat+r')\s*[:=]?\s*([\d,]+(?:\.\d+)?)\s*('+area_units+r')',text)
        if m:
            val=float(m.group(1).replace(',',''))
            if 0<val<1e9:
                v[key]=round(to_m2(val,m.group(2)),3)
                e.append('%s area annotation: %s %s → %.3f m² (verify)'%(key,m.group(1),m.group(2),v[key]))
    # Recognize dimension tokens without inferring that they describe a room.
    dim_pattern=r"(?<!\w)(\d{1,4})\s*[′']\s*(?:(\d{1,2}(?:\.\d+)?)\s*[″\"])?"
    candidates=[]
    for m in re.finditer(dim_pattern,text):
        ft=float(m.group(1));inch=float(m.group(2) or 0)
        if inch<12 and ft>0:candidates.append('%s → %.3f m'%(m.group(0),(ft+inch/12)*.3048))
        if len(candidates)>=8:break
    for m in re.finditer(r'(?i)\b(\d+(?:\.\d+)?)\s*(mm|cm|metres?|meters?|m|feet|ft)\b',text):
        n=float(m.group(1));u=m.group(2).lower()
        factor=.001 if u=='mm' else .01 if u=='cm' else .3048 if u in ('ft','feet') else 1
        candidates.append('%s → %.3f m'%(m.group(0),n*factor))
        if len(candidates)>=12:break
    if candidates:e.append('Dimension text candidates (unassigned): '+', '.join(candidates))
    if not e:notes.append('No reliable dimension annotation extracted. Required values must be confirmed.')
    return e,v,notes

FIELDS=[('slab','RCC slab area (m²)',None),('floor','Floor area (m²)',None),('external','External wall centerline length (m)',None),('internal','Internal wall centerline length (m)',None),('height','Wall height (m)',3),('ext_thick','External wall thickness (m)',.23),('int_thick','Internal wall thickness (m)',.115),('ext_open','External openings area (m²)',None),('int_open','Internal openings area (m²)',None),('slab_depth','Slab thickness (m)',.125),('toilet_tile','Toilet wall tiling net area (m²)',None),('kitchen_tile','Kitchen wall tiling net area (m²)',None),('floor_tile_side','Floor tile side (m)',.6096),('wall_tile_side','Wall tile side (m)',.3048),('waste','Tile wastage (%)',5)]

def adaptive_form_html(pid,fid,name,report,csrf,esc):
    evidence,detected,notes=report
    lines=''.join('<li>'+esc(z)+'</li>' for z in evidence) or '<li>No extracted annotations</li>'
    lines+=''.join('<li>'+esc(z)+'</li>' for z in notes)
    fields=''
    for key,label,default in FIELDS:
        value=detected.get(key,default)
        origin='Drawing candidate: editable' if key in detected else 'Optional: not detected' if value is None else 'Optional suggested assumption'
        fields+=f'<label>{esc(label)} · {esc(origin)}</label><input type="number" name="{key}" min="0" step="any" value="{value if value is not None else ""}">'
    return f'''<span class="eyebrow">ADAPTIVE DRAWING ANALYSIS</span><h1>{esc(name)}</h1><p>PDF/DXF text and image OCR are inspected when available; OCR may need Tesseract installed. Unknown quantities are NOT copied from the previous sample building.</p><div class="card"><h2>Detected evidence and limitations</h2><ul>{lines}</ul></div><div class="card form"><h2>Review detected measurements (optional)</h2><p class="hint">Leave unknown values blank. Only work types with sufficient inputs will be calculated; blank values are never treated as zero. Review assumptions before construction.</p><form method="post"><input type="hidden" name="csrf_token" value="{csrf}">{fields}<label>Concrete supply</label><select name="mode"><option value="both">RMC + indicative site mix</option><option value="rmc">RMC only</option><option value="site">Site mix only</option></select><button>Generate verified-input BOQ →</button></form></div><a href="/projects/{pid}/drawings/{fid}">← Drawing Viewer</a>'''

def adaptive_report_html(pid,fid,name,report,data,takeoff,esc):
    x={};invalid=[]
    for key,label,_ in FIELDS:
        raw=str(data.get(key,'')).strip()
        if not raw:
            x[key]=None
            continue
        try:
            n=float(raw)
            if not math.isfinite(n) or n<0 or n>1e7:raise ValueError()
            x[key]=n
        except (ValueError,TypeError):
            x[key]=None
            invalid.append(label+' was invalid and ignored')
    rows=[];warnings=list(invalid);skipped=[]
    def has(*keys):return all(x.get(k) is not None for k in keys)
    def add(title,work,area,depth,waste=5,rcc_mode='rmc'):
        if area<=0:return
        try:
            result=takeoff(work=work,length=area,width=1,depth=depth,unit='m',waste=waste,rcc_mode=rcc_mode,rcc_grade='M20',rcc_site_method='nominal',rcc_nominal_ratio='1:1.5:3')
            materials='; '.join('%s: %.2f %s'%(i['material'],i['quantity'],i['unit']) for i in result['items'])
            rows.append(f'<tr><td>{esc(title)}</td><td>{area:.2f} m²</td><td>{esc(materials)}</td></tr>')
        except (ValueError,KeyError,TypeError) as ex:warnings.append(title+': '+str(ex))
    ext=None;internal=None
    if has('external','height','ext_thick'):
        gross=x['external']*x['height'];op=x['ext_open'] if x['ext_open'] is not None else 0
        if op>gross:warnings.append('External openings exceed wall area; external masonry omitted')
        elif x['ext_open'] is None:skipped.append('External masonry: opening area missing; no deduction assumed')
        else:
            ext=gross-op
            add('External masonry','brickwork',ext,x['ext_thick'])
    else:skipped.append('External masonry: wall length, height and thickness needed')
    if has('internal','height','int_thick'):
        gross=x['internal']*x['height'];op=x['int_open'] if x['int_open'] is not None else 0
        if op>gross:warnings.append('Internal openings exceed wall area; internal masonry omitted')
        elif x['int_open'] is None:skipped.append('Internal masonry: opening area missing; no deduction assumed')
        else:
            internal=gross-op
            add('Internal masonry','brickwork',internal,x['int_thick'])
    else:skipped.append('Internal masonry: wall length, height and thickness needed')
    if ext is not None and internal is not None and has('toilet_tile','kitchen_tile'):
        plaster=ext+2*internal-x['toilet_tile']-x['kitchen_tile']
        if plaster>=0:
            add('Wall plaster','plaster',plaster,.012)
            add('Painting','painting',plaster,.001)
        else:warnings.append('Tile area exceeds available wall area; plaster and paint omitted')
    else:skipped.append('Plaster/painting: verified wall net areas and tiling deductions needed')
    if has('floor'):
        add('Floor tiles','flooring',x['floor'],.01,x['waste'] if x['waste'] is not None else 5)
    else:skipped.append('Floor tiles: floor area needed')
    for title,key in [('Toilet wall tiles','toilet_tile'),('Kitchen wall tiles','kitchen_tile')]:
        if has(key):add(title,'flooring',x[key],.01,x['waste'] if x['waste'] is not None else 5)
        else:skipped.append(title+': net tile area needed')
    mode=str(data.get('mode','both'))
    if has('slab','slab_depth'):
        if mode in ('both','rmc'):add('RCC slab – RMC','rcc',x['slab'],x['slab_depth'])
        if mode in ('both','site'):add('RCC slab – site mix (indicative)','rcc',x['slab'],x['slab_depth'],rcc_mode='site')
        add('Slab shuttering','shuttering',x['slab'],.01)
    else:skipped.append('RCC slab: slab area and thickness needed')
    waste=x['waste'] if x['waste'] is not None else 5
    for title,area_key,side_key in [('Floor tile pieces','floor','floor_tile_side'),('Toilet wall tile pieces','toilet_tile','wall_tile_side'),('Kitchen wall tile pieces','kitchen_tile','wall_tile_side')]:
        if not has(area_key,side_key):
            skipped.append(title+': area and tile size needed')
            continue
        area=x[area_key];side=x[side_key]
        if side<=0:warnings.append(title+': tile size must be positive');continue
        rows.append(f'<tr><td>{esc(title)}</td><td>{area:.2f} m²</td><td>{math.ceil(area*(1+waste/100)/(side*side))} Nos</td></tr>')
    if not rows:
        rows.append('<tr><td colspan="3">No work quantities could be calculated from the available inputs. Enter any relevant measurements to enable individual work calculations.</td></tr>')
    return f'''<span class="eyebrow">PRELIMINARY · NOT SAVED</span><h1>Available-Input Material BOQ</h1><p>{esc(name)}</p><div class="card"><div class="scroll"><table><thead><tr><th>Work</th><th>Quantity basis</th><th>Materials</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>{''.join('<p class="hint">'+esc(z)+'</p>' for z in warnings)}<details><summary>Not calculated (optional missing inputs): {len(skipped)} work items</summary><ul>{''.join('<li>'+esc(z)+'</li>' for z in skipped)}</ul></details><p class="hint">This is an estimate based on user-confirmed inputs, NOT full automatic wall/door/room detection. BBS requires approved reinforcement details; nominal site mix is not an approved mix design.</p><a href="/projects/{pid}/drawings/{fid}/adaptive">← Edit inputs</a>'''
