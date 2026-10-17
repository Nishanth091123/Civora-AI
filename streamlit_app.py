"""Civora AI Lite - Streamlit version of Quick Estimate.

Deploy on Streamlit Community Cloud with  Main file path:  streamlit_app.py
(The full Civora app is a FastAPI web app and cannot run on Streamlit; this page reuses its calculation engine.)
"""
import streamlit as st

import civora_lite as cl

st.set_page_config(page_title='Civora AI Lite · Quick Estimate', page_icon='🏗️', layout='wide')

st.markdown("""<style>
.block-container{padding-top:1.6rem;max-width:1200px}
.cv-hero{background:#142b45;color:#fff;border-radius:16px;padding:22px 26px;margin-bottom:14px}
.cv-hero h1{color:#fff;margin:0;font-size:30px}.cv-hero p{color:#c9d8ea;margin:6px 0 0}
.cv-ta{color:#0d9488;font-size:14px}
.cv-warn{background:#fef2f2;border:1px solid #fecaca;color:#7f1d1d;border-radius:10px;padding:10px 12px;font-size:13px}
</style>""", unsafe_allow_html=True)

st.markdown('<div class="cv-hero"><h1>Civora AI Lite</h1><p>Type the built-up area → materials, steel and cost in one click · '
            'கட்டிடப் பரப்பை உள்ளிடுங்கள் → பொருட்கள், கம்பி, செலவு</p></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ inputs
with st.sidebar:
    st.header('Building · கட்டிடம்')
    name = st.text_input('Project name', 'My house')
    area = st.number_input('Built-up area, all floors (sq.ft)', min_value=100, max_value=1_000_000, value=1000, step=50)
    floors = st.selectbox('Floors · தளங்கள்', [1, 2, 3, 4], format_func=lambda n: 'G (ground)' if n == 1 else f'G + {n - 1}')
    st.header('My rates · என் விலைகள்')
    st.caption('Enter today’s prices from your dealer. Leave 0 if not known — those lines show as "not priced". '
               'Civora does not supply market prices.')
    rates = {}
    with st.expander('Materials', expanded=True):
        for key, en, ta, unit, group in cl.RATE_ITEMS:
            if group == 'material':
                rates[key] = st.number_input(f'{en} ({unit})', min_value=0.0, value=0.0, step=1.0, key=key, help=ta)
    with st.expander('Work items, labour & GST'):
        for key, en, ta, unit, group in cl.RATE_ITEMS:
            if group != 'material':
                mx = 100.0 if key in cl.PERCENT_KEYS else 1e7
                rates[key] = st.number_input(f'{en} ({unit})', min_value=0.0, max_value=mx, value=0.0, step=1.0, key=key, help=ta)

try:
    payload = cl.run(area, floors, rates, name)
except ValueError as ex:
    st.error(str(ex))
    st.stop()

h = cl.headline(payload)
c = cl.cost(payload)

# ------------------------------------------------------------------ headline
k = st.columns(5)
k[0].metric('Cement · சிமெண்ட்', f'{h["cement_bags"]:,.0f} bags')
k[1].metric('Steel · கம்பி', f'{h["steel_kg"]:,.0f} kg', help='Planning allowance from thumb rules, not a bar bending schedule')
k[2].metric('Bricks · செங்கல்', f'{h["bricks"]:,.0f} nos')
k[3].metric('RMC concrete', f'{h["rmc_m3"]:,.1f} m³')
k[4].metric('Estimated total', cl.inr(c['total']) if c['total'] else 'add rates',
            f'{cl.inr(c["per_sqft"])} per sq.ft' if c['per_sqft'] else None, delta_color='off')
if c['unrated']:
    st.info(f'{c["unrated"]} material line(s) have no rate yet — add rates in the sidebar to complete the total.')

tab1, tab2, tab3, tab4 = st.tabs(['Materials · பொருட்கள்', 'Work items · வேலைகள்', 'Cost · செலவு', 'Assumptions · அனுமானங்கள்'])

with tab1:
    st.dataframe([{'Material': m, 'Quantity': round(q, 2), 'Unit': u, 'Amount (₹)': round(a) if a else None}
                  for m, q, u, a in cl.materials(payload)], use_container_width=True, hide_index=True)

with tab2:
    for row in payload['rows']:
        amt = sum(cl._f(i.get('quantity')) * cl._f(i.get('rate')) for i in row['items'])
        with st.expander(f'{row["work"]}' + (f'  ·  {cl.inr(amt)}' if amt else '')):
            st.dataframe([{'Material': i.get('material'), 'Quantity': round(cl._f(i.get('quantity')), 3), 'Unit': i.get('unit'),
                           'Rate (₹)': cl._f(i.get('rate')) or None, 'How it was worked out': i.get('basis', '')} for i in row['items']],
                         use_container_width=True, hide_index=True)

with tab3:
    rows = [('Materials', c['material']), ('Labour', c['labour']), ('Transport', c['transport']), ('Other charges', c['other']),
            (f'GST ({c["tax_percent"]:g}%)', c['tax']), ('Total estimate', c['total'])]
    st.dataframe([{'Item': n, 'Amount (₹)': round(v)} for n, v in rows], use_container_width=True, hide_index=True)
    st.caption('Labour = labour rate × built-up area. Transport = % of material cost. GST on materials + charges.')

with tab4:
    st.write('Only the area and floors came from you. Everything else is a **typical value** — check before ordering.')
    st.dataframe([{'Input': i['label'], 'Value': i['value'], 'Unit': i['unit'], 'Source': cl.SOURCE_LABEL.get(i['source'], i['source'])}
                  for i in payload['inputs']], use_container_width=True, hide_index=True)
    for n in payload['notes'][:8]:
        st.caption('• ' + n)

# ------------------------------------------------------------------ downloads
st.subheader('Download · பதிவிறக்கம்')
d1, d2, _ = st.columns([1, 1, 3])
safe = ''.join(ch for ch in name if ch.isalnum() or ch in ' -_').strip().replace(' ', '_') or 'Civora'
d1.download_button('Excel BOQ', cl.excel(payload), f'{safe}_Civora_BOQ.xlsx',
                   'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
d2.download_button('PDF summary', cl.pdf(payload), f'{safe}_Civora_BOQ.pdf', 'application/pdf', use_container_width=True)

st.markdown(f'<div class="cv-warn">{cl.DISCLAIMER}</div>', unsafe_allow_html=True)
st.caption('Full Civora AI (drawings, Structural & BBS Studio, reinforcement details, team access, reports): '
           'https://github.com/Nishanth091123/Civora-AI')
