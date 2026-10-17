"""Civora AI v2.6.0 - Rate Master.

Each user saves their local rates once (cement bag, sand, steel, bricks, labour per sq.ft ...).
Smart Estimate applies them automatically; any saved BOQ can be re-priced with one click.
Table (new, additive): civora_rate_master_v260(user_id, key, rate, updated).
"""
import json
import math
import time

# key, English, Tamil, unit shown to the user, group
RATE_ITEMS = [
    ('cement_bag', 'Cement', 'சிமெண்ட்', 'per 50 kg bag', 'material'),
    ('sand', 'Sand (river / P-sand)', 'மணல்', 'per m³', 'material'),
    ('msand', 'M-sand', 'எம்-சாண்ட்', 'per m³', 'material'),
    ('aggregate', '20 mm jelly / aggregate', 'ஜல்லி', 'per m³', 'material'),
    ('rmc', 'Ready-mix concrete (RMC)', 'ரெடிமிக்ஸ் கான்கிரீட்', 'per m³', 'material'),
    ('steel', 'Steel / TMT bars', 'கம்பி (TMT)', 'per kg', 'material'),
    ('brick', 'Red brick', 'செங்கல்', 'per brick', 'material'),
    ('aac_block', 'AAC block', 'ஏஏசி பிளாக்', 'per block', 'material'),
    ('aac_adhesive_bag', 'AAC adhesive', 'ஏஏசி ஒட்டு பசை', 'per 40 kg bag', 'material'),
    ('tile', 'Floor tile', 'தரை டைல்ஸ்', 'per tile', 'material'),
    ('wall_tile', 'Wall tile (kitchen / bathroom)', 'சுவர் டைல்ஸ்', 'per tile', 'material'),
    ('tile_adhesive', 'Tile adhesive', 'டைல் ஒட்டு பசை', 'per kg', 'material'),
    ('paint', 'Paint', 'பெயிண்ட்', 'per litre', 'material'),
    ('primer', 'Primer', 'பிரைமர்', 'per litre', 'material'),
    ('waterproofing', 'Waterproofing material', 'நீர்க்காப்பு பொருள்', 'per kg', 'material'),
    ('putty', 'Wall putty', 'சுவர் புட்டி', 'per kg', 'material'),
    # v3.9.0: labour for every work item (no material) - item-wise labour replaces the per sq.ft lump sum
    ('lab_pcc', 'PCC laying', 'பிசிசி கூலி', 'per m³', 'labour'),
    ('lab_rcc', 'RCC concreting (mix, pour, vibrate, cure)', 'கான்கிரீட் கூலி', 'per m³', 'labour'),
    ('lab_steel', 'Bar bending & fixing', 'கம்பி கட்டும் கூலி', 'per kg', 'labour'),
    ('lab_brick', 'Brick / block masonry', 'கட்டு வேலை கூலி', 'per m³', 'labour'),
    ('lab_plaster', 'Plastering', 'பூச்சு கூலி', 'per m²', 'labour'),
    ('lab_floor_tile', 'Floor tile laying', 'தரை டைல்ஸ் கூலி', 'per m²', 'labour'),
    ('lab_wall_tile', 'Wall tile laying', 'சுவர் டைல்ஸ் கூலி', 'per m²', 'labour'),
    ('lab_paint', 'Painting (putty, primer, 2 coats)', 'பெயிண்ட் கூலி', 'per m²', 'labour'),
    ('lab_waterproof', 'Waterproofing application', 'நீர்க்காப்பு கூலி', 'per m²', 'labour'),
    # v3.9.0: doors, windows, services and fixed items
    ('door_main', 'Main door (teak, with frame & fittings)', 'தலைவாசல் கதவு', 'per door', 'services'),
    ('door_internal', 'Internal door (flush, with frame)', 'உள் கதவு', 'per door', 'services'),
    ('door_toilet', 'Toilet door (WPC / PVC)', 'கழிவறை கதவு', 'per door', 'services'),
    ('window_m2', 'Windows & ventilators (UPVC / aluminium, glass)', 'ஜன்னல்', 'per m²', 'services'),
    ('grill_m2', 'Window grills (MS)', 'ஜன்னல் கிரில்', 'per m²', 'services'),
    ('electrical_sqft', 'Electrical (wiring, points, MCB, basic fittings)', 'மின்சார வேலை', 'per sq.ft built-up', 'services'),
    ('plumbing_sqft', 'Plumbing & sanitary (pipes, WC, basin, taps)', 'பிளம்பிங் & சானிடரி', 'per sq.ft built-up', 'services'),
    ('kitchen_platform', 'Kitchen granite platform & sink', 'சமையலறை மேடை', 'per kitchen', 'services'),
    ('sump', 'Sump (underground tank)', 'சம்ப்', 'per house', 'services'),
    ('septic', 'Septic tank', 'செப்டிக் டேங்க்', 'per house', 'services'),
    ('oh_tank', 'Overhead tank 1000 L with stand', 'மேல்நிலை தொட்டி', 'per house', 'services'),
    ('formwork', 'Shuttering / centring', 'சென்டரிங்', 'per m²', 'work'),
    ('excavation', 'Excavation', 'மண் தோண்டுதல்', 'per m³', 'work'),
    ('backfill', 'Backfilling', 'மண் நிரப்புதல்', 'per m³', 'work'),
    ('labour_sqft', 'Labour lump sum (only if NOT using item-wise labour)', 'கூலி (மொத்தம்)', 'per sq.ft built-up', 'charge'),
    ('transport_pct', 'Transport', 'போக்குவரத்து', '% of material cost', 'charge'),
    ('contingency_pct', 'Contingency / sundries', 'எதிர்பாராத செலவு', '% of total', 'charge'),
    ('contractor_pct', 'Contractor margin / supervision', 'ஒப்பந்ததாரர் லாபம்', '% of total', 'charge'),
    ('tax_percent', 'GST / tax', 'வரி', '%', 'charge'),
]
RATE_KEYS = [k for k, *_ in RATE_ITEMS]
LABEL = {k: en for k, en, *_ in RATE_ITEMS}

# v3.8.0: Tamil Nadu average market rates (Chennai / Trichy / Madurai dealer-to-retail midpoints,
# infralens.in price pages updated 12 Aug 2026; indialandconverter.in Trichy). Bulk density used to
# convert per-tonne prices: sand 1.6 t/m³, 20 mm aggregate 1.5 t/m³. Items marked ~ are typical
# trade figures (no published TN average) - every value is editable in the Rate Master.
MARKET_AS_OF = 'Tamil Nadu average · Aug–Oct 2026'
MARKET_RATES = {
    'cement_bag': 400,        # OPC 53 ~₹421, PPC ~₹389 per 50 kg bag
    'sand': 2750,             # P-sand ~₹1,717/t
    'msand': 2270,            # M-sand ~₹1,418/t
    'aggregate': 1900,        # 20 mm ~₹1,271/t
    'rmc': 4950,              # RMC M20 ~₹4,934/m³
    'steel': 60,              # Fe500D 12 mm ~₹60/kg
    'brick': 11,              # red clay 9x4x3"
    'aac_block': 78,          # 600x200x200 mm
    'aac_adhesive_bag': 480,  # ~ 40 kg bag
    'tile': 345,              # vitrified 600x600 (3.87 sq.ft x ~₹89)
    'wall_tile': 39,          # ceramic 300x300 (0.97 sq.ft x ~₹40)
    'tile_adhesive': 14,      # ~ per kg
    'paint': 285,             # interior/exterior emulsion average
    'primer': 110,
    'waterproofing': 150,     # ~ per kg (polymer / cementitious)
    'formwork': 450,          # ~ per m² contact area (material + labour)
    'excavation': 350,        # ~ per m³ (manual, ordinary soil)
    'backfill': 250,          # ~ per m³
    'putty': 23,              # wall putty per kg
    # labour per unit = daily wages (mason ₹894, helper ₹618, bar bender ₹877, tile layer ₹924, painter ₹747)
    # / usual daily output (CPWD-type outputs); brickwork falls in the ₹1,000–2,200/m³ trade range
    'lab_pcc': 800, 'lab_rcc': 1000, 'lab_steel': 7, 'lab_brick': 1600, 'lab_plaster': 200,
    'lab_floor_tile': 200, 'lab_wall_tile': 260, 'lab_paint': 180, 'lab_waterproof': 60,
    # doors / windows / services: infralens Chennai item prices + frame, hardware and fixing (~ typical)
    'door_main': 28000, 'door_internal': 9000, 'door_toilet': 7500, 'window_m2': 6000, 'grill_m2': 2000,
    'electrical_sqft': 130, 'plumbing_sqft': 120, 'kitchen_platform': 30000,
    'sump': 90000, 'septic': 70000, 'oh_tank': 12000,
    'labour_sqft': 0,         # item-wise labour above is used instead
    'transport_pct': 3, 'contingency_pct': 3, 'contractor_pct': 10,
    'tax_percent': 0,         # dealer prices above already include GST
}
PERCENT_KEYS = {'transport_pct', 'tax_percent', 'contingency_pct', 'contractor_pct'}

_SIMPLE = {
    'Sand': 'sand', 'M-sand': 'msand', 'Coarse aggregate': 'aggregate', 'Ready-mix concrete (RMC)': 'rmc',
    'Steel planning allowance (not BBS)': 'steel', 'Reinforcement steel': 'steel', 'Bricks': 'brick',
    'AAC blocks': 'aac_block', 'AAC adhesive 40 kg bags': 'aac_adhesive_bag', 'Tiles': 'tile', 'Wall tiles': 'wall_tile',
    'Tile adhesive': 'tile_adhesive', 'Paint': 'paint', 'Primer': 'primer', 'Formwork contact area': 'formwork',
    'Excavated earth (in-situ volume)': 'excavation', 'Compacted backfill': 'backfill',
    'Waterproofing material': 'waterproofing', 'Wall putty (2 coats)': 'putty',
}
_VOLUME_ONLY = {'msand', 'aggregate'}       # site-mix "approved design" rows can be in kg - not priced per m³


def rate_key_for(item):
    """Which Rate Master entry prices this BOQ line (None = not priced automatically)."""
    name = str(item.get('material', '')).strip()
    unit = str(item.get('unit', '')).lower()
    if name in ('Cement', 'Cement 50 kg bags'):
        # Site-mix RCC lists cement both in kg and as bags; only the bag line is priced.
        return 'cement_bag' if 'bag' in unit else None
    key = _SIMPLE.get(name)
    if key in _VOLUME_ONLY and 'm³' not in unit:
        return None
    return key


def _f(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def init(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS civora_rate_master_v260 (
            user_id TEXT NOT NULL, key TEXT NOT NULL, rate REAL NOT NULL, updated INTEGER NOT NULL,
            PRIMARY KEY(user_id, key))''')


def load_rates(c, user_id):
    rows = c.execute('SELECT key, rate FROM civora_rate_master_v260 WHERE user_id=?', (user_id,)).fetchall()
    return {r[0]: float(r[1]) for r in rows if r[0] in RATE_KEYS}


def effective_rates(saved):
    """v3.8.0: market default for every rate the user has not saved; a saved value (even 0) wins."""
    out = dict(MARKET_RATES)
    out.update({k: v for k, v in (saved or {}).items() if k in RATE_KEYS})
    return out


def rates_for_project(c, project, user_id):
    """v2.7 team rule: a shared project is priced with the OWNER's Rate Master; if the owner
    has not saved any rates yet, the rates of the person running the estimate are used.
    v3.8.0: rates nobody saved fall back to the Tamil Nadu market default."""
    owner_rates = load_rates(c, project['owner_id'])
    if any(v > 0 for v in owner_rates.values()):
        return effective_rates(owner_rates)
    return effective_rates(load_rates(c, user_id))


def validate_rates(form):
    """{key: value} from a submitted form. Blank = 0 (not set). Raises ValueError on bad input."""
    out = {}
    for key, en, *_ in RATE_ITEMS:
        raw = str(form.get(key, '') or '').strip().replace(',', '')
        if not raw:
            continue                      # v3.8.0: blank = use the market rate
        try:
            v = float(raw)
        except ValueError:
            raise ValueError(f'{en}: enter a number')
        if not math.isfinite(v) or v < 0 or v > 1e7:
            raise ValueError(f'{en}: must be between 0 and 1,00,00,000')
        if key in PERCENT_KEYS and v > 100:
            raise ValueError(f'{en}: percentage must be 100 or less')
        out[key] = v
    return out


AUTO_TAG = 'civora_auto_v390'
LABOUR_WORK = 'Labour – item-wise (all work items)'
SERVICES_WORK = 'Doors, windows, electrical, plumbing & fixed items'


def _waste(payload):
    try:
        return float((payload.get('options') or {}).get('waste', 5)) / 100
    except (TypeError, ValueError):
        return 0.05


def work_quantities(payload):
    """Net work quantities (no wastage) from the material lines, for item-wise labour."""
    w = 1 + _waste(payload)
    q = {'pcc': 0.0, 'rcc': 0.0, 'steel': 0.0, 'brick': 0.0, 'plaster': 0.0, 'floor_tile': 0.0, 'wall_tile': 0.0,
         'paint': 0.0, 'paint_inside': 0.0, 'waterproof': 0.0}
    for row in payload.get('rows', []):
        if row.get(AUTO_TAG):
            continue
        work = str(row.get('work', '')).lower()
        area = _f(row.get('area'))
        mats = {}
        for it in row.get('items', []):
            mats[(it.get('material'), it.get('unit'))] = mats.get((it.get('material'), it.get('unit')), 0) + _f(it.get('quantity'))
        steel = sum(v for (m, u), v in mats.items() if m in ('Steel planning allowance (not BBS)', 'Reinforcement steel'))
        q['steel'] += steel / w
        if mats.get(('Bricks', 'nos')):
            q['brick'] += mats[('Bricks', 'nos')] * 0.002 / w           # 200 x 100 x 100 mm module
        if mats.get(('AAC blocks', 'nos')):
            q['brick'] += mats[('AAC blocks', 'nos')] * 0.604 * 0.204 * 0.204 / w
        if 'pcc' in work:
            agg = mats.get(('Coarse aggregate', 'm³'), 0)
            q['pcc'] += agg / 0.9477 / w if agg else area
        elif 'rcc' in work or mats.get(('Ready-mix concrete (RMC)', 'm³')):
            rmc = mats.get(('Ready-mix concrete (RMC)', 'm³'))
            if rmc:
                q['rcc'] += rmc / w
            elif mats.get(('M-sand', 'm³')):
                q['rcc'] += mats[('M-sand', 'm³')] / 0.42 / w
        if 'plaster' in work:
            q['plaster'] += area
        if any(m == 'Paint' for m, _ in mats):
            q['paint'] += area
            if any(k in work for k in ('internal', 'inner', 'ceiling')):
                q['paint_inside'] += area if 'external walls' not in work else area / 2
        if mats.get(('Wall tiles', 'nos')) or 'wall tile' in work:
            q['wall_tile'] += area
        elif mats.get(('Tiles', 'nos')):
            q['floor_tile'] += area
        if mats.get(('Waterproofing material', 'kg')):
            q['waterproof'] += area
    return q


def _openings(payload):
    """(main doors, internal doors, toilet doors, window+vent m²) from the schedule, else typical."""
    ops = payload.get('openings') or []
    main = internal = toilet = 0
    win = 0.0
    for o in ops:
        lab, src = str(o.get('label', '')).upper(), str(o.get('source', '')).upper()
        n = int(_f(o.get('count')) or 0)
        if 'DOOR' in lab:
            if 'MAIN' in src or 'MAIN' in lab or lab.endswith('D1'):
                main += n
            elif 'TOILET' in src or 'BATH' in src or _f(o.get('width')) <= 0.76:
                toilet += n
            else:
                internal += n
        elif any(k in lab for k in ('WINDOW', 'VENT')):
            win += _f(o.get('area'))
    floors = max(int(_f(payload.get('floors')) or 1), 1)
    if ops:
        return main * floors, internal * floors, toilet * floors, win * floors, 'from the door/window schedule'
    inp = {i.get('key'): _f(i.get('value')) for i in payload.get('inputs', [])}
    sqft = _f(payload.get('builtup_sqft'))
    n_int = round(inp.get('int_open', 0) / (0.9 * 2.1)) if inp.get('int_open') else max(round(sqft / floors / 250), 2)
    n_toilet = max(round(sqft / floors / 500), 1)
    win = inp.get('ext_open', sqft / 10.7639 / floors * 0.15) or 0
    return 1, max(n_int - n_toilet, 2) * floors, n_toilet * floors, win * floors, 'typical (no door/window schedule)'


def auto_rows(payload, rates):
    """Item-wise labour row + doors / windows / services row, priced. Old auto rows are replaced."""
    old_auto = {(r.get('work'), i.get('material')): i for r in payload.get('rows', []) if r.get(AUTO_TAG) for i in r.get('items', [])}
    removed = set(payload.get('removed_auto') or [])
    rows = [r for r in payload.get('rows', []) if not r.get(AUTO_TAG)]
    q = work_quantities({**payload, 'rows': rows})
    lab = []
    for key, qty, unit, what in (('lab_pcc', q['pcc'], 'm³', 'PCC'), ('lab_rcc', q['rcc'], 'm³', 'RCC concrete'),
                                 ('lab_steel', q['steel'], 'kg', 'steel'), ('lab_brick', q['brick'], 'm³', 'brick / block masonry'),
                                 ('lab_plaster', q['plaster'], 'm²', 'plaster'), ('lab_floor_tile', q['floor_tile'], 'm²', 'floor tiling'),
                                 ('lab_wall_tile', q['wall_tile'], 'm²', 'wall tiling'), ('lab_paint', q['paint'], 'm²', 'painting'),
                                 ('lab_waterproof', q['waterproof'], 'm²', 'waterproofing')):
        if qty > 0 and rates.get(key, 0) > 0 and not rates.get('labour_sqft', 0) > 0:   # lump sum chosen -> no item labour
            lab.append({'material': 'Labour – ' + LABEL[key], 'quantity': round(qty, 3), 'unit': unit, 'rate': round(rates[key], 2),
                        'basis': f'Net {what} quantity (no wastage) × labour rate', 'rate_key': key})
    if q['paint_inside'] > 0 and rates.get('putty', 0) > 0:
        lab.append({'material': 'Wall putty (2 coats)', 'quantity': round(q['paint_inside'] * 1.0, 2), 'unit': 'kg', 'rate': round(rates['putty'], 2),
                    'basis': '≈1.0 kg/m² for two coats on internal walls and ceiling', 'rate_key': 'putty'})
    sqft = _f(payload.get('builtup_sqft'))
    floors = max(int(_f(payload.get('floors')) or 1), 1)
    main, internal, toilet, win, src = _openings({**payload, 'rows': rows})
    kitchens = max(sum(1 for r in payload.get('rooms') or [] if 'KITCHEN' in str(r.get('name', '')).upper()), 1)
    svc = []
    for key, qty, unit, basis in (('door_main', main, 'nos', src), ('door_internal', internal, 'nos', src), ('door_toilet', toilet, 'nos', src),
                                  ('window_m2', win, 'm²', src), ('grill_m2', win, 'm²', 'same area as windows'),
                                  ('electrical_sqft', sqft, 'sq.ft', 'built-up area'), ('plumbing_sqft', sqft, 'sq.ft', 'built-up area'),
                                  ('kitchen_platform', kitchens, 'nos', 'one per kitchen'), ('sump', 1, 'nos', 'one per house'),
                                  ('septic', 1, 'nos', 'one per house'), ('oh_tank', 1, 'nos', 'one per house')):
        if qty > 0 and rates.get(key, 0) > 0:
            svc.append({'material': LABEL[key], 'quantity': round(qty, 3), 'unit': unit, 'rate': round(rates[key], 2),
                        'basis': basis, 'rate_key': key})
    for work, items in ((LABOUR_WORK, lab), (SERVICES_WORK, svc)):      # manual edits survive re-pricing
        keep = []
        for it in items:
            if it['material'] in removed:
                continue
            old = old_auto.get((work, it['material']))
            if old:
                if old.get('manual_qty'):
                    it['quantity'], it['manual_qty'] = old['quantity'], True
                if old.get('manual_rate'):
                    it['rate'], it['manual_rate'] = old['rate'], True
            keep.append(it)
        items[:] = keep
    has_labour = any(i.get('rate_key', '').startswith('lab_') for i in lab)
    if lab:
        rows.append({'work': LABOUR_WORK, 'area': 0, 'items': lab, AUTO_TAG: True})
    if svc:
        rows.append({'work': SERVICES_WORK, 'area': 0, 'items': svc, AUTO_TAG: True})
    payload['rows'] = rows
    return has_labour


def apply_rates(payload, rates, builtup_sqft):
    """Price a BOQ payload in place. Only lines with a saved (non-zero) rate are changed.
    Returns (priced_lines, unpriced_lines)."""
    priced = unpriced = 0
    material = 0.0
    itemwise = auto_rows(payload, rates)            # v3.9.0: labour per work item + doors/windows/services
    for row in payload.get('rows', []):
        for item in row.get('items', []):
            key = item.get('rate_key') or rate_key_for(item)
            r = rates.get(key, 0) if key else 0
            if r > 0 and not item.get('manual_rate'):      # a rate typed by hand is never overwritten
                item['rate'] = round(r, 2)
            if _f(item.get('rate')) > 0:
                priced += 1
                if not row.get(AUTO_TAG):
                    material += _f(item.get('quantity')) * _f(item.get('rate'))
            elif key:
                unpriced += 1
    extras = dict(payload.get('cost_extras') or {})
    manual = set(extras.get('manual') or [])
    if 'labour' in manual:
        pass
    elif rates.get('labour_sqft', 0) > 0 and builtup_sqft > 0 and not itemwise:
        extras['labour'] = round(rates['labour_sqft'] * builtup_sqft, 2)
    elif itemwise:
        extras['labour'] = 0                         # labour is in the item-wise row
    if rates.get('transport_pct', 0) > 0 and 'transport' not in manual:
        extras['transport'] = round(material * rates['transport_pct'] / 100, 2)
    pct = rates.get('contingency_pct', 0) + rates.get('contractor_pct', 0)
    if pct > 0 and 'other' not in manual:
        allin = sum(_f(i.get('quantity')) * _f(i.get('rate')) for r in payload.get('rows', []) for i in r.get('items', []))
        extras['other'] = round((allin + _f(extras.get('labour')) + _f(extras.get('transport'))) * pct / 100, 2)
        extras['other_note'] = f'Contingency {rates.get("contingency_pct", 0):g}% + contractor margin {rates.get("contractor_pct", 0):g}%'
    if rates.get('tax_percent', 0) > 0 and 'tax_percent' not in manual:
        extras['tax_percent'] = rates['tax_percent']
    for k in ('labour', 'transport', 'other', 'tax_percent'):
        extras.setdefault(k, 0)
    payload['cost_extras'] = extras
    payload['rates_applied_at'] = int(time.time())
    payload['pricing_version'] = PRICING_VERSION
    return priced, unpriced


PRICING_VERSION = 390


def upgrade_saved(c, project, rows):
    """v3.9.0: estimates saved before the complete Rate Master are re-priced once (labour, doors, services
    added; old per-sq.ft labour replaced). Rates typed by hand are kept. Returns ids that were updated."""
    done = []
    rates = None
    for r in rows:
        try:
            data = json.loads(r['payload'])
        except (TypeError, ValueError):
            continue
        if int(_f(data.get('pricing_version'))) >= PRICING_VERSION:
            continue
        if rates is None:
            rates = rates_for_project(c, project, project['owner_id'])
        ex = data.get('cost_extras') or {}
        if 'manual' not in ex:
            ex.pop('labour', None)                    # old per-sq.ft labour is replaced by item-wise labour
            data['cost_extras'] = ex
        apply_rates(data, rates, builtup_sqft_of(data, project))
        c.execute('UPDATE civora_boq_reports SET payload=? WHERE id=? AND project_id=?', (json.dumps(data, ensure_ascii=False), r['id'], project['id']))
        done.append(r['id'])
    return done


def builtup_sqft_of(payload, project):
    v = _f(payload.get('builtup_sqft'))
    return v if v > 0 else _f(project['area'])


def register_rates_v260(app, db, require, owned_project, csrf, check_csrf, layout, esc):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    init(db)

    def form_html(request, saved, message='', error=''):
        rates = effective_rates(saved)
        def rows(group):
            out = []
            for key, en, ta, unit, g in RATE_ITEMS:
                if g != group:
                    continue
                v = rates.get(key, 0)
                val = f'{v:g}' if (v or key in saved or key in MARKET_RATES) else ''
                mk = MARKET_RATES.get(key)
                tag = ('<em class="cv-rtag" style="font-style:normal;font-size:11px;color:#0369a1">market</em>' if key not in saved
                       else '<em class="cv-rtag" style="font-style:normal;font-size:11px;color:#15803d">yours</em>')
                hint = f' · market ₹{mk:g}' if (mk and key in saved and key not in PERCENT_KEYS and abs((v or 0) - mk) > 1e-9) else ''
                out.append(f'<div class="cv-rate"><label for="r_{key}"><b>{esc(en)} {tag}</b><small>{esc(ta)} · {esc(unit)}{hint}</small></label>'
                           f'<div class="cv-rin"><span>{"%" if key in PERCENT_KEYS else "₹"}</span><input id="r_{key}" name="{key}" type="number" '
                           f'min="0" max="{100 if key in PERCENT_KEYS else 10000000}" step="any" value="{val}" placeholder="not set">'
                           f'<button type="button" class="cv-rclr" title="Clear this rate" aria-label="Clear {esc(en)}" '
                           f'onclick="var i=document.getElementById(\'r_{key}\');i.value=\'\';i.focus()">&#10005;</button></div></div>')
            return ''.join(out)
        filled = sum(1 for k in RATE_KEYS if rates.get(k, 0) > 0)
        note = (f'<div class="cv-review cv-ok" style="margin-bottom:14px">{esc(message)}</div>' if message else '') + \
               (f'<div class="cv-review" style="margin-bottom:14px;background:#fef2f2;border-color:#fecaca;color:#991b1b">{esc(error)}</div>' if error else '')
        return layout(request, 'Rate Master', f'''<div class="cv-ph"><div><span class="eyebrow">RATE MASTER · விலைப் பட்டியல்</span><h1>My Local Rates</h1>
<div class="meta">{filled} of {len(RATE_ITEMS)} rates ready · {len(saved)} edited by you · market defaults: {esc(MARKET_AS_OF)}</div></div></div>{note}
<form method="post" action="/rates"><input type="hidden" name="csrf_token" value="{csrf(request)}">
<div class="cv-flow" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr))">
<section class="cv-card"><h3>Materials · பொருட்கள்</h3><p class="sub">Filled with today's Tamil Nadu average market price. Change any value to your dealer's price.</p>{rows('material')}
<h3 style="margin-top:18px">Doors, windows & services · கதவு, ஜன்னல் & சேவைகள்</h3><p class="sub">Counts come from the door/window schedule; electrical and plumbing by built-up area. Enter 0 for anything not needed.</p>{rows('services')}
</section>
<section class="cv-card"><h3>Labour by work item · வேலை வாரியான கூலி</h3><p class="sub">Labour only (no material). Worked out from daily wages and usual output per day.</p>{rows('labour')}
<h3 style="margin-top:18px">Work items · வேலைகள்</h3><p class="sub">Rates for work paid by quantity (labour + material / machine).</p>{rows('work')}
<h3 style="margin-top:18px">Charges · கட்டணங்கள்</h3><p class="sub">Percentages are added on the total. Use the labour lump sum only if you want ONE labour rate per sq.ft instead of item-wise labour.</p>{rows('charge')}</section></div>
<div class="actions"><button class="cv-btn">Save my rates</button><a class="cv-btn ghost" href="/">Back to Home</a></div>
<p class="hint"><b>market</b> = Tamil Nadu average (Chennai, Trichy, Madurai dealer prices, GST included); <b>yours</b> = your saved price. Prices change often – check with your dealer before ordering. Enter 0 for an item you do not want priced. “Reset to market” below removes your own values.</p></form>
<form method="post" action="/rates/clear" class="cv-inline" onsubmit="return confirm('Replace all your own rates with the market rates? Saved estimates keep their rates.')"><input type="hidden" name="csrf_token" value="{csrf(request)}">
<button class="cv-btn sm ghost">Reset all to market rates</button></form>''')

    @app.get('/rates')
    def rate_master(request: Request):
        u = require(request)
        with db() as c:
            rates = load_rates(c, u['id'])
        msg = ('Rates saved. New Smart Estimates will use them automatically.' if request.query_params.get('saved')
               else 'Your own rates were removed – market rates are used again.' if request.query_params.get('cleared') else '')
        return form_html(request, rates, msg)

    @app.post('/rates')
    async def save_rate_master(request: Request):
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        try:
            rates = validate_rates(form)
        except ValueError as ex:
            with db() as c:
                current = load_rates(c, u['id'])
            return form_html(request, current, error=str(ex))
        now = int(time.time())
        with db() as c:
            saved = load_rates(c, u['id'])
            for k in RATE_KEYS:                # blanked -> back to market rate
                if k in saved and k not in rates:
                    c.execute('DELETE FROM civora_rate_master_v260 WHERE user_id=? AND key=?', (u['id'], k))
            for k, v in rates.items():
                if k not in saved and abs(v - MARKET_RATES.get(k, -1)) < 1e-9:
                    continue                   # unchanged market value - keep following the market
                c.execute('INSERT INTO civora_rate_master_v260(user_id,key,rate,updated) VALUES(?,?,?,?) '
                          'ON CONFLICT(user_id,key) DO UPDATE SET rate=excluded.rate, updated=excluded.updated', (u['id'], k, v, now))
        return RedirectResponse('/rates?saved=1', 303)

    @app.post('/projects/{pid}/rates/apply')
    async def apply_rate_master(request: Request, pid: str):
        p = owned_project(request, pid)
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            rates = rates_for_project(c, p, u['id'])
            b = c.execute('SELECT id,payload FROM civora_boq_reports WHERE project_id=? ORDER BY created DESC LIMIT 1', (pid,)).fetchone()
            if not b:
                raise HTTPException(404, 'No saved BOQ in this project yet')
            payload = json.loads(b['payload'])
            apply_rates(payload, rates, builtup_sqft_of(payload, p))
            c.execute('UPDATE civora_boq_reports SET payload=? WHERE id=? AND project_id=?', (json.dumps(payload), b['id'], pid))
        return RedirectResponse(f'/projects/{pid}/workflow?priced=1#cost', 303)
