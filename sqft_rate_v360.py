"""Civora AI v3.6.0 - Estimate by current rate per sq.ft.

Next to every total estimate the user can type today's rate (e.g. ₹2,500 per sq.ft):
  Rate estimate = built-up area (sq.ft) × rate, shown instantly, compared with the
  detailed BOQ total, and remembered for the project (civora_sqft_rate_v360).
"""
import time

_DB = {'db': None}
MIN_RATE, MAX_RATE = 100, 100000          # ₹ per sq.ft sanity range


def inr(v):
    """Full Indian grouping: 2500000 -> ₹ 25,00,000."""
    v = round(float(v or 0))
    s = str(abs(int(v)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ','.join(parts) + ',' + tail
    return ('-₹ ' if v < 0 else '₹ ') + s


def calc(sqft, rate, boq_total=0):
    sqft, rate, boq_total = float(sqft or 0), float(rate or 0), float(boq_total or 0)
    total = sqft * rate
    out = {'sqft': sqft, 'rate': rate, 'total': total, 'boq_total': boq_total, 'diff': None, 'boq_per_sqft': None}
    if boq_total > 0 and sqft > 0:
        out['diff'] = total - boq_total
        out['boq_per_sqft'] = boq_total / sqft
    return out


def validate_rate(raw):
    try:
        v = float(str(raw).replace(',', '').replace('₹', '').strip())
    except ValueError:
        raise ValueError('Enter the rate per sq.ft as a number, e.g. 2500')
    if not MIN_RATE <= v <= MAX_RATE:
        raise ValueError(f'Rate per sq.ft must be between ₹{MIN_RATE:,} and ₹{MAX_RATE:,}')
    return v


def saved_rate(pid):
    db = _DB['db']
    if not db or not pid:
        return 0.0
    try:
        with db() as c:
            r = c.execute('SELECT rate FROM civora_sqft_rate_v360 WHERE project_id=?', (pid,)).fetchone()
        return float(r['rate']) if r else 0.0
    except Exception:
        return 0.0


def box_html(pid, sqft, boq_total=0, csrf_token='', can_edit=True, esc=None, rate=None, save=True):
    """The calculator block. Works instantly in the browser; 'Save rate' stores it for the project."""
    from html import escape
    esc = esc or escape
    rate = saved_rate(pid) if rate is None else rate
    c = calc(sqft, rate, boq_total)
    uid = f'sq{abs(hash((pid, sqft))) % 10**8}'
    boq_line = (f'<div class="sq-row"><span>Detailed BOQ total</span><b>{inr(boq_total)}</b></div>'
                f'<div class="sq-row"><span>BOQ works out to</span><b>{inr(c["boq_per_sqft"])} / sq.ft</b></div>'
                f'<div class="sq-row" id="{uid}d"></div>') if c['boq_per_sqft'] else ''
    form_open, form_close, btn = '<div>', '</div>', ''
    if save and pid and can_edit and csrf_token:
        form_open = (f'<form method="post" action="/projects/{esc(pid)}/sqft-rate" style="margin:0">'
                     f'<input type="hidden" name="csrf_token" value="{esc(csrf_token)}">')
        form_close = '</form>'
        btn = '<button class="cv-btn sm">Save rate</button>'
        if c['rate']:
            btn += (f'<button class="cv-btn sm" style="background:#b91c1c;border-color:#b91c1c" formaction="/projects/{esc(pid)}/sqft-rate/delete" '
                    'formnovalidate onclick="return confirm(&quot;Clear the saved rate?&quot;)">Delete rate</button>')
    return f'''<div class="sq-box" id="{uid}"><style>.sq-box{{margin-top:12px;padding:12px 14px;border:1px solid #fde68a;background:#fffbeb;border-radius:12px}}
.sq-box h4{{margin:0 0 8px;font-size:14px}}.sq-in{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.sq-in label{{margin:0;font-weight:600;font-size:13px}}
.sq-in input{{width:130px;padding:8px 10px;font-size:16px;font-weight:700}}.sq-row{{display:flex;justify-content:space-between;gap:10px;font-size:13.5px;margin-top:6px}}
.sq-big{{font-size:22px;font-weight:800;color:#92400e}}</style>
<h4>Estimate by today's rate per sq.ft <small style="font-weight:400;color:#64798d">· சதுர அடி விலைப்படி மதிப்பீடு</small></h4>
{form_open}<div class="sq-in"><label for="{uid}r">₹ per sq.ft</label><input id="{uid}r" name="rate" type="number" min="{MIN_RATE}" max="{MAX_RATE}" step="1" inputmode="numeric"
 value="{c['rate']:g}" placeholder="e.g. 2500">{btn}</div>{form_close}
<div class="sq-row"><span>{c['sqft']:,.0f} sq.ft × <b id="{uid}x">{inr(c['rate'])}</b></span><b class="sq-big" id="{uid}t">{inr(c['total']) if c['rate'] else '—'}</b></div>
{boq_line}
<p class="hint" style="margin:6px 0 0">Rate estimate = built-up area × your rate. Use it to compare with contractor quotes; the detailed BOQ above is item-wise.</p>
<script>(function(){{var b=document.getElementById('{uid}');if(!b)return;var i=document.getElementById('{uid}r'),A={c['sqft']:.4f},B={c['boq_total']:.2f};
function f(v){{v=Math.round(v);var n=Math.abs(v).toLocaleString('en-IN');return (v<0?'-₹ ':'₹ ')+n}}
function u(){{var r=parseFloat(i.value)||0,t=A*r;document.getElementById('{uid}x').textContent=f(r);document.getElementById('{uid}t').textContent=r?f(t):'—';
var d=document.getElementById('{uid}d');if(d&&B>0){{d.innerHTML=r?('<span>Difference (rate − BOQ)</span><b style="color:'+(t>B?'#b45309':'#15803d')+'">'+(t>=B?'+':'')+f(t-B)+'</b>'):''}}}}
i.addEventListener('input',u);u();}})();</script></div>'''


def register_sqft_rate_v360(app, db, owned_project, require, csrf, check_csrf, layout, esc):
    from fastapi import Request
    from fastapi.responses import RedirectResponse
    _DB['db'] = db
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS civora_sqft_rate_v360(project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE, '
                  'rate REAL NOT NULL, updated INTEGER NOT NULL)')

    @app.post('/projects/{pid}/sqft-rate')
    async def save_sqft_rate(request: Request, pid: str):
        owned_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        try:
            rate = validate_rate(form.get('rate', ''))
        except ValueError as ex:
            from fastapi import HTTPException
            raise HTTPException(400, str(ex))
        with db() as c:
            c.execute('INSERT INTO civora_sqft_rate_v360(project_id,rate,updated) VALUES(?,?,?) '
                      'ON CONFLICT(project_id) DO UPDATE SET rate=excluded.rate, updated=excluded.updated', (pid, rate, int(time.time())))
        return _back(request, pid)

    def _back(request, pid):
        back = request.headers.get('referer') or ''
        from urllib.parse import urlparse
        path = urlparse(back).path if back else ''
        return RedirectResponse(path if path.startswith(f'/projects/{pid}') else f'/projects/{pid}/workflow', 303)

    @app.post('/projects/{pid}/sqft-rate/delete')
    async def delete_sqft_rate(request: Request, pid: str):
        owned_project(request, pid)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        with db() as c:
            c.execute('DELETE FROM civora_sqft_rate_v360 WHERE project_id=?', (pid,))
        return _back(request, pid)
