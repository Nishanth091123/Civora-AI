"""Civora AI Lite - the calculation part used by the Streamlit app (no Streamlit import, so it can be tested).

Reuses the SAME engine as the full Civora web app: quick_v280 -> smart_estimate_v260 -> engineering.takeoff,
rates_v260.apply_rates for pricing and boq_export_v171 for Excel / PDF. Nothing is recalculated here.
"""
import sys
from collections import OrderedDict
from pathlib import Path

# Works in both layouts: streamlit_demo/ inside the repo, or everything flat in the repo root
# (uploading folders through the GitHub website flattens them).
HERE = Path(__file__).resolve().parent
for _d in (HERE, HERE.parent):
    if (_d / 'quick_v280.py').is_file() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import quick_v280 as quick                                # noqa: E402
import rates_v260 as rv                                   # noqa: E402
import smart_estimate_v260 as se                          # noqa: E402
import workflow_v250 as wf                                # noqa: E402
from engineering import takeoff                           # noqa: E402

RATE_ITEMS = rv.RATE_ITEMS
PERCENT_KEYS = rv.PERCENT_KEYS
SOURCE_LABEL = se.SOURCE_LABEL
DISCLAIMER = ('DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED. Quick Estimate uses only the built-up area; plan shape, walls, '
              'openings and structure are typical values. Quantities and costs are planning estimates, not a structural design, '
              'and do not certify compliance with any code.')


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def run(area_sqft, floors, rates=None, name='Quick estimate'):
    """Full quick estimate as a BOQ payload (same shape the web app saves). Raises ValueError on bad input."""
    area, floors = quick.parse_quick({'area': str(area_sqft), 'floors': str(floors)})
    inp, opts, result = quick.quick_estimate(area, floors, takeoff)
    project = {'id': 'streamlit-lite', 'name': name}
    payload = se.build_payload(project, {'id': 'lite', 'original_name': 'Quick estimate (area only)'}, inp, opts, result, {})
    payload['source_detail'] = 'quick_v280'
    payload['project_name'] = name
    payload['notes'].insert(0, 'QUICK ESTIMATE from built-up area only: plan shape, walls, openings and structure are typical values.')
    rates = {k: _f(v) for k, v in (rates or {}).items() if _f(v) > 0}
    if rates:
        rv.apply_rates(payload, rates, payload['builtup_sqft'])
    return payload


def materials(payload):
    """[(material, quantity, unit, amount)] summed over all work items, biggest first by amount then quantity."""
    agg = OrderedDict()
    for row in payload.get('rows', []):
        for i in row.get('items', []):
            key = (str(i.get('material', '')), str(i.get('unit', '')))
            q, a = agg.get(key, (0.0, 0.0))
            agg[key] = (q + _f(i.get('quantity')), a + _f(i.get('quantity')) * _f(i.get('rate')))
    out = [(m, q, u, a) for (m, u), (q, a) in agg.items() if q > 0]
    order = ['Ready-mix concrete (RMC)', 'Steel planning allowance (not BBS)', 'Cement', 'Bricks', 'Sand', 'M-sand', 'Coarse aggregate']
    out.sort(key=lambda r: (order.index(r[0]) if r[0] in order else len(order), -r[3]))
    return out


def cost(payload):
    c = wf.boq_cost(payload)
    sub = c['material'] + c['labour'] + c['transport'] + c['other']
    c['subtotal'] = sub
    c['total'] = sub + c['tax']
    sqft = _f(payload.get('builtup_sqft'))
    c['per_sqft'] = c['total'] / sqft if sqft and c['total'] else 0.0
    return c


def headline(payload):
    """Key numbers for the top cards."""
    mats = {m: q for m, q, u, a in materials(payload)}
    return {'cement_bags': mats.get('Cement', 0.0), 'steel_kg': mats.get('Steel planning allowance (not BBS)', 0.0),
            'bricks': mats.get('Bricks', 0.0), 'rmc_m3': mats.get('Ready-mix concrete (RMC)', 0.0),
            'sand_m3': mats.get('Sand', 0.0) + mats.get('M-sand', 0.0)}


def excel(payload):
    from boq_export_v171 import excel_bytes
    return excel_bytes(payload)


def pdf(payload):
    from boq_export_v171 import pdf_bytes
    return pdf_bytes(payload)


def inr(v):
    v = _f(v)
    if v >= 1e7:
        return f'₹ {v / 1e7:,.2f} Cr'
    if v >= 1e5:
        return f'₹ {v / 1e5:,.2f} L'
    return f'₹ {v:,.0f}'
