"""Civora AI v3.0 - Settings: Guided / Expert mode and English / Tamil menu.

One additive table: civora_user_prefs_v300(user_id, mode, lang, updated).
Only preferences that actually work are shown as controls; planned ones are listed as "planned".
"""
import time

MODES = {'guided': ('Guided mode', 'எளிய முறை', 'Step-by-step help, examples and Tamil/English tips. Advanced engineering settings are tucked away.'),
         'expert': ('Expert mode', 'நிபுணர் முறை', 'Detailed tables, measurement basis, steel kg/m³ and every advanced setting shown.')}
LANGS = {'en': ('English', 'English menus and screens.'),
         'ta': ('தமிழ் + English', 'Menus, headings, buttons and labels on the main screens in Tamil. Numbers, units and site terms (BOQ, BBS, RCC, M20) stay in English.')}
DEFAULT = {'mode': 'guided', 'lang': 'en'}


def init(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS civora_user_prefs_v300 (
            user_id TEXT PRIMARY KEY, mode TEXT NOT NULL, lang TEXT NOT NULL, updated INTEGER NOT NULL)''')


def get_prefs(c, uid):
    if not uid:
        return dict(DEFAULT)
    try:
        r = c.execute('SELECT mode, lang FROM civora_user_prefs_v300 WHERE user_id=?', (uid,)).fetchone()
    except Exception:          # table not created yet (first start) - defaults
        return dict(DEFAULT)
    if not r:
        return dict(DEFAULT)
    return {'mode': r[0] if r[0] in MODES else 'guided', 'lang': r[1] if r[1] in LANGS else 'en'}


def register_settings_v300(app, db, require, csrf, check_csrf, layout, esc):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse
    init(db)

    @app.get('/settings')
    def settings(request: Request):
        u = require(request)
        with db() as c:
            pr = get_prefs(c, u['id'])
        saved = request.query_params.get('saved') == '1'

        def choice(name, key, title, sub, desc, current):
            return (f'<label><input type="radio" name="{name}" value="{key}"{" checked" if key == current else ""}>'
                    f'<span><b>{esc(title)}</b>{f"<em style=font-style:normal>{esc(sub)}</em>" if sub else ""}{esc(desc)}</span></label>')
        modes = ''.join(choice('mode', k, v[0], v[1], v[2], pr['mode']) for k, v in MODES.items())
        langs = ''.join(choice('lang', k, v[0], '', v[1], pr['lang']) for k, v in LANGS.items())
        note = '<div class="cv-banner"><div><b>Settings saved.</b>They apply on every page from now on.</div></div>' if saved else ''
        return layout(request, 'Settings', f'''<span class="eyebrow">SETTINGS · அமைப்புகள்</span><h1>Personalise Civora</h1>{note}
<form method="post" action="/settings" style="max-width:860px"><input type="hidden" name="csrf_token" value="{csrf(request)}">
<section class="wz-sec"><h2>How much detail?</h2><p class="ta">Both modes use the same calculations. Engineer review warnings show in both.</p><div class="wz-choice" style="grid-template-columns:repeat(2,minmax(0,1fr))">{modes}</div></section>
<section class="wz-sec"><h2>Language · மொழி</h2><p class="ta">Tamil covers the dashboard, projects, studios, Cost &amp; BOQ, BBS, reports, team and settings. Anything not yet translated stays in English.</p><div class="wz-choice" style="grid-template-columns:repeat(2,minmax(0,1fr))">{langs}</div></section>
<section class="wz-sec"><h2>Also here</h2><ul class="cv-files"><li><span class="nm">Your local prices<small>Rate Master</small></span><a class="cv-btn sm ghost" href="/rates">Open</a></li>
<li><span class="nm">Move my data<small>Download your projects here and upload them into another Civora (PC → online)</small></span><a class="cv-btn sm ghost" href="/transfer">Open</a></li>
<li><span class="nm">Database backups<small>Automatic daily backup on this computer; manual backup with backup.bat</small></span></li>
<li><span class="nm">Units, theme, notifications<small>Planned — not available yet</small></span></li></ul></section>
<div class="actions"><button class="cv-btn">Save settings</button></div></form>''')

    @app.post('/settings')
    async def save_settings(request: Request):
        u = require(request)
        form = await request.form()
        check_csrf(request, str(form.get('csrf_token', '')))
        mode, lang = form.get('mode'), form.get('lang')
        if mode not in MODES or lang not in LANGS:
            raise HTTPException(400, 'Choose a mode and a language')
        with db() as c:
            c.execute('INSERT INTO civora_user_prefs_v300(user_id,mode,lang,updated) VALUES(?,?,?,?) '
                      'ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode, lang=excluded.lang, updated=excluded.updated',
                      (u['id'], mode, lang, int(time.time())))
        return RedirectResponse('/settings?saved=1', 303)
