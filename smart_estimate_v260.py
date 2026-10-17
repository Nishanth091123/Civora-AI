"""Civora AI v2.6.0 - Smart Estimate: one drawing in, full estimate out.

  1. Upload / choose a drawing (or enter sizes without a drawing)
  2. Civora reads every measurement it can find. Only what is MISSING is asked for,
     pre-filled with a clearly marked typical value the user can change.
  3. One click: materials (walls, plaster, paint, tiles, slab, roof), preliminary RCC frame
     (footings, columns, beams, steel by thumb rule), Rate Master pricing -> saved draft BOQ.

Nothing here certifies structural design: frame sizes are PRELIMINARY quantities only.
No new tables: the result is saved as a normal draft BOQ (civora_boq_reports).
"""
import csv
import io
import json
import math
import re
import time
import uuid
from collections import OrderedDict

from measurement import BASES, normalise_basis, wall_faces, grid_partition_length

SQFT_PER_M2 = 10.7639
DRAWING_EXT = ('.png', '.jpg', '.jpeg', '.pdf', '.dxf')

# key, English label, Tamil label, unit, group, min, max, step
FIELDS = [
    ('length', 'Building outside length', 'கட்டிட வெளிப்புற நீளம்', 'm', 'building', 1, 500, 0.01),
    ('width', 'Building outside width', 'கட்டிட வெளிப்புற அகலம்', 'm', 'building', 1, 500, 0.01),
    ('floors', 'Number of floors', 'தளங்களின் எண்ணிக்கை', 'nos', 'building', 1, 10, 1),
    ('height', 'Wall height per floor', 'ஒரு தளத்தின் சுவர் உயரம்', 'm', 'building', 2, 6, 0.01),
    ('floor_area', 'Floor area per floor', 'ஒரு தளத்தின் தரைப் பரப்பு', 'm²', 'building', 1, 250000, 0.01),
    ('plinth_h', 'Plinth height above ground', 'பிளின்த் உயரம் (தரைக்கு மேல்)', 'm', 'building', 0, 1.5, 0.01),
    ('ext_thick', 'External wall thickness', 'வெளிச்சுவர் தடிமன்', 'm', 'walls', 0.075, 0.6, 0.005),
    ('int_thick', 'Internal wall thickness', 'உட்சுவர் தடிமன்', 'm', 'walls', 0.075, 0.6, 0.005),
    ('int_length', 'Internal wall total length', 'உட்சுவர் மொத்த நீளம்', 'm', 'walls', 0, 5000, 0.01),
    ('ext_open', 'Doors & windows on external walls', 'வெளிச்சுவர் கதவு/ஜன்னல் பரப்பு', 'm²', 'walls', 0, 5000, 0.01),
    ('int_open', 'Doors on internal walls', 'உட்சுவர் கதவு பரப்பு', 'm²', 'walls', 0, 5000, 0.01),
    ('slab_area', 'Roof slab area per floor', 'கூரை ஸ்லாப் பரப்பு', 'm²', 'slab', 1, 250000, 0.01),
    ('slab_thick', 'Slab thickness', 'ஸ்லாப் தடிமன்', 'm', 'slab', 0.075, 0.5, 0.005),
    ('wall_tile', 'Wall tiles (kitchen + bathrooms) per floor', 'சுவர் டைல்ஸ் பரப்பு', 'm²', 'slab', 0, 5000, 0.01),
    ('roof_wp', 'Roof waterproofing area', 'கூரை நீர்க்காப்பு பரப்பு', 'm²', 'slab', 0, 250000, 0.01),
    ('parapet_h', 'Parapet wall height on roof', 'மொட்டை மாடி கைப்பிடிச் சுவர் உயரம்', 'm', 'slab', 0, 1.5, 0.01),
    ('columns', 'Number of columns', 'தூண்களின் எண்ணிக்கை', 'nos', 'frame', 0, 500, 1),
    ('col_b', 'Column width', 'தூண் அகலம்', 'm', 'frame', 0.15, 1.5, 0.01),
    ('col_d', 'Column depth', 'தூண் ஆழம்', 'm', 'frame', 0.15, 1.5, 0.01),
    ('ftg_l', 'Footing length', 'அடித்தள நீளம்', 'm', 'frame', 0.5, 6, 0.01),
    ('ftg_w', 'Footing width', 'அடித்தள அகலம்', 'm', 'frame', 0.5, 6, 0.01),
    ('ftg_t', 'Footing thickness', 'அடித்தள தடிமன்', 'm', 'frame', 0.15, 1.5, 0.01),
    ('fdn_depth', 'Foundation depth below ground', 'அடித்தள ஆழம் (தரைக்கு கீழ்)', 'm', 'frame', 0.6, 5, 0.01),
    ('beam_b', 'Beam width', 'பீம் அகலம்', 'm', 'frame', 0.15, 1, 0.01),
    ('beam_d', 'Beam depth', 'பீம் ஆழம்', 'm', 'frame', 0.2, 1.5, 0.01),
]
FIELD = {f[0]: f for f in FIELDS}
GROUPS = [('building', 'Building size', 'கட்டிட அளவு'), ('walls', 'Walls & openings', 'சுவர் & கதவு/ஜன்னல்'),
          ('slab', 'Slab, tiles & roof', 'ஸ்லாப், டைல்ஸ் & கூரை'),
          ('frame', 'Structure – columns, beams, footings (preliminary)', 'தூண், பீம், அடித்தளம் (ஆரம்ப மதிப்பீடு)')]
MEASURED_GROUPS = ('building', 'walls', 'slab')

# Thumb-rule steel (kg per m³ of concrete) - preliminary planning only, replace with BBS.
STEEL_RULES = [('steel_footing', 'Footings', 80), ('steel_column', 'Columns', 180),
               ('steel_beam', 'Beams', 150), ('steel_slab', 'Slabs', 90)]

SOURCE_LABEL = {'drawing': 'From drawing', 'derived': 'Worked out from drawing',
                'typical': 'Typical value – please check', 'user': 'Entered by you'}


def _ev(schedule, key):
    e = (schedule.get('evidence') or {}).get(key)
    return (float(e['value']), e.get('source', '')) if e and e.get('value') is not None else (None, '')


def _tile_wall_area(schedule):
    """Kitchen dado + bathroom walls from the room schedule and the tile notes on the drawing."""
    ev = schedule.get('evidence') or {}

    def height(key, default):
        m = re.search(r'HEIGHT\s*(\d+(?:\.\d+)?)\s*M', str(ev.get(key, {}).get('source', '')).upper())
        return float(m.group(1)) if m else default
    kh, bh = height('kitchen_tile_area_each', 0.6), height('bathroom_tile_area_each', 2.1)
    total, parts = 0.0, []
    for r in schedule.get('rooms') or []:
        name = str(r.get('name', '')).upper()
        per = 2 * (float(r.get('length') or 0) + float(r.get('width') or 0))
        if 'KITCHEN' in name:
            a = per * kh
        elif 'BATH' in name or 'TOILET' in name:
            a = max(per * bh - 0.9 * 2.1, 0)
        else:
            continue
        total += a
        parts.append(f'{r.get("name")}: {a:.2f} m²')
    return round(total, 2), parts


def build_inputs(schedule, project_area_sqft):
    """Every input with (value, source, note). source: drawing / derived / typical."""
    schedule = schedule or {}
    inp = OrderedDict()

    def put(k, v, src, note=''):
        inp[k] = {'value': round(float(v), 4), 'source': src, 'note': note}

    L, sL = _ev(schedule, 'overall_length')
    W, sW = _ev(schedule, 'overall_width')
    if L and W:
        put('length', L, 'drawing', sL); put('width', W, 'drawing', sW)
    else:
        side = math.sqrt(max(float(project_area_sqft or 0), 100) / SQFT_PER_M2)
        L = W = round(side, 2)
        put('length', L, 'typical', 'Square plan assumed from the project built-up area')
        put('width', W, 'typical', 'Square plan assumed from the project built-up area')
    put('floors', 1, 'typical', 'Ground floor only unless you change it')
    v, s = _ev(schedule, 'height')
    put('height', v or 3.0, 'drawing' if v else 'typical', s or 'Typical floor-to-ceiling 3.0 m')
    v, s = _ev(schedule, 'floor_area')
    rooms = schedule.get('rooms') or []
    if v:
        put('floor_area', v, 'drawing', s)
    elif rooms:
        put('floor_area', sum(float(r['area']) for r in rooms), 'derived', f'Sum of {len(rooms)} rooms in the room schedule')
    else:
        put('floor_area', L * W, 'derived' if inp['length']['source'] == 'drawing' else 'typical', 'Length × width')
    v, s = _ev(schedule, 'external_thickness')
    te = v or 0.23
    put('ext_thick', te, 'drawing' if v else 'typical', s or 'Typical 230 mm (9 inch) brick wall')
    v, s = _ev(schedule, 'internal_thickness')
    put('int_thick', v or 0.115, 'drawing' if v else 'typical', s or 'Typical 115 mm (4.5 inch) partition')
    # internal wall length: regular 3x2 room grid that matches the outside size, else a typical ratio
    grid = None
    if len(rooms) == 6 and len({round(float(r['length']), 2) for r in rooms}) == 1 and inp['length']['source'] == 'drawing':
        a = float(rooms[0]['length'])
        if abs(3 * a - L) < .15 and abs(sum(float(r['area']) for r in rooms) - L * W) < .5:
            grid = grid_partition_length(L, W, te, 'centreline')
    v_il, s_il = _ev(schedule, 'internal_wall_length')
    if v_il:
        put('int_length', v_il, 'drawing', s_il)
    elif grid:
        put('int_length', grid['length'], 'derived', 'Regular 3×2 room grid: ' + grid['formula'])
    else:
        perim = 2 * (L + W)
        put('int_length', 0.75 * perim, 'typical', 'Typical: about 0.75 × outside perimeter. Measure from the plan for accuracy')
    openings = schedule.get('openings') or []
    H = inp['height']['value']
    if openings:
        internal = [o for o in openings if 'D2' in o['label'].upper() or 'INTERNAL' in str(o.get('source', '')).upper()]
        external = [o for o in openings if o not in internal]
        put('ext_open', sum(o['area'] for o in external), 'derived', ', '.join(f'{o["label"]} ×{o["count"]}' for o in external) or 'none')
        put('int_open', sum(o['area'] for o in internal), 'derived' if internal else 'typical',
            ', '.join(f'{o["label"]} ×{o["count"]}' for o in internal) or 'No internal doors in the schedule')
    else:
        put('ext_open', 0.12 * 2 * (L + W) * H, 'typical', 'Typical: 12% of the outer wall face')
        n = max(len(rooms) - 1, 3)
        put('int_open', n * 0.9 * 2.1, 'typical', f'Typical: {n} internal doors of 0.9 × 2.1 m')
    v, s = _ev(schedule, 'slab_area')
    put('slab_area', v or L * W, 'drawing' if v else ('derived' if inp['length']['source'] == 'drawing' else 'typical'), s or 'Length × width')
    v, s = _ev(schedule, 'slab_thickness')
    put('slab_thick', v or 0.125, 'drawing' if v else 'typical', s or 'Typical 125 mm residential slab')
    tile, parts = _tile_wall_area(schedule)
    if parts:
        put('wall_tile', tile, 'derived', '; '.join(parts))
    else:
        put('wall_tile', 0, 'typical', 'No kitchen/bathroom found – enter the tiled wall area if any')
    v, s = _ev(schedule, 'roof_waterproof_area')
    put('roof_wp', v or inp['slab_area']['value'], 'drawing' if v else ('typical' if inp['slab_area']['source'] == 'typical' else 'derived'), s or 'Same as roof slab area')
    v, s = _ev(schedule, 'plinth_height')
    put('plinth_h', v or 0.45, 'drawing' if v else 'typical', s or 'Typical 450 mm (1.5 ft) above ground')
    v, s = _ev(schedule, 'parapet_height')
    put('parapet_h', v if v is not None else 0.9, 'drawing' if v else 'typical', s or 'Typical 0.9 m parapet on the top roof (0 = none)')
    # keep the user-facing order of FIELDS
        # Preliminary frame - always typical values (the plan does not give structural sizes).
    cols = (math.ceil(L / 4) + 1) * (math.ceil(W / 4) + 1)
    put('columns', cols, 'typical', 'About one column every 4 m each way. Use the structural drawing count')
    for k, v, note in (('col_b', 0.23, '230 mm'), ('col_d', 0.30, '300 mm'), ('ftg_l', 1.2, '1.2 m'),
                       ('ftg_w', 1.2, '1.2 m'), ('ftg_t', 0.30, '300 mm'), ('fdn_depth', 1.5, '1.5 m'),
                       ('beam_b', 0.23, '230 mm'), ('beam_d', 0.30, '300 mm')):
        put(k, v, 'typical', f'Common size {note} – for quantity only, NOT a design')
    return OrderedDict((f[0], inp[f[0]]) for f in FIELDS if f[0] in inp)


def summary_counts(inp):
    found = sum(1 for k, v in inp.items() if FIELD[k][4] in MEASURED_GROUPS and v['source'] in ('drawing', 'derived'))
    check = sum(1 for k, v in inp.items() if FIELD[k][4] in MEASURED_GROUPS and v['source'] == 'typical')
    return found, check


def parse_form(form, base_inputs):
    """Merge submitted values into the inputs. A changed value becomes 'user'. Raises ValueError."""
    inp = OrderedDict((k, dict(v)) for k, v in base_inputs.items())
    for key, en, ta, unit, group, lo, hi, step in FIELDS:
        raw = str(form.get(key, '') or '').strip()
        if raw == '':
            continue
        try:
            v = float(raw)
        except ValueError:
            raise ValueError(f'{en}: enter a number')
        if not math.isfinite(v) or v < lo or v > hi:
            raise ValueError(f'{en}: must be between {lo:g} and {hi:g} {unit}')
        if key in ('floors', 'columns'):
            if v != int(v):
                raise ValueError(f'{en}: whole number only')
        if abs(v - inp[key]['value']) > 5e-4:          # shown rounded to 3 decimals
            inp[key] = {'value': v, 'source': 'user', 'note': 'Entered by you'}
    return inp


def parse_options(form):
    basis = normalise_basis(form.get('basis') or 'centreline')
    mode = form.get('rcc_mode') if form.get('rcc_mode') in ('rmc', 'site') else 'rmc'
    try:
        waste = float(form.get('waste') or 5)
    except ValueError:
        raise ValueError('Wastage: enter a number')
    if not 0 <= waste <= 30:
        raise ValueError('Wastage must be between 0 and 30%')
    steel = {}
    for key, label, default in STEEL_RULES:
        try:
            v = float(form.get(key) or default)
        except ValueError:
            raise ValueError(f'Steel for {label}: enter a number')
        if not 0 <= v <= 400:
            raise ValueError(f'Steel for {label}: 0 – 400 kg/m³')
        steel[key] = v
    return {'basis': basis, 'rcc_mode': mode, 'waste': waste, 'frame': form.get('frame', 'yes') == 'yes', 'steel': steel}


def default_options():
    return {'basis': 'centreline', 'rcc_mode': 'rmc', 'waste': 5.0, 'frame': True,
            'steel': {k: d for k, _, d in STEEL_RULES}}


def _scale(items, f):
    out = []
    for it in items:
        it = dict(it)
        q = float(it.get('quantity') or 0) * f
        it['quantity'] = int(q) if isinstance(it.get('quantity'), int) else round(q, 3)
        out.append(it)
    return out


LINTEL_DEPTH = 0.15          # m, RCC lintel over every door / window
LINTEL_BEARING = 0.15        # m each side
STAIR_M3_PER_FLOOR = 2.5     # typical dog-legged stair concrete per floor-to-floor flight (planning only)


def _is_internal(o):
    return 'D2' in str(o.get('label', '')).upper() or 'INTERNAL' in str(o.get('source', '')).upper()


def lintel_runs(schedule, v):
    """(external lintel length, internal lintel length, note) from the opening schedule, else typical."""
    openings = (schedule or {}).get('openings') or []
    if openings:
        ext = sum(float(o.get('count') or 0) * (float(o.get('width') or 0) + 2 * LINTEL_BEARING) for o in openings if not _is_internal(o))
        intl = sum(float(o.get('count') or 0) * (float(o.get('width') or 0) + 2 * LINTEL_BEARING) for o in openings if _is_internal(o))
        return ext, intl, 'From the door/window schedule: (opening width + 2 × 150 mm bearing) × count'
    n_ext = round(v['ext_open'] / 1.44) if v['ext_open'] > 0 else 0       # typical 1.2 × 1.2 m window
    n_int = round(v['int_open'] / (0.9 * 2.1)) if v['int_open'] > 0 else 0
    return (n_ext * (1.2 + 2 * LINTEL_BEARING), n_int * (0.9 + 2 * LINTEL_BEARING),
            f'Typical: {n_ext} window(s) 1.2 m wide and {n_int} door(s) 0.9 m wide, + 150 mm bearing each side')


def carpet_area(v):
    """Floor area INSIDE the walls (tiles, ceiling plaster/paint, plinth filling) - never the gross L × W."""
    L, W, te, ti = v['length'], v['width'], v['ext_thick'], v['int_thick']
    inner = (L - 2 * te) * (W - 2 * te) - v['int_length'] * ti
    if inner <= 0:
        return v['floor_area']
    return min(v['floor_area'], inner)


def column_split(L, W, n):
    """How many of n columns stand in external walls and how many in internal walls (4 m grid)."""
    nx, ny = math.ceil(L / 4) + 1, math.ceil(W / 4) + 1
    ext = min(n, 2 * (nx + ny) - 4)
    return ext, max(n - ext, 0)


def estimate(inp, opts, takeoff, schedule=None, frame_rows=True, ground=True):
    """Pure calculation. Returns dict(rows, breakdown, notes, skipped, frame).

    v3.7.0 corrections (checked by hand, see test_v370_calc.py):
      * brickwork is net of RCC beams (drop below slab), columns standing in the walls and lintels
        when the RCC frame is included (no concrete counted twice);
      * floor beams are measured below the slab only (the slab already contains the top part);
      * floor tiles, bedding mortar, ceiling plaster/paint and plinth filling use the CARPET area
        (inside the walls), not the gross length × width;
      * the 50 mm mortar "screed" is replaced by a 20 mm 1:4 tile bedding mortar;
      * added: lintels, plinth filling + PCC flooring base (ground floor), parapet on the top
        roof, staircase for G+1 and above, columns up to plinth level.
    frame_rows=False / ground=False are used by the multi-drawing estimate (one call per floor).
    """
    from intelligent_recognition import calculate
    v = {k: x['value'] for k, x in inp.items()}
    L, W, H, F = v['length'], v['width'], v['height'], int(v['floors'])
    te, ti, waste, mode = v['ext_thick'], v['int_thick'], opts['waste'], opts['rcc_mode']
    st = v['slab_thick']
    plinth_h = v.get('plinth_h', 0) or 0
    parapet_h = v.get('parapet_h', 0) or 0
    ev = (schedule or {}).get('evidence') or {}
    ept = (ev.get('external_plaster_thickness') or {}).get('value') or 0.015
    ipt = (ev.get('internal_plaster_thickness') or {}).get('value') or 0.012
    carpet = carpet_area(v)
    values = {'overall_length': L, 'overall_width': W, 'height': H, 'wall_thickness': te,
              'external_opening_area': v['ext_open'], 'measurement_basis': opts['basis'],
              'external_plaster_thickness': ept, 'internal_wall_length': v['int_length'] or None,
              'internal_thickness': ti, 'internal_opening_area': v['int_open'], 'internal_plaster_thickness': ipt,
              'floor_area': carpet, 'slab_area': v['slab_area'], 'slab_thickness': st,
              'waste': waste, 'rcc_mode': mode, 'opening_area': None}
    res = calculate(values, set(), set(), {'regions': [], 'lines': []}, takeoff)
    rows = [[label, area, items] for label, area, items in res['rows'] if label != 'Floor screed']
    notes = list(res['notes'])
    # Rows the Smart flow covers in its own way (net walls, plaster, paint, wall tiles below).
    skipped = [s for s in res['skipped'] if s not in ('Brick masonry (net of openings)', 'Plaster', 'Painting', 'Wall tiles', 'Floor screed')]
    breakdown = list(res['breakdown'])

    def run(label, work, area, depth, **kw):
        if not area or area <= 0 or not depth or depth <= 0:
            skipped.append(label)
            return None
        try:
            r = takeoff(work=work, length=area, width=1, depth=depth, unit='m', waste=waste, **kw)
        except ValueError as ex:
            skipped.append(f'{label}: {str(ex)[:90]}')
            return None
        rows.append([label, area, r['items']])
        return rows[-1]

    def steel_item(volume, rate, what):
        return {'material': 'Steel planning allowance (not BBS)', 'quantity': round(volume * rate * (1 + waste / 100), 3),
                'unit': 'kg', 'basis': f'Thumb rule {rate:g} kg/m³ × {volume:.3f} m³ ({what}); replace with approved BBS'}

    # floor tiles: no adhesive under floor tiles (laid on 20 mm cement mortar bed, below)
    for row in rows:
        if row[0] == 'Floor tiles':
            row[2] = [it for it in row[2] if it['material'] != 'Tile adhesive']
    run('Floor tile bedding mortar 1:4 – 20 mm', 'screed', carpet, 0.02, plaster_ratio='1:4')
    breakdown.append(('Carpet area inside walls (tiles, ceiling) per floor', carpet, 'm²'))

    # ---- masonry deductions: lintels always; beams + columns when the RCC frame is included
    ext_lin, int_lin, lin_note = lintel_runs(schedule, v)
    frame_on = bool(opts['frame'] and v['columns'] > 0)
    drop = max(v['beam_d'] - st, 0) if frame_on else 0.0
    n = int(v['columns']) if frame_on else 0
    ext_cols, int_cols = column_split(L, W, n) if frame_on else (0, 0)
    ded = {'ext': ext_lin * LINTEL_DEPTH, 'int': int_lin * LINTEL_DEPTH}
    try:
        P_basis = rectangle_perimeter_for(L, W, te, opts['basis'])
    except ValueError:
        P_basis = 0
    if frame_on:
        ded['ext'] += P_basis * drop + ext_cols * v['col_d'] * max(H - drop, 0)
        ded['int'] += v['int_length'] * drop + int_cols * v['col_d'] * max(H - drop, 0)
    for row in rows:
        kind = 'ext' if row[0].startswith('External masonry') else 'int' if row[0].startswith('Internal masonry') else None
        if not kind or ded[kind] <= 0:
            continue
        net = max(row[1] - ded[kind], row[1] * 0.1)
        thick = te if kind == 'ext' else ti
        try:
            row[2] = takeoff(work='brickwork', length=net, width=1, depth=thick, unit='m', waste=waste)['items']
        except ValueError:
            continue
        breakdown.append((f'{"External" if kind == "ext" else "Internal"} masonry face deducted (lintels' + (', beams, columns' if frame_on else '') + ')', ded[kind], 'm²'))
        row[0] = row[0] + (' – less lintels, beams & columns' if frame_on else ' – less lintels')
        row[1] = net
    lin_vol = ext_lin * te * LINTEL_DEPTH + int_lin * ti * LINTEL_DEPTH
    row = run('RCC lintels over doors & windows – preliminary', 'rcc', lin_vol, 1, rcc_mode=mode)
    if row:
        row[2] = list(row[2]) + [steel_item(lin_vol, 80, 'lintels')]
    breakdown.append(('Lintel length (external + internal)', ext_lin + int_lin, 'm'))
    notes.append(f'Lintels {LINTEL_DEPTH * 1000:.0f} mm deep: {lin_note}.')

    try:
        inner = wall_faces(L, W, te, H, v['ext_open'], 'internal')
        outer = wall_faces(L, W, te, H, v['ext_open'], 'external')
    except ValueError as ex:
        inner = outer = None
        notes.append('External wall finishes skipped: ' + str(ex))
    if inner:
        run('Inner face plaster of external walls', 'plaster', inner['net'], ipt)
        run('Painting – external walls (outer + inner face)', 'painting', outer['net'] + inner['net'], 0.001)
        breakdown.append(('External walls inner face (net)', inner['net'], 'm²'))
    run('Ceiling plaster', 'plaster', carpet, 0.006)
    run('Ceiling painting', 'painting', carpet, 0.001)
    wt = run('Wall tiles (kitchen / bathrooms)', 'flooring', v['wall_tile'], 0.01, tile_length=0.3, tile_width=0.3)
    if wt:
        for it in wt[2]:
            if it['material'] == 'Tiles':
                it['material'] = 'Wall tiles'
    for row in rows:
        if row[0].startswith('RCC slab'):
            row[2] = list(row[2]) + [steel_item(v['slab_area'] * st, opts['steel']['steel_slab'], 'slab')]
    # everything so far is per floor
    if F > 1:
        rows = [[f'{label} × {F} floors', area * F, _scale(items, F)] for label, area, items in rows]
        notes.append(f'Walls, finishes and slabs are multiplied by {F} floors (same plan on every floor assumed).')
    run('Roof waterproofing (top roof only)', 'waterproofing', v['roof_wp'], 0.001)
    if v['roof_wp'] > 0 and parapet_h > 0:          # top roof only
        P_par = 2 * (L + W) - 4 * ti
        run(f'Parapet wall on roof – {ti * 1000:.0f} mm brick, {parapet_h:g} m high', 'brickwork', P_par * parapet_h, ti)
        run('Parapet plaster – both faces', 'plaster', 2 * P_par * parapet_h, ipt)
        run('Parapet painting – both faces', 'painting', 2 * P_par * parapet_h, 0.001)
        breakdown.append(('Parapet length (centreline)', P_par, 'm'))
    if ground and plinth_h > 0:
        fill = max(plinth_h - 0.15, 0)
        run(f'Plinth filling inside the building – {fill:.2f} m deep', 'backfill', carpet, fill)
        run('PCC 1:4:8 flooring base – 100 mm (ground floor)', 'pcc', carpet, 0.1)
        breakdown.append(('Plinth height above ground', plinth_h, 'm'))

    frame = {}
    if frame_on and frame_rows:
        fl, fw, ft, D = v['ftg_l'], v['ftg_w'], v['ftg_t'], v['fdn_depth']
        cb, cd, bb, bd = v['col_b'], v['col_d'], v['beam_b'], v['beam_d']
        if ft >= D:
            raise ValueError('Footing thickness must be less than the foundation depth')
        pit = (fl + 0.3) * (fw + 0.3)
        exc = n * pit * D
        pcc = n * pit * 0.1
        ftg = n * fl * fw * ft
        col_below = n * cb * cd * max(D - ft - 0.1, 0)
        col_above = n * cb * cd * (F * (H + st) + plinth_h)
        beam_len = 2 * (L + W) - 4 * te + v['int_length']
        plinth = beam_len * bb * bd
        floor_beams = F * beam_len * bb * max(bd - st, 0)
        backfill = max(exc - pcc - ftg - col_below, 0)
        form = (n * 2 * (fl + fw) * ft + n * 2 * (cb + cd) * (D - ft - 0.1 + plinth_h + F * H)
                + beam_len * 2 * bd + F * beam_len * (2 * max(bd - st, 0) + bb))
        frame = {'columns': n, 'excavation': exc, 'pcc': pcc, 'footing': ftg, 'column': col_below + col_above,
                 'beam_length': beam_len, 'beams': plinth + floor_beams, 'backfill': backfill, 'formwork': form}
        run('Excavation for footings – preliminary', 'excavation', exc, 1)
        run('PCC 1:4:8 below footings – preliminary', 'pcc', pcc, 1)
        for label, vol, key in (('RCC footings – preliminary', ftg, 'steel_footing'),
                                ('RCC columns – preliminary', col_below + col_above, 'steel_column'),
                                ('RCC plinth beam – preliminary', plinth, 'steel_beam'),
                                (f'RCC floor/roof beams below slab – preliminary{f" ({F} floors)" if F > 1 else ""}', floor_beams, 'steel_beam')):
            row = run(label, 'rcc', vol, 1, rcc_mode=mode)
            if row:
                row[2] = list(row[2]) + [steel_item(vol, opts['steel'][key], label.split(' – ')[0])]
        run('Backfilling around footings – preliminary', 'backfill', backfill, 1)
        run('Formwork – footings, columns, beams – preliminary', 'shuttering', form, 0.01)
        breakdown += [('Columns (preliminary count)', n, 'nos'), ('Footing excavation', exc, 'm³'),
                      ('RCC footings', ftg, 'm³'), ('RCC columns', col_below + col_above, 'm³'),
                      ('Beam length per level (perimeter + internal walls)', beam_len, 'm'),
                      ('RCC beams (plinth + floors)', plinth + floor_beams, 'm³')]
        notes.append('STRUCTURE IS PRELIMINARY: column count, footing, column and beam sizes and steel kg/m³ are '
                     'typical planning values for quantity only. They are NOT a structural design. '
                     'DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.')
    if frame_rows and F > 1:
        sv = (F - 1) * STAIR_M3_PER_FLOOR
        row = run(f'RCC staircase – preliminary ({F - 1} flight set(s), typical {STAIR_M3_PER_FLOOR:g} m³ each)', 'rcc', sv, 1, rcc_mode=mode)
        if row:
            row[2] = list(row[2]) + [steel_item(sv, 100, 'staircase')]
        run('Staircase formwork – preliminary', 'shuttering', (F - 1) * 18, 0.01)
        notes.append('Staircase is a typical planning quantity. Use the measured stair drawing for the real figure.')
    if not frame_on:
        notes.append('RCC frame not included: foundations for load-bearing walls are not in this estimate.')
    breakdown.insert(0, ('Number of floors', F, 'nos'))
    breakdown.insert(1, ('Built-up area (all floors)', L * W * F, 'm²'))
    return {'rows': rows, 'breakdown': breakdown, 'notes': notes, 'skipped': skipped, 'frame': frame,
            'basis_label': BASES[opts['basis']], 'builtup_sqft': L * W * F * SQFT_PER_M2}


def rectangle_perimeter_for(L, W, t, basis):
    from measurement import rectangle_perimeter
    return rectangle_perimeter(L, W, t, basis)['perimeter']


def build_payload(project, drawing, inp, opts, result, schedule):
    typical = [FIELD[k][1] for k, x in inp.items() if x['source'] == 'typical' and (opts['frame'] or FIELD[k][4] != 'frame')]
    notes = []
    if typical:
        notes.append(f'{len(typical)} value(s) were TYPICAL ASSUMPTIONS, not read from the drawing: ' + ', '.join(typical) + '. Check them.')
    notes += result['notes'] + list((schedule or {}).get('warnings') or [])
    return {
        'drawing_id': drawing['id'], 'drawing_name': drawing['original_name'], 'project_id': project['id'],
        'source': 'smart_estimate_v260', 'status': 'DRAFT – ASSUMPTIONS REQUIRE VERIFICATION',
        'measurement_basis': opts['basis'], 'measurement_basis_label': result['basis_label'],
        'rows': [{'work': label, 'area': area, 'items': items} for label, area, items in result['rows']],
        'breakdown': [{'measurement': n, 'quantity': q, 'unit': u} for n, q, u in result['breakdown']],
        'rooms': (schedule or {}).get('rooms', []), 'openings': (schedule or {}).get('openings', []),
        'notes': notes, 'skipped': result['skipped'], 'provisional': True,
        'inputs': [{'key': k, 'label': FIELD[k][1], 'value': x['value'], 'unit': FIELD[k][3], 'source': x['source'], 'note': x['note']}
                   for k, x in inp.items()],
        'options': opts, 'floors': int(inp['floors']['value']), 'builtup_sqft': round(result['builtup_sqft'], 2),
        'cost_extras': {'labour': 0, 'transport': 0, 'other': 0, 'tax_percent': 0},
    }


# ------------------------------------------------------------------ web pages
def register_smart_estimate_v260(app, db, owned_project, require, csrf, check_csrf, layout, esc, FILES, takeoff, store_upload):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    from ui_shell import icon
    import rates_v260

    def drawings_of(pid):
        with db() as c:
            return [r for r in c.execute('SELECT * FROM uploads WHERE project_id=? ORDER BY created DESC', (pid,)).fetchall()
                    if str(r['original_name']).lower().endswith(DRAWING_EXT)]

    def drawing_row(pid, fid):
        with db() as c:
            r = c.execute('SELECT * FROM uploads WHERE id=? AND project_id=?', (fid, pid)).fetchone()
        if not r:
            raise HTTPException(404, 'Drawing not found')
        return r

    def read_schedule(r):
        if r is None:
            return {'evidence': {}, 'rooms': [], 'openings': [], 'warnings': [], 'method': 'No drawing – sizes entered by you'}
        path = FILES / r['stored_name']
        if path.suffix.lower() not in DRAWING_EXT or not path.is_file():
            return {'evidence': {}, 'rooms': [], 'openings': [], 'warnings': ['This file type cannot be read; enter sizes below.'], 'method': 'not readable'}
        try:
            from drawing_schedule import extract
            return extract(path, 0)
        except Exception as ex:   # missing OCR/DXF library or unreadable drawing: everything becomes manual
            return {'evidence': {}, 'rooms': [], 'openings': [], 'method': 'unavailable',
                    'warnings': [f'Could not read the drawing automatically ({type(ex).__name__}). Enter the sizes below.']}

    def project_sqft(p):
        return float(p['area'] or 0)

    def steps_bar(active):
        names = ['Choose drawing', 'Check measurements', 'Estimate ready']
        return '<div class="cv-mini-steps">' + ''.join(
            f'<span class="{"on" if i == active else ("done" if i < active else "")}"><b>{i + 1}</b>{n}</span>' for i, n in enumerate(names)) + '</div>'

    @app.get('/projects/{pid}/smart')
    def smart_start(request: Request, pid: str):
        p = owned_project(request, pid)
        P = f'/projects/{pid}'
        cards = ''.join(f'''<a class="cv-pick" href="{P}/smart/{esc(r["id"])}"><span class="cv-pickimg"><img loading="lazy" src="{P}/drawings/{esc(r["id"])}/media" alt=""></span>
<span class="cv-pickt"><b>{esc(r["original_name"])}</b><small>Uploaded {time.strftime("%d %b %Y", time.localtime(r["created"]))}</small></span><span class="cv-btn sm">Use this {icon("arrow", 15)}</span></a>''' for r in drawings_of(pid))
        existing = f'<h2 style="margin:26px 0 10px">Or use a drawing already in this project</h2><div class="cv-picks">{cards}</div>' if cards else ''
        return layout(request, 'Smart Estimate', f'''<span class="eyebrow">SMART ESTIMATE · {esc(p["name"])}</span><h1>Get a full estimate from your drawing</h1>
<p class="muted">Civora reads the sizes from your plan and only asks for what is missing. Walls, plaster, paint, tiles, slab, roof, columns, footings, steel and cost — in one go.</p>
{steps_bar(0)}
<form class="cv-drop" method="post" action="{P}/smart/upload" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{csrf(request)}">
{icon("upload", 40)}<b>Upload your building plan</b><span>PDF, DXF (CAD), PNG or JPG · up to 30 MB</span>
<input type="file" name="file" accept=".pdf,.dxf,.png,.jpg,.jpeg" required><button class="cv-btn">{icon("arrow", 16)} Upload &amp; read drawing</button>
<small>Best results: DXF or a PDF exported from CAD. Photos and scans work, but more values will need checking.</small></form>
<p class="notice" style="margin:14px 0 0">{icon("layers", 16)} Several drawings (ground floor, first floor, sections)? <a href="{P}/multi"><b>Analyse them together</b></a> for one combined estimate.</p>
{existing}
<div class="cv-row" style="margin-top:22px"><form class="cv-card" method="post" action="{P}/quick"><input type="hidden" name="csrf_token" value="{csrf(request)}">
<h3>{icon("calc", 18)} Only know the area?</h3><p class="sub">Quick Estimate uses {float(p["area"] or 0):,.0f} sq.ft (this project's built-up area) with typical sizes.</p>
<div class="cv-fin"><select name="floors" aria-label="Floors"><option value="1">G (ground)</option><option value="2">G + 1</option><option value="3">G + 2</option><option value="4">G + 3</option></select><button class="cv-btn sm">Quick estimate {icon("arrow", 15)}</button></div></form>
<div class="cv-card"><h3>{icon("drawing", 18)} Know the sizes?</h3><p class="sub">Enter length, width, height and wall details yourself.</p><a class="cv-btn sm ghost" href="{P}/smart/manual">Enter sizes {icon("arrow", 15)}</a></div></div>''')

    @app.post('/projects/{pid}/smart/upload')
    async def smart_upload(request: Request, pid: str):
        owned_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        f = form.get('file')
        if f is None or not hasattr(f, 'read'):
            raise HTTPException(400, 'Choose a drawing file')
        name = getattr(f, 'filename', '') or 'drawing'
        if not name.lower().endswith(DRAWING_EXT):
            raise HTTPException(400, 'Upload a PDF, DXF, PNG or JPG drawing')
        content = await f.read(30 * 1024 * 1024 + 1)
        fid = store_upload(pid, name, content, getattr(f, 'content_type', None))
        return RedirectResponse(f'/projects/{pid}/smart/{fid}', 303)

    def review_page(request, p, r, schedule, inp, opts, error=''):
        pid = p['id']
        P = f'/projects/{pid}'
        fid = r['id'] if r is not None else 'manual'
        found, check = summary_counts(inp)
        chip = {'drawing': ('cv-src d', 'From drawing'), 'derived': ('cv-src w', 'Worked out'),
                'typical': ('cv-src t', 'Please check'), 'user': ('cv-src u', 'Your value')}
        groups = ''
        for g, en, ta in GROUPS:
            fields = ''
            for key, fen, fta, unit, grp, lo, hi, step in FIELDS:
                if grp != g:
                    continue
                x = inp[key]
                cls, txt = chip[x['source']]
                val = ("%.3f" % x["value"]).rstrip("0").rstrip(".") if step < 1 else f'{int(round(x["value"]))}'
                fields += (f'<div class="cv-field {"need" if x["source"] == "typical" else ""}"><label for="f_{key}"><b>{esc(fen)}</b><small>{esc(fta)}</small></label>'
                           f'<div class="cv-fin"><input id="f_{key}" name="{key}" type="number" min="{lo:g}" max="{hi:g}" step="{"1" if step >= 1 else "any"}" value="{val}"><span>{esc(unit)}</span></div>'
                           f'<div class="cv-fsrc"><span class="{cls}">{txt}</span><small title="{esc(x["note"])}">{esc(x["note"])[:110]}</small></div></div>')
            if g == 'frame':
                groups += (f'<section class="cv-card cv-group"><h3>{esc(en)}<small>{esc(ta)}</small></h3>'
                           f'<label class="checkline"><input type="checkbox" name="frame" value="yes" {"checked" if opts["frame"] else ""}> Include RCC frame (columns, beams, footings) in the estimate</label>'
                           f'<input type="hidden" name="frame_present" value="1">'
                           f'<div class="cv-review" style="margin:10px 0">{icon("shield", 16)}<span>These sizes are common values for QUANTITY only. A licensed engineer must design the actual structure. DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.</span></div>{fields}</section>')
            else:
                groups += f'<section class="cv-card cv-group"><h3>{esc(en)}<small>{esc(ta)}</small></h3>{fields}</section>'
        steel = ''.join(f'<div class="cv-field"><label for="f_{k}"><b>Steel in {esc(lb)}</b><small>thumb rule</small></label><div class="cv-fin"><input id="f_{k}" name="{k}" type="number" min="0" max="400" step="any" value="{opts["steel"][k]:g}"><span>kg/m³</span></div><div></div></div>' for k, lb, _ in STEEL_RULES)
        basis_opts = ''.join(f'<option value="{k}"{" selected" if k == opts["basis"] else ""}>{esc(lbl)}</option>' for k, lbl in BASES.items())
        advanced = f'''<details class="cv-card cv-group"><summary><b>Advanced settings</b> <small>(for engineers – defaults are fine for most users)</small></summary>
<div class="cv-field"><label><b>Concrete supply</b><small>கான்கிரீட்</small></label><div class="cv-fin"><select name="rcc_mode"><option value="rmc"{" selected" if opts["rcc_mode"] == "rmc" else ""}>Ready-mix (RMC)</option><option value="site"{" selected" if opts["rcc_mode"] == "site" else ""}>Site mix M20 (cement, M-sand, jelly)</option></select></div><div></div></div>
<div class="cv-field"><label><b>Brickwork measured on</b><small>அளவீட்டு முறை</small></label><div class="cv-fin"><select name="basis">{basis_opts}</select></div><div></div></div>
<div class="cv-field"><label for="f_waste"><b>Wastage</b><small>வீணாகும் அளவு</small></label><div class="cv-fin"><input id="f_waste" name="waste" type="number" min="0" max="30" step="any" value="{opts["waste"]:g}"><span>%</span></div><div></div></div>{steel}</details>'''
        thumb = (f'<img src="{P}/drawings/{esc(r["id"])}/media" alt="">' if r is not None else icon('drawing', 54))
        err = f'<div class="cv-review" style="margin:12px 0;background:#fef2f2;border-color:#fecaca;color:#991b1b">{esc(error)}</div>' if error else ''
        warn = ''.join(f'<p class="hint">{esc(w)}</p>' for w in (schedule.get('warnings') or []))
        head = (f'<b>{found}</b> measurement(s) read from your drawing. <b>{check}</b> need your check — they are filled with typical values and highlighted.'
                if r is not None else f'No drawing used. All {check} values start as typical values — replace them with your building sizes.')
        return layout(request, 'Smart Estimate – check measurements', f'''<span class="eyebrow">SMART ESTIMATE · {esc(p["name"])}</span><h1>Check the measurements</h1>
{steps_bar(1)}{err}
<div class="cv-card cv-sumbox"><div class="cv-sumimg">{thumb}</div><div><h3>{esc(r["original_name"]) if r is not None else "Manual sizes"}</h3>
<p>{head}</p><p class="sub">Read by: {esc(schedule.get("method", ""))}</p>
<div class="cv-legend2"><span class="cv-src d">From drawing</span><span class="cv-src w">Worked out</span><span class="cv-src t">Please check</span><span class="cv-src u">Your value</span></div>{warn}
{f'<p style="margin:10px 0 0"><a class="cv-btn sm ghost" href="{P}/vastu/drawing/{esc(r["id"])}">{icon("pin", 15)} Check Vastu for this drawing</a></p>' if r is not None else ''}</div></div>
<form method="post" action="{P}/smart/{esc(fid)}"><input type="hidden" name="csrf_token" value="{csrf(request)}">
<div class="cv-groups">{groups}</div>{advanced}
<div class="cv-stickybar"><span>Quantities, steel and cost will be calculated and saved as a draft BOQ.</span><button class="cv-btn">{icon("calc", 17)} Calculate full estimate</button></div></form>''')

    def _load(request, pid, fid):
        p = owned_project(request, pid)
        r = None if fid == 'manual' else drawing_row(pid, fid)
        schedule = read_schedule(r)
        return p, r, schedule, build_inputs(schedule, project_sqft(p))

    @app.get('/projects/{pid}/smart/{fid}')
    def smart_review(request: Request, pid: str, fid: str):
        p, r, schedule, inp = _load(request, pid, fid)
        return review_page(request, p, r, schedule, inp, default_options())

    @app.post('/projects/{pid}/smart/{fid}')
    async def smart_calculate(request: Request, pid: str, fid: str):
        u = require(request)
        p, r, schedule, base = _load(request, pid, fid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        fd = {k: form.get(k) for k in form.keys()}
        if 'frame_present' in fd and 'frame' not in fd:
            fd['frame'] = 'no'
        try:
            inp = parse_form(fd, base)
            opts = parse_options(fd)
            result = estimate(inp, opts, takeoff, schedule)
        except ValueError as ex:
            return review_page(request, p, r, schedule, base, default_options(), error=str(ex))
        import preview_v370
        if not preview_v370.confirmed(form):     # v3.7.0: preview first, save only on confirm
            draw = r if r is not None else {'id': 'manual', 'original_name': 'Manual sizes'}
            pv = build_payload(p, draw, inp, opts, result, schedule)
            with db() as c:
                rates = rates_v260.rates_for_project(c, p, u['id'])
            if any(v > 0 for v in rates.values()):
                rates_v260.apply_rates(pv, rates, pv['builtup_sqft'])
            return preview_v370.gate(request, form, layout, csrf(request), f'Smart Estimate – {p["name"]}',
                                     preview_v370.boq_summary_html(pv, esc), f'/projects/{pid}/smart/{fid}', esc, 'Save estimate')
        if r is None:
            # No drawing: keep the entered sizes as a small CSV in the project so the BOQ has a source file.
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(['Item', 'Value', 'Unit', 'Source'])
            for k, x in inp.items():
                w.writerow([FIELD[k][1], x['value'], FIELD[k][3], SOURCE_LABEL[x['source']]])
            fid = store_upload(pid, 'Manual_sizes.csv', out.getvalue().encode('utf-8'), 'text/csv')
            r = drawing_row(pid, fid)
        payload = build_payload(p, r, inp, opts, result, schedule)
        with db() as c:
            rates = rates_v260.rates_for_project(c, p, u['id'])
            if any(v > 0 for v in rates.values()):
                rates_v260.apply_rates(payload, rates, payload['builtup_sqft'])
            bid = str(uuid.uuid4())
            c.execute('INSERT INTO civora_boq_reports(id,project_id,drawing_id,payload,created) VALUES(?,?,?,?,?)',
                      (bid, pid, r['id'], json.dumps(payload, ensure_ascii=False), int(time.time())))
        return RedirectResponse(f'/projects/{pid}/workflow?estimate={bid}', 303)
