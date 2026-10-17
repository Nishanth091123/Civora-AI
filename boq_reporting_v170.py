"""Civora AI v1.7.0: signed preview, explicit save, editable material rates and exports."""
import io, json, uuid, secrets, time, math
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
from itsdangerous import URLSafeSerializer, BadSignature

def _init(db):
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS civora_boq_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        c.execute('''CREATE TABLE IF NOT EXISTS civora_boq_reports (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, drawing_id TEXT NOT NULL,
            payload TEXT NOT NULL, created INTEGER NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id))''')
        r=c.execute("SELECT value FROM civora_boq_settings WHERE key='signing_key'").fetchone()
        if not r:
            c.execute("INSERT INTO civora_boq_settings(key,value) VALUES('signing_key',?)",(secrets.token_hex(32),))
            r=c.execute("SELECT value FROM civora_boq_settings WHERE key='signing_key'").fetchone()
        return r['value']

def make_signed_preview(db, payload):
    key=_init(db)
    return URLSafeSerializer(key,salt='civora-boq-v170').dumps(payload)

def _read_signed(db, token):
    try:
        data=URLSafeSerializer(_init(db),salt='civora-boq-v170').loads(token)
        if not isinstance(data,dict) or not isinstance(data.get('rows'),list):raise ValueError('Invalid payload')
        return data
    except (BadSignature,ValueError,TypeError):raise HTTPException(400,'Preview expired or altered. Recalculate before saving.')

def _get(db,pid,fid,bid):
    with db() as c:
        r=c.execute('SELECT * FROM civora_boq_reports WHERE id=? AND project_id=? AND drawing_id=?',(bid,pid,fid)).fetchone()
    if not r:raise HTTPException(404,'BOQ not found')
    return json.loads(r['payload'])

def _materials(data):
    for ri,row in enumerate(data.get('rows',[])):
        for mi,item in enumerate(row.get('items',[])):
            qty=float(item.get('quantity') or 0)
            rate=float(item.get('rate') or 0)
            yield ri,mi,row,item,qty,rate,qty*rate

def _fmt(n):return f'{n:,.2f}'

def _cost_summary(data):
    material=sum(amount for *_,amount in _materials(data))
    extras=data.get('cost_extras') or {}
    labour=float(extras.get('labour',0) or 0)
    transport=float(extras.get('transport',0) or 0)
    other=float(extras.get('other',0) or 0)
    tax_pct=float(extras.get('tax_percent',0) or 0)
    subtotal=material+labour+transport+other
    tax=subtotal*tax_pct/100
    return {'material':material,'labour':labour,'transport':transport,'other':other,'subtotal':subtotal,'tax_percent':tax_pct,'tax':tax,'grand_total':subtotal+tax}


def register_boq_reporting(app,db,owned_project,csrf,check_csrf,layout,esc):
    _init(db)
    def url(pid,fid):return f'/projects/{pid}/drawings/{fid}/boq'
    def validate(request,pid,fid):
        owned_project(request,pid)
        with db() as c:r=c.execute('SELECT id FROM uploads WHERE id=? AND project_id=?',(fid,pid)).fetchone()
        if not r:raise HTTPException(404,'Drawing not found')

    @app.post('/projects/{pid}/drawings/{fid}/boq/save')
    async def save(request:Request,pid:str,fid:str):
        validate(request,pid,fid)
        form=await request.form();check_csrf(request,str(form.get('csrf_token','')))
        data=_read_signed(db,str(form.get('signed_preview','')))
        if data.get('project_id')!=pid or data.get('drawing_id')!=fid:raise HTTPException(400,'Drawing mismatch')
        if form.get('confirm_assumptions')!='yes':raise HTTPException(400,'Review and confirm quantities before saving')
        for _,_,_,item,_,_,_ in _materials(data):item['rate']=0.0
        data['status']='DRAFT – ASSUMPTIONS REQUIRE VERIFICATION'
        bid=str(uuid.uuid4())
        with db() as c:c.execute('INSERT INTO civora_boq_reports(id,project_id,drawing_id,payload,created) VALUES(?,?,?,?,?)',(bid,pid,fid,json.dumps(data,ensure_ascii=False),int(time.time())))
        return RedirectResponse(url(pid,fid)+'/'+bid,status_code=303)

    @app.get('/projects/{pid}/drawings/{fid}/boq')
    def reports(request:Request,pid:str,fid:str):
        validate(request,pid,fid)
        with db() as c:records=c.execute('SELECT id,created FROM civora_boq_reports WHERE project_id=? AND drawing_id=? ORDER BY created DESC',(pid,fid)).fetchall()
        links=''.join(f'<tr><td>{time.strftime("%Y-%m-%d %H:%M",time.localtime(r["created"]))}</td><td><a href="{url(pid,fid)}/{r["id"]}">Open saved BOQ</a></td></tr>' for r in records)
        return layout(request,'Saved BOQ Reports',f'<h1>Saved Drawing BOQ Reports</h1><div class="card"><table><tr><th>Saved at</th><th>Report</th></tr>{links or "<tr><td colspan=2>No saved BOQ yet</td></tr>"}</table></div><a href="/projects/{pid}/drawings/{fid}/intelligence">← Drawing Intelligence</a>')

    @app.get('/projects/{pid}/drawings/{fid}/boq/{bid}')
    def detail(request:Request,pid:str,fid:str,bid:str):
        validate(request,pid,fid);data=_get(db,pid,fid,bid)
        items='';total=0
        for ri,mi,row,item,qty,rate,amount in _materials(data):
            total+=amount
            items+=f'<tr><td>{esc(row["work"])}</td><td>{esc(str(item.get("material","")))}</td><td>{_fmt(qty)} {esc(str(item.get("unit","")))}</td><td><input type="number" min="0" max="100000000" step="any" name="rate_{ri}_{mi}" value="{rate:.2f}" style="max-width:135px"></td><td>{_fmt(amount)}</td></tr>'
        # Work-wise cost audit: the same saved quantities and rates as the BOQ table.
        work_costs = {}
        unrated = 0
        for _,_,work_row,material,quantity,rate,amount in _materials(data):
            work_name = str(work_row.get('work','Unknown'))
            work_costs[work_name] = work_costs.get(work_name,0.0) + amount
            if quantity > 0 and rate == 0: unrated += 1
        work_summary = ''.join(f'<tr><td>{esc(name)}</td><td>₹ {_fmt(cost)}</td></tr>' for name,cost in work_costs.items())
        cost=_cost_summary(data)
        extras=data.get('cost_extras') or {}
        fields=''.join(f'<label style="display:inline-block;margin:8px">{label}<input type="number" min="0" max="100000000" step="any" name="{key}" value="{float(extras.get(key,0) or 0):.2f}" style="max-width:145px"></label>' for key,label in [('labour','Labour (INR)'),('transport','Transport (INR)'),('other','Other charges (INR)'),('tax_percent','Tax (%)')])
        cost_form=f'<div class="card"><h2>Project Cost Summary</h2><p>Material: INR {_fmt(cost["material"])} | Labour: INR {_fmt(cost["labour"])} | Transport: INR {_fmt(cost["transport"])} | Other: INR {_fmt(cost["other"])}</p><p>Subtotal: INR {_fmt(cost["subtotal"])} | Tax ({cost["tax_percent"]:.2f}%): INR {_fmt(cost["tax"])}</p><h3>Estimated Grand Total: INR {_fmt(cost["grand_total"])}</h3><form method="post" action="{url(pid,fid)}/{bid}/costs"><input type="hidden" name="csrf_token" value="{csrf(request)}">{fields}<button type="submit">Save cost adjustments</button></form><p class="hint">Zero rates are missing prices, not free materials. Tax is calculated on material plus entered charges. Review applicable tax treatment before use.</p></div>'
        summary_html = f'<div class="card" style="margin-top:16px"><h2>Work-wise Material Cost Summary</h2><table><tr><th>Work</th><th>Material Cost</th></tr>{work_summary}</table><p><strong>Grand total: ₹ {_fmt(total)}</strong></p><p class="hint">{unrated} material lines have a zero rate. These are not free materials; enter prices before using the estimate for budgeting.</p></div>'
        basis=''.join(f'<tr><td>{esc(x["measurement"])}</td><td>{_fmt(float(x["quantity"]))} {esc(x["unit"])}</td></tr>' for x in data.get('breakdown',[]))
        notes=''.join(f'<p class="hint">{esc(str(x))}</p>' for x in data.get('notes',[]))
        return layout(request,'Saved Draft BOQ',f'''<span class="eyebrow">SAVED DRAFT · NOT VERIFIED FOR PROCUREMENT</span><h1>BOQ – {esc(data.get('drawing_name','Drawing'))}</h1><p class="notice">Measurement basis (masonry): <b>{esc(data.get('measurement_basis_label') or 'External face (saved before v2.4.1)')}</b> · External plaster: external face</p><p class="hint">Quantities are based on drawing extraction and may contain provisional assumptions. Rates start at zero; enter your own material rates and save.</p><div class="card"><form method="post" action="{url(pid,fid)}/{bid}/rates"><input type="hidden" name="csrf_token" value="{csrf(request)}"><div class="scroll"><table><tr><th>Work</th><th>Material</th><th>Quantity</th><th>Rate / unit (₹)</th><th>Amount (₹)</th></tr>{items}</table></div><h3>Estimated material cost: ₹ {_fmt(total)}</h3><p class="hint">Material-only cost; labour, transport, taxes and other charges are not included.</p><button type="submit">Save rates & recalculate</button></form></div>{summary_html}{cost_form}<div class="card" style="margin-top:16px"><h2>Measurement basis & deductions</h2><table><tr><th>Measurement</th><th>Quantity</th></tr>{basis}</table>{notes}</div><p><a href="{url(pid,fid)}/{bid}/excel">Download Excel</a> · <a href="{url(pid,fid)}/{bid}/pdf">Download PDF</a> · <a href="{url(pid,fid)}">Saved reports</a></p>''')

    @app.post('/projects/{pid}/drawings/{fid}/boq/{bid}/rates')
    async def update_rates(request:Request,pid:str,fid:str,bid:str):
        validate(request,pid,fid);form=await request.form();check_csrf(request,str(form.get('csrf_token','')))
        data=_get(db,pid,fid,bid)
        import rates_v260
        drop=[]
        for ri,mi,row,item,_,_,_ in _materials(data):
            # v3.9.0: every line can be edited by hand - rate AND quantity - or removed; hand edits are kept on re-pricing
            if form.get(f'del_{ri}_{mi}')=='1':
                drop.append((ri,mi))
                if row.get(rates_v260.AUTO_TAG):
                    data.setdefault('removed_auto',[]).append(item.get('material'))
                continue
            for key,field,flag,hi in (('rate',f'rate_{ri}_{mi}','manual_rate',1e8),('quantity',f'qty_{ri}_{mi}','manual_qty',1e9)):
                raw=form.get(field)
                if raw is None:continue
                raw=str(raw).strip().replace(',','')
                if raw=='':continue
                try:v=float(raw)
                except ValueError:raise HTTPException(400,f'Invalid {key}')
                if not math.isfinite(v) or not 0<=v<=hi:raise HTTPException(400,f'{key.title()} must be between 0 and {hi:,.0f}')
                nd=2 if key=='rate' else 3
                v=round(v,nd)
                if abs(v-round(float(item.get(key) or 0),nd))>1e-9:     # the page shows rounded values
                    item[key]=v;item[flag]=True
        for ri,mi in sorted(drop,reverse=True):
            del data['rows'][ri]['items'][mi]
        data['rows']=[r for r in data.get('rows',[]) if r.get('items') or r.get('custom')]
        with db() as c:c.execute('UPDATE civora_boq_reports SET payload=? WHERE id=? AND project_id=? AND drawing_id=?',(json.dumps(data,ensure_ascii=False),bid,pid,fid))
        return RedirectResponse(url(pid,fid)+'/'+bid,status_code=303)

    @app.post('/projects/{pid}/drawings/{fid}/boq/{bid}/addline')
    async def add_line(request:Request,pid:str,fid:str,bid:str):
        """v3.9.0: add any item by hand (compound wall, gate, borewell, interior …)."""
        validate(request,pid,fid);form=await request.form();check_csrf(request,str(form.get('csrf_token','')))
        data=_get(db,pid,fid,bid)
        name=str(form.get('item','')).strip()[:120];unit=str(form.get('unit','nos')).strip()[:20] or 'nos'
        group=str(form.get('group','')).strip()[:80] or 'Extra items (added by hand)'
        try:
            q=float(str(form.get('quantity','0')).replace(',',''));r=float(str(form.get('rate','0')).replace(',',''))
        except ValueError:raise HTTPException(400,'Enter numbers for quantity and rate')
        if not name or not (math.isfinite(q) and 0<q<=1e9 and math.isfinite(r) and 0<=r<=1e8):raise HTTPException(400,'Enter an item name, a quantity above 0 and a rate')
        row=next((x for x in data.get('rows',[]) if x.get('work')==group and x.get('custom')),None)
        if row is None:
            row={'work':group,'area':0,'items':[],'custom':True};data.setdefault('rows',[]).append(row)
        row['items'].append({'material':name,'quantity':round(q,3),'unit':unit,'rate':round(r,2),'basis':'Added by hand','manual_rate':True,'manual_qty':True})
        with db() as c:c.execute('UPDATE civora_boq_reports SET payload=? WHERE id=? AND project_id=? AND drawing_id=?',(json.dumps(data,ensure_ascii=False),bid,pid,fid))
        return RedirectResponse(url(pid,fid)+'/'+bid,status_code=303)

    @app.post('/projects/{pid}/drawings/{fid}/boq/{bid}/reprice')
    async def reprice(request:Request,pid:str,fid:str,bid:str):
        """v3.9.0: re-price this estimate with the Rate Master. Hand-typed rates are kept unless 'replace' is ticked."""
        validate(request,pid,fid);form=await request.form();check_csrf(request,str(form.get('csrf_token','')))
        data=_get(db,pid,fid,bid)
        import rates_v260
        if form.get('replace')=='1':
            for row in data.get('rows',[]):
                for it in row.get('items',[]):
                    if not row.get('custom'):it.pop('manual_rate',None);it.pop('manual_qty',None)
            data.pop('removed_auto',None)
            (data.get('cost_extras') or {}).pop('manual',None)
        with db() as c:
            p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
            rates=rates_v260.rates_for_project(c,p,request.state.cv_actor[0] if getattr(request.state,'cv_actor',None) else p['owner_id'])
            rates_v260.apply_rates(data,rates,rates_v260.builtup_sqft_of(data,p))
            c.execute('UPDATE civora_boq_reports SET payload=? WHERE id=? AND project_id=? AND drawing_id=?',(json.dumps(data,ensure_ascii=False),bid,pid,fid))
        return RedirectResponse(url(pid,fid)+'/'+bid,status_code=303)

    @app.post('/projects/{pid}/drawings/{fid}/boq/{bid}/costs')
    async def update_costs(request:Request,pid:str,fid:str,bid:str):
        validate(request,pid,fid)
        form=await request.form()
        check_csrf(request,str(form.get('csrf_token','')))
        data=_get(db,pid,fid,bid)
        old=data.get('cost_extras') or {}
        extras={k:v for k,v in old.items() if k not in ('labour','transport','other','tax_percent','manual')}
        manual=set(old.get('manual') or [])
        for key in ('labour','transport','other','tax_percent'):
            try: value=float(str(form.get(key,'0')).strip())
            except (TypeError,ValueError): raise HTTPException(400,'Invalid cost adjustment')
            limit=100 if key=='tax_percent' else 100000000
            if not math.isfinite(value) or not 0<=value<=limit:raise HTTPException(400,'Invalid cost adjustment range')
            extras[key]=round(value,2)
            if abs(extras[key]-float(old.get(key) or 0))>1e-9:manual.add(key)   # v3.9.0: typed by hand -> kept on re-pricing
        if form.get('reset_manual')=='1':manual=set()
        extras['manual']=sorted(manual)
        data['cost_extras']=extras
        with db() as c:c.execute('UPDATE civora_boq_reports SET payload=? WHERE id=? AND project_id=? AND drawing_id=?',(json.dumps(data,ensure_ascii=False),bid,pid,fid))
        return RedirectResponse(url(pid,fid)+'/'+bid,status_code=303)

    @app.get('/projects/{pid}/drawings/{fid}/boq/{bid}/excel')
    def excel(request:Request,pid:str,fid:str,bid:str):
        validate(request,pid,fid)
        data=_get(db,pid,fid,bid)
        from boq_export_v171 import excel_bytes
        output=io.BytesIO(excel_bytes(data))
        return StreamingResponse(output, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition':f'attachment; filename="Civora_BOQ_{bid[:8]}.xlsx"'})

    @app.get('/projects/{pid}/drawings/{fid}/boq/{bid}/pdf')
    def pdf(request:Request,pid:str,fid:str,bid:str):
        validate(request,pid,fid)
        data=_get(db,pid,fid,bid)
        from boq_export_v171 import pdf_bytes
        output=io.BytesIO(pdf_bytes(data))
        return StreamingResponse(output, media_type='application/pdf', headers={'Content-Disposition':f'attachment; filename="Civora_BOQ_{bid[:8]}.pdf"'})
