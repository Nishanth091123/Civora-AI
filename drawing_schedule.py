"""Civora drawing schedule parser: OCR and native text, with traceable evidence.
All extracted dimensions remain drawing annotations, not construction approval.
"""
import math,re,shutil
from pathlib import Path

UNITS={'MM':.001,'CM':.01,'FT':.3048,'FEET':.3048,'M':1.0}
DIM_RE=re.compile(r'(\d+(?:\.\d+)?)\s*(MM|CM|FT|FEET|M)(?![A-Z²]|2(?!\s*NOS?\b))',re.I)
PAIR_RE=re.compile(r'(\d+(?:\.\d+)?)\s*(?:MM|CM|FT|FEET|M)?\s*[X×]\s*(\d+(?:\.\d+)?)\s*(MM|CM|FT|FEET|M)(?![A-Z²]|2(?!\s*NOS?\b))',re.I)
AREA_RE=re.compile(r'(\d+(?:\.\d+)?)\s*(?:M\s*(?:2|²)|SQ\.?\s*M)\b',re.I)
ROOM_RE=re.compile(r'\b(BEDROOM\s*\d*|LIVING|DINING|KITCHEN|BATHROOM|TOILET|HALL)\b',re.I)
OPEN_RE=re.compile(r'\b(DOOR\s*[A-Z0-9-]*|WINDOW\s*[A-Z0-9-]*|VENTILATOR\s*[A-Z0-9-]*)\b',re.I)  # legacy; kept for compatibility
# v2.4: a schedule code is a type letter + number (D1, W2, V1), never the first digit of a size.
OPEN_CODE_RE=re.compile(r'\b(DOOR|WINDOW|VENTILATOR|VENT)\s*[-–]?\s*([DWV]\d{1,2})\b',re.I)
OPEN_KIND_RE=re.compile(r'\b(DOOR|WINDOW|VENTILATOR|VENT)\b',re.I)
OPEN_QUALIFIERS=('MAIN','INTERNAL','TOILET','BATHROOM','KITCHEN','BALCONY','FRENCH','SLIDING')

def opening_label(s):
    """Stable label for one opening schedule row.

    'DOOR D1 - MAIN 1 NO. @ 1.20 X 2.10 M' -> 'DOOR D1'
    'MAIN DOOR 1.20 X 2.10 M 1 NO'         -> 'MAIN DOOR'
    'INTERNAL DOOR 0.90 X 2.10 M 5 NOS'    -> 'INTERNAL DOOR'
    'VENT 0.60 X 0.45 M 2 NOS'             -> 'VENTILATOR'
    Sizes are never read as part of the label.
    """
    s=_normal(s)
    m=OPEN_CODE_RE.search(s)
    if m:
        kind='VENTILATOR' if m[1].upper()=='VENT' else m[1].upper()
        return f'{kind} {m[2].upper()}'
    m=OPEN_KIND_RE.search(s)
    if not m:return None
    kind='VENTILATOR' if m[1].upper()=='VENT' else m[1].upper()
    before=s[:m.start()].split()
    qualifier=before[-1] if before and before[-1] in OPEN_QUALIFIERS else ''
    return (qualifier+' '+kind).strip()

def _normal(s):
    return re.sub(r'\s+',' ',str(s).replace('×','x').replace('²','2')).strip().upper()

def text_from_drawing(path,page=0):
    path=Path(path); ext=path.suffix.lower(); lines=[]; method=''
    if ext=='.dxf':
        import ezdxf
        d=ezdxf.readfile(str(path));method='DXF TEXT/MTEXT'
        for e in d.modelspace():
            if e.dxftype()=='TEXT':lines.append(str(e.dxf.text))
            elif e.dxftype()=='MTEXT':lines.extend(e.plain_text().splitlines())
    elif ext=='.pdf':
        import fitz
        with fitz.open(str(path)) as doc:
            if not 0<=page<len(doc):raise ValueError('Invalid PDF page')
            lines=doc[page].get_text(sort=True).splitlines()
            if len(''.join(lines).strip())<25:
                import pytesseract
                from PIL import Image
                pix=doc[page].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                img=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                lines=pytesseract.image_to_string(img,config='--psm 6').splitlines();method='PDF OCR'
            else:method='PDF selectable text'
    elif ext in ('.png','.jpg','.jpeg'):
        import pytesseract
        from PIL import Image,ImageOps
        img=Image.open(path).convert('RGB')
        # PSM 6 retains tabular label/value pairs in the same row on typical plans.
        lines=pytesseract.image_to_string(img,config='--psm 6').splitlines()
        method='Tesseract OCR (PSM 6)'
        if not any('OVERALL' in s.upper() or 'GROSS FOOTPRINT' in s.upper() for s in lines):
            extra=pytesseract.image_to_string(ImageOps.grayscale(img),config='--psm 11').splitlines()
            lines+=extra;method+=' + sparse fallback'
    else:raise ValueError('Unsupported drawing type')
    return [_normal(s) for s in lines if str(s).strip()],method

def extract(path,page=0):
    lines,method=text_from_drawing(path,page)
    out={'method':method,'evidence':{},'rooms':[],'openings':[],'warnings':[], 'raw_count':len(lines)}
    ev=out['evidence']
    def record(k,v,source):
        if v is not None and math.isfinite(v) and 0<v<1e7 and k not in ev:
            ev[k]={'value':round(v,5),'source':source}
    def dim(s):
        m=DIM_RE.search(s)
        return float(m[1])*UNITS[m[2].upper()] if m else None
    def pair(s):
        m=PAIR_RE.search(s)
        if not m:return None
        factor=UNITS[m[3].upper()]
        return float(m[1])*factor,float(m[2])*factor
    def area(s):
        m=AREA_RE.search(s)
        return float(m[1]) if m else None
    # Some native PDFs place schedule labels and corresponding values on separate lines.
    # Only join adjacent lines for recognizable schedule labels.
    combined=[]
    labels=('OVERALL EXTERNAL SIZE','GROSS FOOTPRINT','EXTERNAL WALL THICKNESS','INTERNAL WALL THICKNESS',
            'WALL HEIGHT','RCC SLAB THICKNESS','INTERNAL PLASTER','EXTERNAL PLASTER',
            'DOOR D1','DOOR D2','WINDOW W1','VENTILATOR V1','FLOOR TILE SIZE','INTERNAL WALL LENGTH','PLINTH HEIGHT','PARAPET HEIGHT',
            'KITCHEN WALL TILE','BATHROOM WALL TILE','TILE WASTAGE','ROOF WATERPROOFING')
    for i,s in enumerate(lines):
        combined.append(s)
        if i+1<len(lines) and any(label in s for label in labels) and not (dim(s) or pair(s) or area(s)):
            nxt=lines[i+1]
            if (not pair(s) and pair(nxt)) or (not dim(s) and dim(nxt)) or (not area(s) and area(nxt)):
                combined.append(s+' '+nxt)
    # For native PDFs, room labels precede the dimension rows as two runs.
    # Associate them by sequence only if equal counts and the sizes are plausible.
    room_labels=[];room_sizes=[]
    for s in lines:
        if ROOM_RE.fullmatch(s):room_labels.append(s)
        q=pair(s)
        if q and not any(x in s for x in ('OVERALL','DOOR','WINDOW','VENT','TILE','EXTERNAL SIZE')) and s.strip().startswith(tuple(str(n) for n in range(1,10))):
            if 1<=q[0]<=30 and 1<=q[1]<=30:room_sizes.append(q)
    if Path(path).suffix.lower()=='.pdf' and (not room_labels or len(room_labels)!=len(room_sizes)):
        try:
            import fitz
            with fitz.open(str(path)) as _doc:
                _raw=[_normal(v) for v in _doc[page].get_text().splitlines()]
            room_labels=[v for v in _raw if ROOM_RE.fullmatch(v)]
            room_sizes=[pair(v) for v in _raw if pair(v) and ROOM_RE.fullmatch(v)==None and v.count(' X ')==1 and v.startswith(('4.','3.','5.'))][:len(room_labels)]
        except Exception:pass
    if room_labels and len(room_labels)==len(room_sizes):
        for name,(a,b) in zip(room_labels,room_sizes):
            out['rooms'].append({'name':name,'length':a,'width':b,'area':round(a*b,5),'source':'PDF label/dimension sequence; verify'})
    # For OCR, label and dimensions often appear on distinct rows, with 3 rooms per row.
    if not out['rooms']:
        for i,s in enumerate(lines):
            names=ROOM_RE.findall(s)
            if len(names)<2:continue
            for next_line in lines[i+1:i+5]:
                matches=list(PAIR_RE.finditer(next_line))
                if len(matches)!=len(names):continue
                for name,m in zip(names,matches):
                    a=float(m[1])*UNITS[m[3]];b=float(m[2])*UNITS[m[3]]
                    if 1<=a<=30 and 1<=b<=30:
                        out['rooms'].append({'name':name,'length':a,'width':b,'area':round(a*b,5),'source':s+' / '+next_line})
                break
    for s in combined:
        q=pair(s)
        if q and ROOM_RE.search(s) and not any(r['source']==s for r in out['rooms']):
            name=ROOM_RE.search(s)[1]
            if not any(r['name']==name for r in out['rooms']) and 1<=q[0]<=30 and 1<=q[1]<=30:
                out['rooms'].append({'name':name,'length':q[0],'width':q[1], 'area':round(q[0]*q[1],5),'source':s})

        if ('OVERALL EXTERNAL SIZE' in s or 'OVERALL SIZE' in s or s.startswith('OVERALL ')) and q:
            a,b=q;record('overall_length',a,s);record('overall_width',b,s)
            record('floor_area',a*b,s);record('slab_area',a*b,s)
        if 'GROSS FOOTPRINT' in s:
            record('floor_area',area(s),s);record('slab_area',area(s),s)
        if 'WALL HEIGHT' in s:record('height',dim(s),s)
        if 'EXTERNAL WALL THICKNESS' in s:record('external_thickness',dim(s.split('EXTERNAL WALL THICKNESS',1)[1]),s)
        elif s.startswith('EXTERNAL WALL ') and 'LENGTH' not in s and 'HEIGHT' not in s:record('external_thickness',dim(s.split('EXTERNAL WALL',1)[1]),s)
        if 'INTERNAL WALL THICKNESS' in s:record('internal_thickness',dim(s.split('INTERNAL WALL THICKNESS',1)[1]),s)
        elif s.startswith('INTERNAL WALL ') and 'LENGTH' not in s and 'HEIGHT' not in s:record('internal_thickness',dim(s.split('INTERNAL WALL',1)[1]),s)
        # v3.7.0: optional notes that make the estimate exact instead of typical
        if 'INTERNAL WALL LENGTH' in s:record('internal_wall_length',dim(s.split('INTERNAL WALL LENGTH',1)[1]),s)
        if 'PLINTH HEIGHT' in s:record('plinth_height',dim(s.split('PLINTH HEIGHT',1)[1]),s)
        if 'PARAPET HEIGHT' in s:record('parapet_height',dim(s.split('PARAPET HEIGHT',1)[1]),s)
        if 'RCC SLAB THICKNESS' in s or s.startswith('SLAB THICKNESS'):record('slab_thickness',dim(s),s)
        if 'INTERNAL PLASTER' in s:record('internal_plaster_thickness',dim(s),s)
        if 'EXTERNAL PLASTER' in s:record('external_plaster_thickness',dim(s),s)
        if 'TILE WASTAGE' in s:
            m=re.search(r'(\d+(?:\.\d+)?)\s*(?:PERCENT|%)',s)
            if m:record('waste',float(m[1]),s)
        if 'ROOF WATERPROOFING' in s:record('roof_waterproof_area',area(s),s)
        if q and any(k in s for k in ('DOOR','WINDOW','VENTILATOR','VENT ')):
            label=opening_label(s)
            count=re.search(r'(?:\b|(?<=M))(\d+)\s*NOS?\.?\b',s)   # v3.7.0: OCR often glues the unit: '2.10 M1 NO'
            if label and count:
                a,b=q;qty=int(count[1])
                # Duplicate = same label AND same size (OCR / joined lines can repeat a row).
                # Two different openings are never merged just because labels look alike.
                duplicate=any(o['label']==label and abs(o['width']-a)<1e-6 and abs(o['height']-b)<1e-6 for o in out['openings'])
                if 0<qty<=100 and 0<a<=5 and 0<b<=5 and not duplicate:
                    out['openings'].append({'label':label,'width':a,'height':b,'count':qty,'area':round(a*b*qty,5),'source':s})
        if q and ('FLOOR TILE SIZE' in s or s.startswith('FLOOR TILE ')):record('floor_tile_area_each',q[0]*q[1],s)
        if q and 'KITCHEN WALL TILE' in s:record('kitchen_tile_area_each',q[0]*q[1],s)
        if q and 'BATHROOM WALL TILE' in s:record('bathroom_tile_area_each',q[0]*q[1],s)
    if out['rooms']:out['room_area_sum']=round(sum(r['area'] for r in out['rooms']),5)
    if out['openings']:out['opening_area_sum']=round(sum(o['area'] for o in out['openings']),5)
    out['warnings'].append('OCR and PDF labels are not independently verified. Check measurements and opening allocation before procurement.')
    if not ev and not out['openings'] and not out['rooms']:
        out['warnings'].append('No supported schedule values recognized; review the original drawing.')
    return out
