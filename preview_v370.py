"""Civora AI v3.7.0 - "Preview first, then Save" for every calculation that is stored.

How it works (no extra table): a calculation form is posted once WITHOUT confirm=1 ->
the result is shown with all submitted values carried along as hidden fields, plus
[← Change values] and [Save]. Save posts the same values again WITH confirm=1, the server
recalculates (so nothing can be tampered with in between) and stores it.
After saving, every result page shows a Delete button right next to it.
"""
from collections import defaultdict
from html import escape as _esc


def confirmed(form):
    return str(form.get('confirm') or '') == '1'


def hidden_fields(form, esc=_esc):
    items = form.multi_items() if hasattr(form, 'multi_items') else list(form.items())
    return ''.join(f'<input type="hidden" name="{esc(str(k))}" value="{esc(str(v))}">'
                   for k, v in items if k not in ('csrf_token', 'confirm') and not hasattr(v, 'read'))


def gate(request, form, layout, csrf_token, title, summary_html, action, esc=_esc, save_label='Save', note=''):
    """The preview page. Nothing has been saved when this is shown."""
    note_html = f'<p class="hint">{esc(note)}</p>' if note else ''
    q = getattr(getattr(request, 'url', None), 'query', '')
    if q and '?' not in action:          # keep ?return=... so the page comes back to where the user was
        action = f'{action}?{q}'
    return layout(request, f'{title} – preview', f'''<span class="eyebrow">PREVIEW · NOT SAVED YET · முன்னோட்டம்</span><h1>{esc(title)}</h1>
<p class="muted">Check the result below. Nothing is stored until you press <b>{esc(save_label)}</b>.</p>{note_html}
{summary_html}
<form method="post" action="{esc(action)}" class="cv-stickybar" style="gap:10px">{hidden_fields(form, esc)}
<input type="hidden" name="csrf_token" value="{esc(csrf_token)}"><input type="hidden" name="confirm" value="1">
<span>Preview only – not saved.</span>
<button type="button" class="cv-btn ghost" onclick="history.back()">← Change values</button>
<button class="cv-btn">{esc(save_label)}</button></form>''')


def delete_button(action, csrf_token, label='Delete', confirm_text='Delete this permanently?', esc=_esc, next_url=''):
    nxt = f'<input type="hidden" name="next" value="{esc(next_url)}">' if next_url else ''
    return (f'<form method="post" action="{esc(action)}" style="display:inline;margin:0" onsubmit="return confirm(&quot;{esc(confirm_text)}&quot;)">'
            f'<input type="hidden" name="csrf_token" value="{esc(csrf_token)}">{nxt}'
            f'<button class="cv-btn sm" style="background:#b91c1c;border-color:#b91c1c">{esc(label)}</button></form>')


def values_table(pairs, esc=_esc):
    return ('<section class="cv-card"><table class="cv-mt">' +
            ''.join(f'<tr><th style="width:45%">{esc(str(k))}</th><td>{esc(str(v))}</td></tr>' for k, v in pairs) + '</table></section>')


def _fmt(q, unit):
    if unit in ('nos',) or 'bag' in unit:
        return f'{q:,.0f}' if 'bag' not in unit else f'{q:,.1f}'
    return f'{q:,.2f}'


def boq_summary_html(payload, esc=_esc):
    """Compact preview of an estimate payload: totals by material, cost, work items, notes."""
    agg = defaultdict(float)
    amt = defaultdict(float)
    order = []
    cost = 0.0
    for row in payload.get('rows', []):
        for it in row.get('items', []):
            key = (it.get('material', ''), it.get('unit', ''))
            if key not in agg:
                order.append(key)
            q, r = float(it.get('quantity') or 0), float(it.get('rate') or 0)
            agg[key] += q
            amt[key] += q * r
            cost += q * r
    def _rate(k):
        return f'₹ {amt[k] / agg[k]:,.2f}' if agg[k] and amt[k] else '<span class="muted">—</span>'
    mats = ''.join(f'<tr><td>{esc(m)}</td><td style="text-align:right"><b>{_fmt(agg[(m, u)], u)}</b> {esc(u)}</td>'
                   f'<td style="text-align:right">{_rate((m, u))}</td><td style="text-align:right"><b>{"₹ " + format(round(amt[(m, u)]), ",") if amt[(m, u)] else "—"}</b></td></tr>'
                   for m, u in order)
    sqft = float(payload.get('builtup_sqft') or 0)
    ex = payload.get('cost_extras') or {}
    sub = cost + sum(float(ex.get(k) or 0) for k in ('labour', 'transport', 'other'))
    total = sub * (1 + float(ex.get('tax_percent') or 0) / 100)
    cost_html = ''
    if total > 0:
        per = f' · ₹ {total / sqft:,.0f} per sq.ft' if sqft else ''
        lines = [('Materials, labour & services', cost), ('Transport', float(ex.get('transport') or 0)),
                 (ex.get('other_note') or 'Other charges', float(ex.get('other') or 0)), ('Labour (lump sum)', float(ex.get('labour') or 0)),
                 (f'GST {float(ex.get("tax_percent") or 0):g}%', sub * float(ex.get('tax_percent') or 0) / 100)]
        rows_html = ''.join(f'<tr><td>{esc(a)}</td><td style="text-align:right">₹ {b:,.0f}</td></tr>' for a, b in lines if b)
        cost_html = (f'<table class="cv-mt" style="margin-top:10px">{rows_html}<tr><th>Estimated total</th><th style="text-align:right">₹ {total:,.0f}</th></tr></table>'
                     f'<p class="cv-persqft"><b>₹ {total:,.0f}</b> estimated total{per}</p>')
    items = ''.join(f'<li>{esc(r.get("work", ""))} <small class="muted">({float(r.get("area") or 0):,.2f})</small></li>' for r in payload.get('rows', []))
    notes = ''.join(f'<li>{esc(n)}</li>' for n in (payload.get('notes') or [])[:12])
    typical = [i for i in payload.get('inputs', []) if i.get('source') == 'typical']
    typ_html = (f'<div class="cv-review" style="margin:10px 0">{len(typical)} value(s) are typical assumptions: '
                f'{esc(", ".join(i.get("label", "") for i in typical[:8]))}{"…" if len(typical) > 8 else ""}. Change them before saving if you know the real size.</div>'
                if typical else '')
    return f'''<div class="cv-row" style="grid-template-columns:minmax(0,2.2fr) minmax(260px,1fr)"><section class="cv-card"><h3>Materials, labour &amp; services</h3>
<p class="sub">{len(payload.get("rows", []))} work items · built-up {sqft:,.0f} sq.ft · {int(payload.get("floors") or 1)} floor(s)</p>
<div class="scroll"><table class="cv-mt"><tr><th>Item</th><th style="text-align:right">Quantity</th><th style="text-align:right">Rate</th><th style="text-align:right">Amount</th></tr>{mats}</table></div>{cost_html}</section>
<section class="cv-card"><h3>Work items</h3><ul style="margin:0;padding-left:18px;font-size:13.5px">{items}</ul></section></div>
{typ_html}<details class="cv-card" style="margin-top:12px"><summary><b>How it was worked out</b> (notes)</summary><ul>{notes}</ul></details>'''
