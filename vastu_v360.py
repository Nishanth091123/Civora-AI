"""Civora AI v3.6.0 - Vastu guide (traditional guidance, English + Tamil).

The user picks the plot facing and where each room/item is in the plan (9 zones:
NE, N, NW, E, Centre, W, SE, S, SW). Civora shows for each item: ideal / acceptable /
avoid, a simple practical suggestion when a placement is not ideal, an overall score,
and the ideal layout for the chosen facing.

Vastu is traditional guidance, NOT engineering: it never overrides structure, light,
ventilation, fire safety or building-approval rules. Saved per project in civora_vastu_v360.
"""
import json
import time

from vastu_reader import NORTH_SIDES

# 3 x 3 grid, north at the top
ZONES = [('NW', 'North-West', 'வடமேற்கு · வாயு மூலை'), ('N', 'North', 'வடக்கு'), ('NE', 'North-East', 'வடகிழக்கு · ஈசானியம்'),
         ('W', 'West', 'மேற்கு'), ('C', 'Centre', 'மையம் · பிரம்மஸ்தானம்'), ('E', 'East', 'கிழக்கு'),
         ('SW', 'South-West', 'தென்மேற்கு · கன்னி மூலை'), ('S', 'South', 'தெற்கு'), ('SE', 'South-East', 'தென்கிழக்கு · அக்னி மூலை')]
ZONE = {z[0]: z for z in ZONES}
FACINGS = [('E', 'East facing', 'கிழக்கு நோக்கிய மனை'), ('N', 'North facing', 'வடக்கு நோக்கிய மனை'),
           ('W', 'West facing', 'மேற்கு நோக்கிய மனை'), ('S', 'South facing', 'தெற்கு நோக்கிய மனை'),
           ('NE', 'North-East corner plot', 'வடகிழக்கு மூலை மனை'), ('NW', 'North-West corner plot', 'வடமேற்கு மூலை மனை'),
           ('SE', 'South-East corner plot', 'தென்கிழக்கு மூலை மனை'), ('SW', 'South-West corner plot', 'தென்மேற்கு மூலை மனை')]
FACING = {f[0]: f for f in FACINGS}

# main entrance by plot facing: (ideal, acceptable, avoid)
ENTRANCE = {'E': (('E', 'NE'), ('N',), ('SE', 'SW', 'S')), 'N': (('N', 'NE'), ('NW', 'E'), ('SW', 'S')),
            'W': (('W', 'NW'), ('N',), ('SW', 'S')), 'S': (('S', 'SE'), ('E',), ('SW', 'W')),
            'NE': (('NE', 'N', 'E'), ('NW',), ('SW',)), 'NW': (('N', 'NW'), ('W', 'NE'), ('SW',)),
            'SE': (('E', 'S'), ('SE', 'NE'), ('SW',)), 'SW': (('W', 'S'), ('NW', 'SE'), ('SW',))}

# key, English, Tamil, ideal, acceptable, avoid, suggestion when not ideal
ITEMS = [
    ('entrance', 'Main entrance', 'தலைவாசல்', (), (), (),
     'Keep the main door the largest door of the house, opening inwards, well lit and free of obstacles. Do not shift structural columns to move it.'),
    ('pooja', 'Pooja room', 'பூஜை அறை', ('NE',), ('E', 'N'), ('S', 'SW', 'SE'),
     'Place the idols so you face East or North while praying. Keep it away from toilet walls and not under the staircase.'),
    ('living', 'Living room / hall', 'ஹால் · வரவேற்பறை', ('N', 'E', 'NE'), ('NW', 'C'), (),
     'Keep heavy furniture on the South and West sides of the hall and the North-East part of the hall open.'),
    ('kitchen', 'Kitchen', 'சமையலறை', ('SE',), ('NW', 'E'), ('NE', 'SW', 'C', 'N'),
     'Place the stove in the South-East part of the kitchen so the cook faces East. Keep the sink and water away from the stove.'),
    ('master', 'Master bedroom', 'பிரதான படுக்கையறை', ('SW',), ('S', 'W'), ('NE', 'SE', 'C'),
     'Place the bed in the South-West part of the room with the head towards South or East.'),
    ('bedroom', 'Children / other bedroom', 'பிள்ளைகள் / மற்ற படுக்கையறை', ('W', 'NW'), ('S', 'E', 'N'), ('NE', 'SE', 'C'),
     'Head of the bed towards South or East. Keep the study table so the child faces East or North.'),
    ('dining', 'Dining', 'உணவருந்தும் இடம்', ('W',), ('E', 'S', 'N', 'C'), (),
     'Sit facing East or North while eating where possible.'),
    ('toilet', 'Toilet / bathroom', 'கழிவறை / குளியலறை', ('NW', 'W'), ('S', 'E'), ('NE', 'SW', 'C'),
     'Keep it clean, dry and well ventilated with an exhaust fan; keep the door closed. Place the WC so the user faces North or South.'),
    ('stair', 'Staircase', 'மாடிப்படி', ('S', 'W', 'SW'), ('SE', 'NW'), ('NE', 'C'),
     'Steps should climb clockwise (North→South or East→West). Keep the space under the stairs for storage, not pooja or toilet.'),
    ('sump', 'Sump / borewell / underground tank', 'சம்ப் · போர்வெல் · நிலத்தடி தொட்டி', ('NE',), ('N', 'E'), ('SW', 'SE', 'S', 'C'),
     'Water below ground is preferred in the North or East side. Keep it covered and well away from the septic tank (hygiene first).'),
    ('ohtank', 'Overhead water tank', 'மேல்நிலை நீர்த் தொட்டி', ('SW',), ('W', 'S'), ('NE', 'SE', 'C'),
     'Keep the tank on the South-West portion of the roof, on beams designed for its weight (engineer to confirm).'),
    ('septic', 'Septic tank', 'செப்டிக் டேங்க்', ('NW',), ('W', 'N'), ('NE', 'SW', 'SE', 'E', 'C'),
     'Health and local rules come first: keep the required distance from the sump/borewell and from the building.'),
    ('parking', 'Car parking', 'வாகன நிறுத்தம்', ('NW', 'SE'), ('N', 'E'), ('NE', 'SW'),
     'Park so the vehicle faces North or East when leaving; do not block the North-East corner.'),
    ('study', 'Study / office room', 'படிப்பறை / அலுவலக அறை', ('E', 'N', 'NE'), ('W', 'NW'), (),
     'Sit facing East or North while studying or working.'),
    ('store', 'Store room', 'சேமிப்பு அறை', ('SW', 'S'), ('W', 'NW'), ('NE',),
     'Keep heavy items on the South and West walls; keep the North-East side light.'),
]
ITEM = {i[0]: i for i in ITEMS}

TIPS = [('Keep the centre of the house (Brahmasthan) open and uncluttered – no toilet, kitchen, staircase or heavy load there.',
         'வீட்டின் மையப் பகுதியை திறந்து, சுத்தமாக வைக்கவும்.'),
        ('Leave more open space on the North and East sides of the plot; build heavier and taller on the South and West.',
         'வடக்கு, கிழக்கு பக்கம் அதிக திறந்த இடம்; தெற்கு, மேற்கு பக்கம் உயரமான / கனமான கட்டுமானம்.'),
        ('Keep the North-East corner light, clean and open – the best place for water, prayer and windows.',
         'வடகிழக்கு மூலையை லேசாகவும், சுத்தமாகவும் வைக்கவும்.'),
        ('More and larger windows on the North and East for morning light and cross ventilation.',
         'வடக்கு, கிழக்கு பக்கம் அதிக ஜன்னல்கள்.'),
        ('Floor, roof and site slope (rain water flow) towards North, East or North-East.',
         'தரை, கூரை சாய்வு / மழைநீர் ஓட்டம் வடகிழக்கு நோக்கி.'),
        ('Main door should be the largest door, opening inwards; avoid two doors exactly opposite each other on the main axis.',
         'தலைவாசல் பெரியதாகவும், உள்நோக்கித் திறப்பதாகவும் இருக்கட்டும்.')]

SCORE = {'ideal': 100, 'ok': 70, 'neutral': 50, 'avoid': 0}
STATUS_LABEL = {'ideal': ('Ideal', 'சிறந்தது', '#15803d', '#dcfce7'), 'ok': ('Acceptable', 'ஏற்கத்தக்கது', '#1d4ed8', '#dbeafe'),
                'neutral': ('Neutral', 'நடுநிலை', '#475569', '#f1f5f9'), 'avoid': ('Avoid', 'தவிர்க்கவும்', '#b91c1c', '#fee2e2')}


def rule(key, facing):
    if key == 'entrance':
        return ENTRANCE.get(facing, ENTRANCE['E'])
    _, _, _, ideal, ok, avoid, _ = ITEM[key]
    return ideal, ok, avoid


def check(key, zone, facing):
    ideal, ok, avoid = rule(key, facing)
    if zone in ideal:
        return 'ideal'
    if zone in ok:
        return 'ok'
    if zone in avoid:
        return 'avoid'
    return 'neutral'


def evaluate(facing, placements):
    """placements: {item_key: zone}. Returns dict(items=[...], score, grade)."""
    if facing not in FACING:
        raise ValueError('Choose the plot facing')
    out = []
    for key, en, ta, *_rest in ITEMS:
        zone = placements.get(key)
        if zone not in ZONE:
            continue
        st = check(key, zone, facing)
        ideal, ok, avoid = rule(key, facing)
        out.append({'key': key, 'name': en, 'ta': ta, 'zone': zone, 'status': st, 'score': SCORE[st],
                    'ideal': list(ideal), 'ok': list(ok), 'avoid': list(avoid),
                    'tip': ITEM[key][6] if st in ('avoid', 'neutral', 'ok') else ''})
    score = round(sum(i['score'] for i in out) / len(out)) if out else 0
    if any(i['status'] == 'avoid' for i in out):
        score = min(score, 79)          # one 'avoid' placement keeps the plan below 'Very good'
    grade = ('Very good', 'மிகச் சிறப்பு') if score >= 80 else ('Good', 'நன்று') if score >= 60 else \
        ('Average', 'சராசரி') if score >= 40 else ('Needs attention', 'கவனம் தேவை')
    return {'items': out, 'score': score, 'grade': grade if out else ('—', '—')}


def ideal_layout(facing):
    """zone -> list of item names whose IDEAL zone it is (for the suggested layout grid)."""
    grid = {z[0]: [] for z in ZONES}
    for key, en, *_ in ITEMS:
        for z in rule(key, facing)[0][:1]:
            grid[z].append(en)
    grid['C'].append('Keep open')
    return grid


def parse(form):
    facing = str(form.get('facing') or '')
    if facing not in FACING:
        raise ValueError('Choose the plot facing')
    placements = {k: str(form.get(f'z_{k}') or '') for k, *_ in ITEMS}
    return facing, {k: v for k, v in placements.items() if v in ZONE}


# ------------------------------------------------------------------ web pages
def evaluate_list(facing, found):
    """found: [{key, label, zone}] - every room instance from a drawing (e.g. 3 bedrooms)."""
    if facing not in FACING:
        raise ValueError('Choose the plot facing')
    out = []
    for f in found:
        if f['key'] not in ITEM or f['zone'] not in ZONE:
            continue
        st = check(f['key'], f['zone'], facing)
        ideal, ok, avoid = rule(f['key'], facing)
        out.append({'key': f['key'], 'name': ITEM[f['key']][1], 'ta': ITEM[f['key']][2], 'label': f.get('label', ''),
                    'zone': f['zone'], 'status': st, 'score': SCORE[st], 'ideal': list(ideal), 'ok': list(ok),
                    'avoid': list(avoid), 'tip': ITEM[f['key']][6] if st != 'ideal' else ''})
    score = round(sum(i['score'] for i in out) / len(out)) if out else 0
    if any(i['status'] == 'avoid' for i in out):
        score = min(score, 79)
    grade = ('Very good', 'மிகச் சிறப்பு') if score >= 80 else ('Good', 'நன்று') if score >= 60 else \
        ('Average', 'சராசரி') if score >= 40 else ('Needs attention', 'கவனம் தேவை')
    return {'items': out, 'score': score, 'grade': grade if out else ('—', '—')}


GUIDE = [  # (where, what belongs there, Tamil)
    ('North-East (Eesanyam)', 'Pooja room, sump / borewell, main entrance on N or E side, open space, windows. Keep it light and clean – no toilet, no heavy load.',
     'வடகிழக்கு: பூஜை, சம்ப்/போர்வெல், திறந்த இடம். கழிவறை, கனமான பொருள் வேண்டாம்.'),
    ('East', 'Living room, study, bathing area, large windows for morning sun.', 'கிழக்கு: ஹால், படிப்பறை, பெரிய ஜன்னல்கள்.'),
    ('South-East (Agni)', 'Kitchen (cook facing East), electrical panel, generator.', 'தென்கிழக்கு: சமையலறை, மின் சாதனங்கள்.'),
    ('South', 'Bedrooms, staircase, store, heavier and taller construction.', 'தெற்கு: படுக்கையறை, மாடிப்படி, சேமிப்பு அறை.'),
    ('South-West (Nairuthi / Kanni moolai)', 'Master bedroom, overhead tank, heavy storage. Highest and heaviest part of the house. No entrance, no pit or sump.',
     'தென்மேற்கு: பிரதான படுக்கையறை, மேல்நிலை தொட்டி. வாசல், குழி வேண்டாம்.'),
    ('West', 'Dining, children\'s bedroom, staircase, toilets.', 'மேற்கு: உணவு அறை, பிள்ளைகள் அறை, கழிவறை.'),
    ('North-West (Vayu)', 'Guest room, toilets, septic tank, car parking, grain store.', 'வடமேற்கு: விருந்தினர் அறை, கழிவறை, செப்டிக், வாகன நிறுத்தம்.'),
    ('North', 'Living room, entrance, cash locker facing North, open space.', 'வடக்கு: ஹால், வாசல், திறந்த இடம்.'),
    ('Centre (Brahmasthan)', 'Keep open and clutter-free: no toilet, kitchen, staircase or heavy column cluster.', 'மையம்: திறந்து வைக்கவும்.'),
]


def register_vastu_v360(app, db, owned_project, require, csrf, check_csrf, layout, esc, FILES=None, store_upload=None):
    store_upload_ref, files_ref = {'fn': store_upload}, {'dir': FILES}
    from fastapi import Request
    from fastapi.responses import RedirectResponse
    from ui_shell import icon

    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS civora_vastu_v360(project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE, '
                  'payload TEXT NOT NULL, updated INTEGER NOT NULL)')

    def load(pid):
        with db() as c:
            r = c.execute('SELECT payload FROM civora_vastu_v360 WHERE project_id=?', (pid,)).fetchone()
        try:
            return json.loads(r['payload']) if r else {}
        except ValueError:
            return {}

    def zone_label(z):
        return f'{ZONE[z][1]}'

    def grid_html(cells, title):
        out = ''
        for z, en, ta in ZONES:
            body = cells.get(z, '')
            out += (f'<div style="border:1px solid #dbe6f1;border-radius:10px;padding:8px;min-height:86px;background:{"#fefce8" if z == "C" else "#fff"}">'
                    f'<div style="font-size:11px;font-weight:800;color:#64798d;letter-spacing:.5px">{esc(en.upper())}</div>'
                    f'<div style="font-size:10.5px;color:#94a3b8">{esc(ta)}</div>{body}</div>')
        return (f'<section class="cv-card"><h3>{esc(title)}</h3><div style="text-align:center;font-weight:800;color:#2563eb;font-size:12px">▲ NORTH · வடக்கு</div>'
                f'<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:6px">{out}</div></section>')

    def result_html(ev, facing, mine_title='Your layout'):
        colour = '#15803d' if ev['score'] >= 60 else '#b45309' if ev['score'] >= 40 else '#b91c1c'
        trs = ''
        for it in ev['items']:
            lab, lta, fg, bg = STATUS_LABEL[it['status']]
            best = ', '.join(zone_label(z) for z in it['ideal'])
            name = esc(it['name']) + (f' <small class="muted">“{esc(it["label"])}”</small>' if it.get('label') else '')
            trs += (f'<tr><td><b>{name}</b><br><small class="muted">{esc(it["ta"])}</small></td><td>{esc(zone_label(it["zone"]))}</td>'
                    f'<td><span style="background:{bg};color:{fg};padding:3px 9px;border-radius:99px;font-weight:700;font-size:12.5px">{lab}</span>'
                    f'<br><small class="muted">{lta}</small></td><td><small>Best: <b>{esc(best)}</b></small>'
                    + (f'<br><small>{esc(it["tip"])}</small>' if it['tip'] else '') + '</td></tr>')
        mine = {}
        for it in ev['items']:
            fg, bg = STATUS_LABEL[it['status']][2:]
            mine[it['zone']] = mine.get(it['zone'], '') + (f'<div style="margin-top:4px;font-size:12px;background:{bg};color:{fg};border-radius:6px;padding:2px 6px">'
                                                            f'{esc(it.get("label") or it["name"])}</div>')
        sugg = {z: ''.join(f'<div style="margin-top:4px;font-size:12px;background:#eff6ff;color:#1e3a8a;border-radius:6px;padding:2px 6px">{esc(n)}</div>'
                           for n in names) for z, names in ideal_layout(facing).items()}
        n_avoid = sum(1 for i in ev['items'] if i['status'] == 'avoid')
        return (f'<section class="cv-card" style="margin-bottom:16px"><div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">'
                f'<div style="font-size:44px;font-weight:800;color:{colour}">{ev["score"]}<small style="font-size:18px">/100</small></div>'
                f'<div><b style="font-size:18px">{esc(ev["grade"][0])}</b> · {esc(ev["grade"][1])}<br><small class="muted">{esc(FACING[facing][1])} · '
                f'{len(ev["items"])} item(s) checked · {n_avoid} to avoid</small></div></div></section>'
                f'<section class="cv-card" style="margin-bottom:16px"><h3>Room by room · அறை வாரியாக</h3><div class="scroll"><table class="cv-mt">'
                f'<tr><th>Item</th><th>In your plan</th><th>Vastu</th><th>Suggestion</th></tr>{trs}</table></div></section>'
                f'<div class="cv-row" style="margin-bottom:16px">{grid_html(mine, mine_title)}{grid_html(sugg, "Ideal layout for " + FACING[facing][1])}</div>')

    def guide_html():
        rows = ''.join(f'<tr><td><b>{esc(w)}</b></td><td>{esc(en)}<br><small class="muted">{esc(ta)}</small></td></tr>' for w, en, ta in GUIDE)
        tips = ''.join(f'<li>{esc(en)}<br><small class="muted">{esc(ta)}</small></li>' for en, ta in TIPS)
        return (f'<section class="cv-card" style="margin-top:16px"><h3>Vastu guide – what goes where · எது எங்கே இருக்க வேண்டும்</h3>'
                f'<div class="scroll"><table class="cv-mt"><tr><th style="width:28%">Direction</th><th>Best used for</th></tr>{rows}</table></div></section>'
                f'<section class="cv-card" style="margin-top:16px"><h3>General Vastu tips · பொது குறிப்புகள்</h3><ul>{tips}</ul></section>')

    DISCLAIM = ('Vastu is traditional guidance, not engineering. Never move columns, beams or footings, or reduce light, ventilation, '
                'fire exits or approval setbacks for Vastu. The engineer\'s design and building rules come first.')

    def page(request, p, facing, placements, saved, preview=False, found=None, source=''):
        P = f'/projects/{p["id"]}'
        token = csrf(request)
        fopts = '<option value="">Choose…</option>' + ''.join(
            f'<option value="{k}"{" selected" if k == facing else ""}>{esc(en)} · {esc(ta)}</option>' for k, en, ta in FACINGS)
        rows = ''
        for key, en, ta, *_ in ITEMS:
            zsel = '<option value="">Not in plan</option>' + ''.join(
                f'<option value="{z}"{" selected" if placements.get(key) == z else ""}>{esc(zen)}</option>' for z, zen, _ in ZONES)
            rows += (f'<div class="cv-field"><label for="z_{key}"><b>{esc(en)}</b><small>{esc(ta)}</small></label>'
                     f'<div class="cv-fin"><select id="z_{key}" name="z_{key}">{zsel}</select></div><div></div></div>')
        result, state = '', ''
        if facing:
            ev = evaluate_list(facing, found) if found else evaluate(facing, placements)
            if ev['items']:
                result = result_html(ev, facing, 'Rooms found on the drawing' if found else 'Your layout')
        if preview:
            state = (f'<div class="cv-review" style="margin:0 0 14px;background:#fffbeb;border-color:#fde68a;color:#92400e">'
                     f'<b>PREVIEW – NOT SAVED.</b>&nbsp;{esc(source) or "Check the result"}. Correct any room below, then press <b>Save Vastu check</b>.</div>')
        elif saved:
            state = (f'<div class="cv-review" style="margin:0 0 14px;background:#f0fdf4;border-color:#bbf7d0;color:#166534">'
                     f'<span>Saved with this project.</span>&nbsp;'
                     + __import__('preview_v370').delete_button(f'{P}/vastu/delete', token, 'Delete saved Vastu check', 'Delete the saved Vastu check?', esc) + '</div>')
        return layout(request, 'Vastu guide', f'''<span class="eyebrow">VASTU · வாஸ்து · {esc(p["name"])}</span>
<h1>Vastu check for your plan</h1>
<p class="muted">Upload a drawing and Civora finds the rooms and checks them, or choose where each room is yourself.</p>
<div class="actions" style="margin:6px 0 14px"><a class="cv-btn" href="{P}/vastu/drawing">{icon("upload", 16)} Check Vastu from a drawing</a><a class="cv-btn ghost" href="#guide">Vastu guide</a></div>
<div class="cv-review" style="margin:0 0 16px">{icon("shield", 16)}<span>{esc(DISCLAIM)}</span></div>
{state}{result}
<form method="post" action="{P}/vastu"><input type="hidden" name="csrf_token" value="{token}">
<section class="cv-card cv-group"><h3>Plot <small>மனை</small></h3>
<div class="cv-field"><label for="facing"><b>Plot facing (road side)</b><small>மனை எந்த திசையை நோக்கியுள்ளது</small></label><div class="cv-fin"><select id="facing" name="facing" required>{fopts}</select></div><div></div></div></section>
<section class="cv-card cv-group" style="margin-top:14px"><h3>Where is each room? <small>ஒவ்வொரு அறையும் எந்த திசையில்</small></h3>
<p class="sub">Divide your plan into a 3 × 3 grid with North at the top. Pick the zone where most of the room is.</p>{rows}</section>
<div class="cv-stickybar"><span>{"Preview – not saved yet." if preview else "Step 1: check · Step 2: save."}</span>
<button class="cv-btn ghost" name="confirm" value="0">{icon("check", 17)} Check (preview)</button>
<button class="cv-btn" name="confirm" value="1">Save Vastu check</button></div></form>
<div id="guide">{guide_html()}</div>''')

    @app.get('/projects/{pid}/vastu')
    def vastu_page(request: Request, pid: str):
        p = owned_project(request, pid)
        saved = load(pid)
        return page(request, p, saved.get('facing', ''), saved.get('placements', {}), bool(saved))

    @app.post('/projects/{pid}/vastu')
    async def vastu_save(request: Request, pid: str):
        p = owned_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        try:
            facing, placements = parse(form)
        except ValueError:
            return RedirectResponse(f'/projects/{pid}/vastu', 303)
        import preview_v370
        if not preview_v370.confirmed(form):
            return page(request, p, facing, placements, False, preview=True, source='Your choices')
        with db() as c:
            c.execute('INSERT INTO civora_vastu_v360(project_id,payload,updated) VALUES(?,?,?) '
                      'ON CONFLICT(project_id) DO UPDATE SET payload=excluded.payload, updated=excluded.updated',
                      (pid, json.dumps({'facing': facing, 'placements': placements}), int(time.time())))
        return RedirectResponse(f'/projects/{pid}/vastu', 303)

    @app.post('/projects/{pid}/vastu/delete')
    async def vastu_delete(request: Request, pid: str):
        owned_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            c.execute('DELETE FROM civora_vastu_v360 WHERE project_id=?', (pid,))
        return RedirectResponse(f'/projects/{pid}/vastu', 303)

    # ---------------- Vastu from an uploaded drawing
    def drawings_of(pid):
        with db() as c:
            return [r for r in c.execute('SELECT * FROM uploads WHERE project_id=? ORDER BY created DESC', (pid,)).fetchall()
                    if str(r['original_name']).lower().endswith(('.pdf', '.dxf', '.png', '.jpg', '.jpeg'))]

    @app.get('/projects/{pid}/vastu/drawing')
    def vastu_drawing_start(request: Request, pid: str):
        p = owned_project(request, pid)
        P = f'/projects/{pid}'
        cards = ''.join(f'<a class="cv-pick" href="{P}/vastu/drawing/{esc(r["id"])}"><span class="cv-pickimg"><img loading="lazy" src="{P}/drawings/{esc(r["id"])}/media" alt=""></span>'
                        f'<span class="cv-pickt"><b>{esc(r["original_name"])}</b></span><span class="cv-btn sm">Check this {icon("arrow", 15)}</span></a>' for r in drawings_of(pid))
        existing = f'<h2 style="margin:22px 0 10px">Or a drawing already in this project</h2><div class="cv-picks">{cards}</div>' if cards else ''
        return layout(request, 'Vastu from drawing', f'''<span class="eyebrow">VASTU · DRAWING CHECK · {esc(p["name"])}</span>
<h1>Check Vastu from your plan</h1><p class="muted">Civora reads the room names on the plan (KITCHEN, POOJA, MASTER BED, TOILET, STAIR, SUMP …) and where they are, then checks each one.</p>
<form class="cv-drop" method="post" action="{P}/vastu/drawing" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{csrf(request)}">
{icon("upload", 40)}<b>Upload the floor plan</b><span>PDF, DXF (CAD), PNG or JPG · room names must be written on the plan</span>
<input type="file" name="file" accept=".pdf,.dxf,.png,.jpg,.jpeg" required><button class="cv-btn">{icon("arrow", 16)} Upload &amp; read rooms</button></form>{existing}''')

    @app.post('/projects/{pid}/vastu/drawing')
    async def vastu_drawing_upload(request: Request, pid: str):
        owned_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        f = form.get('file')
        if f is None or not hasattr(f, 'read'):
            from fastapi import HTTPException
            raise HTTPException(400, 'Choose a drawing file')
        fid = store_upload_ref['fn'](pid, getattr(f, 'filename', '') or 'plan', await f.read(30 * 1024 * 1024 + 1), getattr(f, 'content_type', None))
        return RedirectResponse(f'/projects/{pid}/vastu/drawing/{fid}', 303)

    @app.get('/projects/{pid}/vastu/drawing/{fid}')
    def vastu_drawing_check(request: Request, pid: str, fid: str, north: str = '', facing: str = '', page_no: int = 0):
        p = owned_project(request, pid)
        P = f'/projects/{pid}'
        with db() as c:
            r = c.execute('SELECT * FROM uploads WHERE id=? AND project_id=?', (fid, pid)).fetchone()
        if not r:
            from fastapi import HTTPException
            raise HTTPException(404, 'Drawing not found')
        if north not in NORTH_SIDES or facing not in FACING:
            saved = load(pid)
            fopts = ''.join(f'<option value="{k}"{" selected" if k == (facing or saved.get("facing")) else ""}>{esc(en)} · {esc(ta)}</option>' for k, en, ta in FACINGS)
            sides = ''.join(f'<label class="cv-pick" style="flex-direction:row;align-items:center;gap:10px;padding:12px">'
                            f'<input type="radio" name="north" value="{k}" style="width:auto" required{" checked" if k == north else ""}>'
                            f'<b>{esc(v)}</b></label>' for k, v in NORTH_SIDES.items())
            return layout(request, 'Vastu from drawing', f'''<span class="eyebrow">VASTU · DRAWING CHECK</span><h1>Which side of this drawing is North?</h1>
<p class="muted">Look for the North arrow (N ↑) on the plan. Civora needs this to know where each room is.</p>
<div class="cv-row"><section class="cv-card"><img src="{P}/drawings/{esc(fid)}/media" alt="Drawing" style="width:100%;border:1px solid #dbe6f1;border-radius:10px"></section>
<form class="cv-card" method="get" action="{P}/vastu/drawing/{esc(fid)}"><h3>North arrow points to · வடக்கு திசை</h3><div class="cv-picks" style="grid-template-columns:1fr 1fr">{sides}</div>
<h3 style="margin-top:14px">Plot facing (road side)</h3><select name="facing" required>{fopts}</select>
<div class="actions"><button class="cv-btn">{icon("check", 16)} Check Vastu</button></div></form></div>''')
        import vastu_reader, filestore
        try:
            res = vastu_reader.read_plan(filestore.ensure(files_ref['dir'], r['stored_name']), north, page_no)
        except Exception as ex:
            res = {'rooms': [], 'method': 'unreadable', 'labels_read': 0, 'error': f'{type(ex).__name__}: {str(ex)[:120]}'}
        found = res['rooms']
        if not found:
            return layout(request, 'Vastu from drawing', f'''<span class="eyebrow">VASTU · DRAWING CHECK</span><h1>No room names found on this drawing</h1>
<p>Civora read {res.get("labels_read", 0)} text label(s) ({esc(res.get("method", ""))}) but none was a room name such as KITCHEN, POOJA, BEDROOM, TOILET.
{esc(res.get("error", ""))}</p><p>Use a plan with room names written inside the rooms, or choose the rooms yourself.</p>
<div class="actions"><a class="cv-btn" href="{P}/vastu">Choose rooms myself</a><a class="cv-btn ghost" href="{P}/vastu/drawing">Try another drawing</a></div>''')
        placements = {}
        for f in found:
            placements.setdefault(f['key'], f['zone'])
        return page(request, p, facing, placements, False, preview=True, found=found,
                    source=f'{len(found)} room(s) read from “{r["original_name"]}” ({res["method"]}, North = {NORTH_SIDES[north].lower()})')
