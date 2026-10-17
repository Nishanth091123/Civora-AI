import re
"""Civora AI v2.5.0 application shell and dashboard home.

Pure HTML rendering (no FastAPI imports) so it can be tested and previewed on its own.
app.layout() delegates here, so EVERY page - including all older modules - gets the
new navy sidebar, search header and mobile navigation without changing those modules.
"""
import html as _html

VERSION = '2.5.0'


def esc(s):
    return _html.escape(str(s if s is not None else ''), quote=True)


# ---------------------------------------------------------------- icons (24px stroke icons)
ICONS = {
    'home': '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'folder': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    'calc': '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2M12 11h2M16 11v6M8 15h2M12 15h2"/>',
    'shield': '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    'drawing': '<path d="M4 4h16v16H4z"/><path d="M4 10h7v10M11 4v6M15 10h5"/>',
    'layers': '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    'cube': '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M12 22V12M21 7l-9 5-9-5"/>',
    'beam': '<path d="M3 6h18M3 18h18M7 6v12M17 6v12"/>',
    'rupee': '<path d="M6 4h12M6 9h12M6 4c7 0 7 10 0 10l8 6"/>',
    'report': '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
    'search': '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    'bell': '<path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
    'users': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    'truck': '<path d="M2 6h12v10H2zM14 10h4l3 3v3h-7"/><circle cx="6" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
    'book': '<path d="M4 4h6a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4z"/><path d="M20 4h-5a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h5z"/>',
    'settings': '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    'upload': '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v4h16v-4"/>',
    'download': '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/>',
    'check': '<path d="M5 12l5 5 9-10"/>',
    'menu': '<path d="M4 6h16M4 12h16M4 18h16"/>',
    'logout': '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/>',
    'pin': '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    'chart': '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    'arrow': '<path d="M5 12h14M13 6l6 6-6 6"/>',
    'site': '<path d="M3 21h18M5 21V10l7-5 7 5v11"/><path d="M9 21v-6h6v6"/>',
    'brick': '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M3 10h18M3 15h18M9 5v5M15 10v5M9 15v4"/>',
    'user': '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
}


def icon(name, size=20, cls='cv-ic'):
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{ICONS.get(name, ICONS["folder"])}</svg>')


LOGO = ('<svg width="36" height="36" viewBox="0 0 40 40" aria-hidden="true"><defs><linearGradient id="cvg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#2bb8ff"/><stop offset="1" stop-color="#2563eb"/></linearGradient></defs>'
        '<rect width="40" height="40" rx="11" fill="url(#cvg)"/><path d="M11 29V17l9-6 9 6v12h-6v-7h-6v7z" fill="#fff"/></svg>')

# ---------------------------------------------------------------- workflow model
# key, number, title, short, colour, icon
STEPS = [
    ('setup', 1, 'Project Setup', 'Type, location, area', '#2563eb', 'folder'),
    ('input', 2, 'Drawings & Input', 'Upload plans, dimensions', '#16a34a', 'drawing'),
    ('materials', 3, 'Quantity Estimation', 'Materials & BOQ', '#f59e0b', 'calc'),
    ('structure', 4, 'Design Guidance', 'Structural review', '#7c3aed', 'shield'),
    ('cost', 5, 'Cost & Budget', 'Rates & total cost', '#ea580c', 'rupee'),
    ('reports', 6, 'Reports & Execute', 'Excel, PDF, download', '#0ea5e9', 'report'),
]
STEP_KEYS = [s[0] for s in STEPS]

CATEGORIES = [
    ('Residential', 'Homes, villas, apartments', 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=640'),
    ('Commercial', 'Offices, shops, complexes', 'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=640'),
    ('Industrial', 'Factories, warehouses', 'https://images.unsplash.com/photo-1581092335878-2d9ff86ca2bf?w=640'),
    ('Infrastructure', 'Roads, bridges, utilities', 'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=640'),
]
CAT_ICONS = {'Residential': 'home', 'Commercial': 'site', 'Industrial': 'truck', 'Infrastructure': 'beam'}
CATEGORY_COLOURS = {'Residential': '#2563eb', 'Commercial': '#7c3aed', 'Industrial': '#ea580c',
                    'Infrastructure': '#16a34a', 'Custom': '#0ea5e9'}


def inr_short(v):
    """Indian short money format: 4.25 L, 1.20 Cr."""
    v = float(v or 0)
    if v >= 1e7:
        return f'₹ {v/1e7:,.2f} Cr'
    if v >= 1e5:
        return f'₹ {v/1e5:,.2f} L'
    return f'₹ {v:,.0f}'


def stepper(done=(), links=None, current=None):
    """Six-step progress bar. done: iterable of step keys that are complete."""
    done = set(done or ())
    links = links or {}
    if current is None:
        current = next((k for k in STEP_KEYS if k not in done), None)
    out = []
    for key, num, title, short, colour, ic in STEPS:
        state = 'done' if key in done else ('now' if key == current else 'todo')
        mark = icon('check', 16) if state == 'done' else str(num)
        href = links.get(key)
        tag_open = f'<a class="cv-step {state}" href="{esc(href)}"' if href else f'<div class="cv-step {state}"'
        tag_close = '</a>' if href else '</div>'
        out.append(f'{tag_open} style="--c:{colour}"><span class="cv-dot">{mark}</span>'
                   f'<span class="cv-stxt"><b>{esc(title)}</b><small>{esc(short)}</small></span>{tag_close}')
    return '<div class="cv-steps">' + ''.join(out) + '</div>'


# ---------------------------------------------------------------- navigation
LABELS = {  # v3.0 menu labels, English / Tamil
    'Dashboard': 'முகப்பு', 'Projects': 'திட்டங்கள்', 'Drawing Studio': 'வரைபட ஸ்டுடியோ', 'Smart Estimate': 'மதிப்பீடு',
    'Structural Studio': 'கட்டமைப்பு', 'BBS & BOQ': 'BBS & BOQ', 'Rate Master': 'விலைப் பட்டியல்', 'Reports': 'அறிக்கைகள்',
    'Estimate': 'மதிப்பீடு', 'Structure': 'கட்டமைப்பு', 'Guide': 'வழிகாட்டி', 'More': 'மேலும்',
    'Team': 'குழு', 'Settings': 'அமைப்புகள்', 'WORKSPACE': 'பணியிடம்', 'MANAGEMENT': 'மேலாண்மை', 'Advanced tools': 'கூடுதல் கருவிகள்',
    'Guest Preview': 'விருந்தினர் பார்வை', 'Sign in': 'உள்நுழை', 'Create Account': 'கணக்கு உருவாக்கு', 'Home': 'முகப்பு',
}


def tr(text, lang='en'):
    return LABELS.get(text, text) if lang == 'ta' else text


SECTIONS = [  # v3.8.0: six sections only - everything else lives inside them
    ('home', 'Home', '/'),
    ('folder', 'Projects', '/projects'),
    ('calc', 'Estimate', '/estimate'),
    ('beam', 'Structure', '/structure'),
    ('book', 'Guide', '/guide'),
    ('menu', 'More', '/more'),
]
_SECTION_RX = [
    ('/estimate', re.compile(r'^/(estimate|quick|materials)(/|$)|^/projects/[^/]+/(smart|multi|studio|drawings|takeoff|quick|boq|materials|estimate|sqft-rate)(/|$)')),
    ('/structure', re.compile(r'^/structure(/|$)|^/projects/[^/]+/(structure|structural|bbs)(/|$)')),
    ('/guide', re.compile(r'^/guide(/|$)|^/projects/[^/]+/vastu(/|$)')),
    ('/more', re.compile(r'^/(more|rates|reports|settings|system|transfer|admin|bin)(/|$)|^/projects/[^/]+/(more|reports|team|data|workflow/download)(/|$)')),
    ('/projects', re.compile(r'^/projects(/|$)')),
    ('/', re.compile(r'^/$')),
]


def section_of(path):
    for href, rx in _SECTION_RX:
        if rx.search(path or '/'):
            return href
    return ''


def _nav_items(user, pid):
    if not user:
        return [('', [('home', 'Home', '/'), ('calc', 'Guest Preview', '/guest'),
                      ('user', 'Sign in', '/login'), ('plus', 'Create Account', '/register')])], []
    return [('', list(SECTIONS))], []


def _is_active(href, path):
    if href in [h for _, _, h in SECTIONS]:
        return section_of(path) == href
    h = href.split('#')[0]
    return path == h or (h != '/' and path.startswith(h + '/'))


def nav_html(user, pid, path, lang='en'):
    groups, _ = _nav_items(user, pid)
    links = []
    for title, items in groups:
        for ic, label, href in items:
            on = _is_active(href, path)
            links.append(f'<a class="cv-nl{" on" if on else ""}" href="{esc(href)}">{icon(ic)}<span>{esc(tr(label, lang))}</span></a>')
    return ''.join(links)


STAGE_LABEL = {'setup': 'Project setup', 'input': 'Drawings & input', 'materials': 'Quantity estimation',
               'structure': 'Design guidance', 'cost': 'Cost & budget', 'reports': 'Reports ready'}
ROLE_COLOURS = {'owner': '#2563eb', 'engineer': '#7c3aed', 'colleague': '#0d9488', 'dealer': '#c2410c', 'customer': '#0369a1'}


def context_bar(ctx):
    """Project context bar shown on every project page (v3.0)."""
    if not ctx:
        return ''
    pid = ctx['id']
    P = f'/projects/{pid}'
    role = ctx.get('role', 'owner')
    import team_v270
    rlabel, _, _, rc = team_v270.display(role, ctx.get('admin'))
    stage = ctx.get('stage')
    stage_html = (f'<span class="cv-cb-chip" style="background:#fef3c7;color:#92400e">Next: {esc(STAGE_LABEL.get(stage, stage))}</span>'
                  if stage else '<span class="cv-cb-chip" style="background:#ccfbf1;color:#115e59">All steps done</span>')
    rev = ctx.get('revisions', 0)
    rev_html = f'<span class="cv-cb-meta">Estimate rev {rev}</span>' if rev else '<span class="cv-cb-meta">No estimate yet</span>'
    tabs = [('Overview', P), ('Estimate', P + '/smart'), ('Structure', P + '/structure'), ('BOQ & Cost', P + '/boq'),
            ('Vastu', P + '/vastu'), ('More', P + '/more')]
    path = ctx.get('path', '')
    extra = {'Estimate': (P + '/multi', P + '/studio', P + '/drawings', P + '/takeoff', P + '/materials'),
             'Structure': (P + '/structural', P + '/bbs'), 'BOQ & Cost': (P + '/drawings/boq',),
             'More': (P + '/reports', P + '/team', P + '/data', P + '/workflow')}
    def _score(t, h):
        cands = [h] + list(extra.get(t, ()))
        return max([len(x) for x in cands if (path == x if x == P else path.startswith(x))] or [0])
    best = max(tabs, key=lambda th: _score(*th))
    sel = best[0] if _score(*best) else ''
    tab_html = ''.join(f'<a class="cv-cb-tab{" on" if t == sel else ""}" href="{esc(h)}">{esc(t)}</a>' for t, h in tabs)
    return (f'<div class="cv-ctx" role="region" aria-label="Current project"><div class="cv-cb-main"><a class="cv-cb-name" href="{P}">{esc(ctx["name"])}</a>'
            f'<span class="cv-cb-meta">{esc(ctx.get("type", ""))} · {esc(ctx.get("location", ""))}</span>{stage_html}{rev_html}'
            f'<span class="cv-cb-chip" style="background:{rc}1a;color:{rc}">{esc(rlabel)}</span>'
            + _saved_chip() + '</div>'
            f'<nav class="cv-cb-tabs" aria-label="Project sections">{tab_html}</nav></div>')


def _acct(user):
    """v3.9.2: account type under the name - only the site owner is Admin, everyone else is a User."""
    try:
        import admin_v380
        adm = admin_v380.is_site_owner(user)
    except Exception:
        adm = False
    return '<b style="color:#b45309">Admin</b>' if adm else 'User'


def _saved_chip():
    """v3.6.0: only say 'Saved' when the data survives a server restart."""
    try:
        import persistence_v360
        safe = persistence_v360.is_safe()
    except Exception:
        safe = True
    if safe:
        return f'<span class="cv-cb-meta" style="margin-left:auto">{icon("check", 14)} Saved</span>'
    return ('<a class="cv-cb-meta" href="/system/storage" style="margin-left:auto;color:#b91c1c;font-weight:700">'
            'Not backed up</a>')


def _initials(name):
    parts = [w for w in str(name or '').split() if w]
    return (''.join(w[0] for w in parts[:2]) or 'U').upper()


# ---------------------------------------------------------------- page
CSS = r"""
:root{--cv-navy:#142b45;--cv-navy2:#1b3758;--cv-blue:#2563eb;--cv-teal:#0d9488;--cv-amber:#f59e0b;--cv-red:#dc2626;--cv-bg:#f3f6fa;--cv-line:#e2e8f0;--cv-ink:#0f172a;--cv-mute:#5b6b7f}
.primary,button{background:var(--cv-blue)}
body{background:var(--cv-bg);color:var(--cv-ink);font:15px/1.5 "Segoe UI",system-ui,-apple-system,Arial,sans-serif}
.cv-shell{display:flex;min-height:100vh}
.cv-side{width:252px;flex-shrink:0;background:linear-gradient(180deg,var(--cv-navy),#1b3758);color:#cfe0f2;display:flex;flex-direction:column;position:sticky;top:0;height:100vh;overflow-y:auto;z-index:40}
.cv-brand{display:flex;align-items:center;gap:10px;padding:22px 20px 18px;color:#fff}
.cv-brand b{font-size:21px;letter-spacing:-.4px;display:block;line-height:1.1}.cv-brand b i{font-style:normal;color:#5cb4ff}
.cv-brand small{font-size:11px;color:#8fb0cf;letter-spacing:.3px}
.cv-nav{padding:6px 12px;flex:1}
.cv-nl{display:flex;align-items:center;gap:12px;padding:10px 12px;margin:2px 0;border-radius:10px;color:#c9dbee;font-weight:550;font-size:14.5px;text-decoration:none}
.cv-nl:hover{background:#ffffff12;color:#fff}.cv-nl.on{background:var(--cv-blue);color:#fff;box-shadow:0 6px 16px #2563eb55}
.cv-nl .cv-ic{flex-shrink:0;opacity:.95}
.cv-nl.soon{opacity:.55;cursor:default}.cv-nl.soon:hover{background:none;color:#c9dbee}
.cv-nl em{margin-left:auto;font-style:normal;font-size:10px;background:#ffffff1c;padding:2px 7px;border-radius:20px}
.cv-adv summary{cursor:pointer;list-style:none}.cv-adv summary::-webkit-details-marker{display:none}
.cv-adv summary::after{content:'\25BE';margin-left:auto;font-size:12px;opacity:.7}.cv-adv[open] summary::after{content:'\25B4'}
.cv-nl.sub{padding:8px 12px 8px 22px;font-size:13.5px;color:#a9c4de}
.cv-nsec{font-size:11px;text-transform:uppercase;letter-spacing:1.3px;color:#6f8fae;margin:16px 12px 6px}
.cv-sidefoot{padding:14px 16px 18px;border-top:1px solid #ffffff14}
.cv-help{background:linear-gradient(135deg,#123d63,#0f2f4f);border:1px solid #ffffff14;border-radius:12px;padding:13px;font-size:12.5px;color:#a9c4de}
.cv-help b{color:#fff;display:block;font-size:13.5px;margin-bottom:3px}
.cv-main{flex:1;min-width:0;display:flex;flex-direction:column}
.cv-top{display:flex;align-items:center;gap:14px;background:#fff;border-bottom:1px solid var(--cv-line);padding:12px 26px;position:sticky;top:0;z-index:30}
.cv-search{flex:1;max-width:560px;position:relative}
.cv-search .cv-ic{position:absolute;left:13px;top:50%;transform:translateY(-50%);color:#8aa0b5}
.cv-search input{width:100%;padding:10px 14px 10px 40px;border:1px solid var(--cv-line);border-radius:11px;background:#f5f8fc;font:inherit;font-size:14px}
.cv-search input:focus{outline:2px solid #2563eb33;background:#fff}
.cv-topr{margin-left:auto;display:flex;align-items:center;gap:10px}
.cv-iconbtn{padding:0;margin:0;display:grid;place-items:center;width:40px;height:40px;border-radius:11px;border:1px solid var(--cv-line);background:#fff;color:#38536d;position:relative}
.cv-iconbtn .dotn{position:absolute;top:8px;right:9px;width:8px;height:8px;border-radius:50%;background:#ef4444;border:2px solid #fff}
.cv-avatar{display:grid;place-items:center;width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#2bb8ff,#2563eb);color:#fff;font-weight:700;font-size:14px}
.cv-who{line-height:1.15;font-size:13px}.cv-who b{display:block;font-size:14px}.cv-who small{color:var(--cv-mute)}
.cv-btn{display:inline-flex;align-items:center;gap:8px;background:var(--cv-blue);color:#fff;border:0;border-radius:11px;padding:10px 16px;font-weight:650;font-size:14px;cursor:pointer;text-decoration:none;white-space:nowrap}
.cv-btn:hover{filter:brightness(.93)}.cv-btn.ghost{background:#fff;color:var(--cv-ink);border:1px solid var(--cv-line)}
.cv-btn.light{background:#ffffff22;color:#fff;border:1px solid #ffffff44}
.cv-btn.sm{padding:7px 12px;font-size:13px;border-radius:9px}
.cv-logout{margin:0}.cv-logout button{background:none;border:0;padding:0;color:inherit;cursor:pointer}
.cv-content{padding:24px 28px 40px;max-width:1480px;width:100%;margin:0 auto}
#cv-navtoggle{display:none}.cv-burger{display:none}.cv-scrim{display:none}
.cv-bottom{display:none}
/* --- dashboard ----------------------------------------------------------- */
.cv-hero{position:relative;border-radius:20px;overflow:hidden;color:#fff;padding:34px 36px;min-height:230px;display:flex;flex-direction:column;justify-content:center;
 background:linear-gradient(100deg,rgba(7,24,43,.97) 0%,rgba(9,40,70,.88) 48%,rgba(10,60,100,.25) 100%),url('https://images.unsplash.com/photo-1487958449943-2429e8be8625?w=1600') center/cover}
.cv-hero .tag{display:inline-flex;align-items:center;gap:6px;width:max-content;font-size:11.5px;letter-spacing:1.4px;font-weight:700;background:#ffffff1f;border:1px solid #ffffff33;border-radius:20px;padding:5px 11px;margin-bottom:12px}
.cv-hero h1{font-size:clamp(26px,3vw,40px);line-height:1.13;letter-spacing:-.8px;margin:0 0 10px;max-width:640px}
.cv-hero p{margin:0 0 20px;color:#c9def3;font-size:15.5px}
.cv-hero .acts{display:flex;gap:10px;flex-wrap:wrap}
.cv-sec{display:flex;align-items:end;justify-content:space-between;gap:12px;margin:26px 0 12px}
.cv-sec h2{margin:0;font-size:19px;letter-spacing:-.2px}.cv-sec a{font-size:13.5px;color:var(--cv-blue);font-weight:600}
.cv-steps{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:0;background:#fff;border:1px solid var(--cv-line);border-radius:16px;padding:18px 10px;margin-top:18px;position:relative}
.cv-step{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;position:relative;padding:0 6px;color:var(--cv-ink);text-decoration:none}
.cv-step:not(:last-child)::after{content:"";position:absolute;top:19px;left:calc(50% + 26px);right:calc(-50% + 26px);height:2px;background:repeating-linear-gradient(90deg,#cfdbe8 0 6px,transparent 6px 11px)}
.cv-step.done:not(:last-child)::after{background:var(--c)}
.cv-dot{display:grid;place-items:center;width:40px;height:40px;border-radius:50%;font-weight:800;font-size:15px;border:2px solid var(--c);color:var(--c);background:#fff;flex-shrink:0}
.cv-step.done .cv-dot,.cv-step.now .cv-dot{background:var(--c);color:#fff}
.cv-step.now .cv-dot{box-shadow:0 0 0 5px color-mix(in srgb,var(--c) 22%,transparent)}
.cv-stxt b{display:block;font-size:13.5px}.cv-stxt small{color:var(--cv-mute);font-size:12px}
.cv-row{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(300px,1fr);gap:18px}
.cv-cats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.cv-cat{display:block;background:#fff;border:1px solid var(--cv-line);border-radius:15px;overflow:hidden;text-decoration:none;color:var(--cv-ink);transition:transform .15s,box-shadow .15s}
.cv-cat:hover{transform:translateY(-2px);box-shadow:0 12px 26px #0e345614}
.cv-cat .ph{height:118px;background-size:cover;background-position:center;display:grid;place-items:center;color:#ffffff73}
.cv-cat .tx{padding:11px 13px 13px}.cv-cat b{display:flex;justify-content:space-between;align-items:center;font-size:14.5px}
.cv-cat small{color:var(--cv-mute);font-size:12.5px}
.cv-card{background:#fff;border:1px solid var(--cv-line);border-radius:16px;padding:18px;box-shadow:0 6px 20px #0e34560a}
.cv-card>h3{margin:0 0 4px;font-size:16px;display:flex;align-items:center;gap:9px}
.cv-card .sub{color:var(--cv-mute);font-size:13px;margin:0 0 12px}
.cv-recent{display:flex;flex-direction:column;gap:4px}
.cv-ri{display:flex;align-items:center;gap:12px;padding:10px;border-radius:12px;text-decoration:none;color:var(--cv-ink)}
.cv-ri:hover{background:#f3f7fc}
.cv-ri .bx{display:grid;place-items:center;width:42px;height:42px;border-radius:11px;color:#fff;flex-shrink:0}
.cv-ri .mid{flex:1;min-width:0}.cv-ri b{display:block;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cv-ri small{color:var(--cv-mute);font-size:12px}
.cv-bar{height:6px;border-radius:6px;background:#e8eef5;overflow:hidden;margin-top:5px}.cv-bar i{display:block;height:100%;border-radius:6px}
.cv-chip{display:inline-block;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}
.cv-quick{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-top:18px}
.cv-qa{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--cv-line);border-radius:15px;padding:14px;text-decoration:none;color:var(--cv-ink);transition:transform .15s,box-shadow .15s}
.cv-qa:hover{transform:translateY(-2px);box-shadow:0 12px 24px #0e345614}
.cv-qa .ib{display:grid;place-items:center;width:46px;height:46px;border-radius:13px;flex-shrink:0}
.cv-qa b{display:block;font-size:14.5px}.cv-qa small{color:var(--cv-mute);font-size:12.5px}
.cv-quickform{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-top:4px}
.cv-quickform .qa{display:flex;flex-direction:column;gap:6px;margin:0;font-size:12.5px;color:#b9d2ea;font-weight:600}
.cv-quickform .qi{display:flex;align-items:center;gap:8px;background:#fff;border-radius:12px;height:52px;padding:0 14px}
.cv-quickform .qi input{border:0;width:120px;font-size:22px;font-weight:700;font-family:inherit;color:#0f2740;padding:0;outline:none}
.cv-quickform .qi b{color:#64798d;font-size:14px}
.cv-quickform select{height:52px;border-radius:12px;border:0;padding:0 12px;font-size:15px;font-weight:600;font-family:inherit;width:auto;min-width:140px}
.cv-quickform .qgo{height:52px;background:#ffb020;color:#1b1300;font-size:15px;font-weight:800}
.cv-hows{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:22px;max-width:900px}
.cv-how{display:flex;align-items:center;gap:10px;background:#ffffff14;border:1px solid #ffffff26;border-radius:13px;padding:11px 13px;backdrop-filter:blur(4px)}
.cv-how .n{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:#fff;color:#142b45;font-weight:800;font-size:12.5px;flex-shrink:0}
.cv-how b{display:block;font-size:13.5px}.cv-how small{color:#b9d2ea;font-size:12px}
.cv-ratecard h3{display:flex;align-items:center;gap:8px;margin:0 0 6px;font-size:16px;color:#c2410c}
.cv-mini-steps{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 18px}
.cv-mini-steps span{display:inline-flex;align-items:center;gap:8px;padding:7px 14px 7px 8px;border-radius:30px;background:#e6edf5;color:#5b7189;font-weight:650;font-size:13.5px}
.cv-mini-steps b{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:#fff;font-size:12px}
.cv-mini-steps .on{background:var(--cv-blue);color:#fff}.cv-mini-steps .on b{color:var(--cv-blue)}
.cv-mini-steps .done{background:#dcfce7;color:#15803d}
.cv-drop{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;background:#fff;border:2px dashed #9fbbe0;border-radius:18px;padding:30px 20px;color:var(--cv-blue)}
.cv-drop b{font-size:19px;color:var(--cv-ink)}.cv-drop span{color:var(--cv-mute)}.cv-drop small{color:var(--cv-mute);font-size:12.5px;max-width:520px}
.cv-drop input[type=file]{max-width:420px;margin:6px 0;background:#f5f8fc}
.cv-picks{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.cv-pick{display:flex;flex-direction:column;background:#fff;border:1px solid var(--cv-line);border-radius:15px;overflow:hidden;text-decoration:none;color:var(--cv-ink)}
.cv-pick:hover{box-shadow:0 12px 26px #0e345614}
.cv-pickimg{height:140px;background:#f3f7fb;display:block}.cv-pickimg img{width:100%;height:100%;object-fit:contain;background:#fff}
.cv-pickt{padding:10px 13px 4px}.cv-pickt b{display:block;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cv-pickt small{color:var(--cv-mute)}
.cv-pick .cv-btn{margin:8px 13px 13px;align-self:flex-start}
.cv-sumbox{display:grid;grid-template-columns:200px 1fr;gap:18px;align-items:center;margin-bottom:16px}
.cv-sumbox h3{margin:0 0 6px}.cv-sumbox p{margin:0 0 8px}
.cv-sumimg{height:140px;border-radius:12px;background:#f3f7fb;border:1px solid var(--cv-line);display:grid;place-items:center;color:#8aa0b5;overflow:hidden}
.cv-sumimg img{width:100%;height:100%;object-fit:contain;background:#fff}
.cv-legend2{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
.cv-src{display:inline-block;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}
.cv-src.d{background:#dcfce7;color:#15803d}.cv-src.w{background:#e0f2fe;color:#0369a1}.cv-src.t{background:#fef3c7;color:#b45309}.cv-src.u{background:#ede9fe;color:#6d28d9}
.cv-groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.cv-group h3{display:flex;flex-direction:column;align-items:flex-start;margin:0 0 8px;font-size:16px}.cv-group h3 small{font-weight:500;color:var(--cv-mute);font-size:12.5px}
details.cv-group{margin-top:16px}details.cv-group summary{cursor:pointer;padding:2px 0 8px}
.cv-field{display:grid;grid-template-columns:minmax(0,1.2fr) 150px;gap:4px 12px;align-items:center;padding:10px 8px;border-bottom:1px solid #eef3f8;border-radius:10px}
.cv-field.need{background:#fffbeb}
.cv-field label{margin:0;font-weight:500}.cv-field label b{display:block;font-size:14px}.cv-field label small{color:var(--cv-mute);font-size:12px}
.cv-fin{display:flex;align-items:center;gap:6px}.cv-fin input,.cv-fin select{padding:8px 10px;border-radius:9px;font-size:14px}.cv-fin span{color:var(--cv-mute);font-size:12.5px;min-width:26px}
.cv-fsrc{grid-column:1/-1;display:flex;gap:8px;align-items:center;min-width:0}.cv-fsrc small{color:var(--cv-mute);font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cv-stickybar{position:sticky;bottom:12px;margin-top:18px;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#142b45;color:#d4e4f5;border-radius:14px;padding:12px 14px 12px 18px;box-shadow:0 14px 30px #142b4540;z-index:5}
.cv-stickybar span{font-size:13.5px}
.cv-rate{display:grid;grid-template-columns:minmax(0,1fr) 160px;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid #eef3f8}
.cv-rate label{margin:0;font-weight:500}.cv-rate label b{display:block;font-size:14px}.cv-rate label small{color:var(--cv-mute);font-size:12px}
.cv-rin{display:flex;align-items:center;gap:6px}.cv-rin span{color:var(--cv-mute);font-weight:700}.cv-rin input{padding:8px 10px;border-radius:9px;text-align:right}
.cv-types{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:6px 0 4px}
.cv-types label{margin:0;cursor:pointer}.cv-types input{display:none}
.cv-types span{display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;border:1.5px solid var(--cv-line);border-radius:12px;font-weight:650;font-size:13.5px;background:#fff}
.cv-types input:checked+span{border-color:var(--cv-blue);background:#eef5ff;color:var(--cv-blue);box-shadow:0 0 0 3px #2563eb22}
.cv-persqft{margin:12px 0 0;padding:9px 12px;background:#f5f8fc;border-radius:10px;font-size:13.5px}.cv-persqft b{font-size:16px}.cv-persqft small{color:var(--cv-mute)}
.cv-banner{display:flex;gap:12px;align-items:flex-start;background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;border-radius:14px;padding:14px 16px;margin:4px 0 16px}
.cv-banner b{display:block;font-size:15px}.cv-banner.err{background:#fef2f2;border-color:#fecaca;color:#991b1b}
.cv-people,.cv-activity{list-style:none;margin:0;padding:0}
.cv-person{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #eef3f8;flex-wrap:wrap}
.cv-person .nm{flex:1;min-width:120px}.cv-person .nm b{display:block;font-size:14px}.cv-person .nm small{color:var(--cv-mute)}
.cv-avatar.sm{width:36px;height:36px;font-size:13px;flex-shrink:0}
.cv-inline{display:inline-flex;margin:0}.cv-inline select{padding:6px 8px;border-radius:8px;font-size:13px;width:auto}
.cv-activity li{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #eef3f8;font-size:13.5px}
.cv-activity .dot{width:9px;height:9px;border-radius:50%;background:var(--cv-blue);margin-top:6px;flex-shrink:0}
.cv-activity small{display:block;color:var(--cv-mute);font-size:12px}
.cv-linkbox{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}.cv-linkbox input{flex:1;min-width:200px;font-size:13px;padding:8px 10px;background:#f5f8fc;border-radius:9px}
.cv-team{display:flex;align-items:center;gap:8px}.cv-stack{display:flex}.cv-stack span{margin-left:-8px;border:2px solid #fff}.cv-stack span:first-child{margin-left:0}
.cv-signed{display:flex;gap:9px;align-items:flex-start;background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;border-radius:11px;padding:10px 12px;font-size:12.5px;margin-top:10px}
.cv-signform{margin-top:10px;border-top:1px dashed #d6e0eb;padding-top:10px}.cv-signform textarea{width:100%;min-height:58px;border:1px solid #c5d5e5;border-radius:9px;padding:8px;font:inherit;font-size:13px}.cv-banner.warn{background:#fffbeb;border-color:#fde68a;color:#92400e}
.cv-flow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.cv-fc{display:flex;flex-direction:column;scroll-margin-top:90px}
.cv-fc .hd{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.cv-fc .hd .n{display:grid;place-items:center;width:30px;height:30px;border-radius:9px;color:#fff;font-weight:800;font-size:13px;flex-shrink:0}
.cv-fc .hd h3{margin:0;font-size:15.5px;flex:1}
.cv-fc .ft{margin-top:auto;padding-top:12px;display:flex;gap:8px;flex-wrap:wrap}
.cv-kv{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:13.5px;margin:0}
.cv-kv dt{color:var(--cv-mute)}.cv-kv dd{margin:0;font-weight:600;text-align:right}
.cv-mt{width:100%;border-collapse:collapse;font-size:13.5px;background:none}
.cv-mt td,.cv-mt th{padding:7px 4px;border-bottom:1px solid #eef3f8;text-align:left;background:none}
.cv-mt th{font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--cv-mute);font-weight:700}
.cv-mt td:last-child,.cv-mt th:last-child{text-align:right}
.cv-empty{border:1.5px dashed #c9d7e6;border-radius:12px;padding:16px;text-align:center;color:var(--cv-mute);font-size:13.5px}
.cv-empty b{display:block;color:var(--cv-ink);margin-bottom:3px}
.cv-donut{display:flex;align-items:center;gap:16px}
.cv-donut .ring{width:132px;height:132px;border-radius:50%;flex-shrink:0;display:grid;place-items:center}
.cv-donut .hole{width:86px;height:86px;border-radius:50%;background:#fff;display:grid;place-items:center;text-align:center;line-height:1.1}
.cv-donut .hole b{font-size:15px}.cv-donut .hole small{font-size:10.5px;color:var(--cv-mute)}
.cv-legend{list-style:none;margin:0;padding:0;font-size:13px;flex:1}.cv-legend li{display:flex;align-items:center;gap:7px;padding:3px 0}
.cv-legend i{width:10px;height:10px;border-radius:3px;flex-shrink:0}.cv-legend span{margin-left:auto;font-weight:650}
.cv-review svg,.cv-disclaim svg{flex-shrink:0;margin-top:1px}
.cv-review{display:flex;gap:9px;align-items:flex-start;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;border-radius:11px;padding:10px 12px;font-size:12.5px;font-weight:600}
.cv-ok{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
.cv-files{list-style:none;margin:0;padding:0}.cv-files li{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #eef3f8;font-size:13.5px}
.cv-files li .ty{display:grid;place-items:center;width:34px;height:34px;border-radius:9px;font-size:10.5px;font-weight:800;flex-shrink:0}
.cv-files li .nm{flex:1;min-width:0}.cv-files li .nm small{display:block;color:var(--cv-mute);font-size:11.5px}
.cv-files li a.dl{color:var(--cv-blue)}.cv-files li .na{color:#a3b3c3;font-size:12px}
.cv-view{position:relative;border-radius:12px;overflow:hidden;background:#f3f7fb;border:1px solid var(--cv-line);height:190px;display:grid;place-items:center}
.cv-view img{width:100%;height:100%;object-fit:contain;background:#fff}
.cv-tabs{display:inline-flex;background:#eef3f9;border-radius:9px;padding:3px;margin-left:auto}
.cv-tabs label{display:inline-block;padding:4px 11px;border-radius:7px;font-size:12px;font-weight:700;color:#59708a;cursor:pointer;margin:0}
.cv-tabs input,#cv-t2,#cv-t3{display:none}
.cv-v3d{display:none}
#cv-t3:checked~.cv-viewwrap .cv-v2d{display:none}#cv-t3:checked~.cv-viewwrap .cv-v3d{display:grid}
#cv-t2:checked~.cv-hdr label[for=cv-t2],#cv-t3:checked~.cv-hdr label[for=cv-t3]{background:#fff;color:var(--cv-ink);box-shadow:0 1px 3px #0002}
.cv-ph{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:6px}
.cv-ph h1{margin:0;font-size:26px;letter-spacing:-.5px}.cv-ph .meta{color:var(--cv-mute);font-size:14px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.cv-ph .meta span{display:inline-flex;align-items:center;gap:5px}
.cv-disclaim{margin-top:22px;font-size:12.5px;color:var(--cv-mute);display:flex;gap:8px;align-items:flex-start}
/* --- v2.7 theme unification: older pages get the same look ---------------- */
.cv-content h1{font-size:26px;letter-spacing:-.5px}.cv-content h2{font-size:19px;letter-spacing:-.2px}
.cv-content a:not([class]){color:var(--cv-blue);font-weight:600}.cv-content a:not([class]):hover{text-decoration:underline}
.cv-content .card{padding:20px;border-radius:16px}
.cv-content table:not(.cv-mt){border-collapse:separate;border-spacing:0;border:1px solid var(--cv-line);border-radius:12px;overflow:hidden;font-size:14px}
.cv-content table:not(.cv-mt) th{background:#f3f7fc;color:#4a637c;font-size:12px;text-transform:uppercase;letter-spacing:.5px;font-weight:700;padding:10px 12px}
.cv-content table:not(.cv-mt) td{padding:9px 12px;border-bottom:1px solid #edf2f7}
.cv-content table:not(.cv-mt) tr:nth-child(even) td{background:#fafcfe}
.cv-content table:not(.cv-mt) tr:last-child td{border-bottom:0}
.cv-content table input[type=number]{padding:7px 9px;border-radius:8px;text-align:right}
.cv-content input:focus,.cv-content select:focus,.cv-content textarea:focus{outline:2px solid #2563eb40;border-color:#2563eb}
.cv-content .actions{align-items:center}
:focus-visible{outline:3px solid #2563eb80;outline-offset:2px}
/* print: BOQ and reports print cleanly without the menus */
@media print{.cv-side,.cv-top,.cv-bottom,.cv-stickybar,.cv-burger,form button,.actions{display:none!important}
 .cv-shell{display:block}.cv-content{padding:0;max-width:none}body{background:#fff}.cv-card,.card{box-shadow:none;break-inside:avoid}}
/* --- v3.0 design system: context bar, modes, dashboard, portfolio, wizard, studio --- */
.cv-side{background:var(--cv-navy)}
.cv-nsec{font-size:10.5px;letter-spacing:1.4px;color:#8aa3bf;margin:18px 12px 6px}
.cv-ctx{background:#fff;border-bottom:1px solid var(--cv-line);padding:10px 26px 0;position:sticky;top:65px;z-index:25}
.cv-cb-main{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.cv-cb-name{font-weight:700;font-size:16px;color:var(--cv-ink);text-decoration:none}
.cv-cb-meta{font-size:13px;color:var(--cv-mute)}
.cv-cb-chip{font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}
.cv-cb-tabs{display:flex;gap:4px;margin-top:8px;overflow-x:auto}
.cv-cb-tab{padding:8px 12px;font-size:13.5px;font-weight:600;color:var(--cv-mute);text-decoration:none;border-bottom:2px solid transparent;white-space:nowrap}
.cv-cb-tabs .cv-cb-tab{margin:0;border-radius:0;background:none;display:block;color:var(--cv-mute)}
.cv-cb-tabs .cv-cb-tab:hover{color:var(--cv-ink);background:none}.cv-cb-tabs .cv-cb-tab.on{color:var(--cv-blue);border-bottom-color:var(--cv-blue)}
.cv-mode-expert .cv-guide{display:none}.cv-mode-guided .cv-expert{display:none}
.cv-guide{display:flex;gap:10px;align-items:flex-start;background:#f0fdfa;border:1px solid #99f6e4;color:#134e4a;border-radius:12px;padding:12px 14px;font-size:13.5px;margin-bottom:14px}
.cv-guide b{display:block}.cv-guide .ta{display:block;color:#0f766e;font-size:13px;margin-top:2px}
.cv-status{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}
.cv-status::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.st-draft{background:#f1f5f9;color:#475569}.st-progress{background:#dbeafe;color:#1d4ed8}.st-input{background:#fef3c7;color:#92400e}
.st-review{background:#ede9fe;color:#6d28d9}.st-checked{background:#ccfbf1;color:#115e59}.st-approved{background:#dcfce7;color:#166534}.st-failed{background:#fee2e2;color:#991b1b}
/* dashboard */
.db-top{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.db-top h1{margin:0;font-size:26px}.db-top .sub{color:var(--cv-mute);font-size:13.5px}
.db-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:16px}
.db-ask{background:var(--cv-navy);color:#fff;border-radius:16px;padding:24px 26px}
.db-ask .k{font-size:11.5px;letter-spacing:1.4px;font-weight:700;color:#93c5fd}
.db-ask h2{margin:6px 0 2px;font-size:30px;letter-spacing:-.6px;color:#fff}.db-ask .ta{color:#a5c3e3;font-size:15px;margin-bottom:14px}
.db-ask form{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}
.db-ask label{margin:0;color:#c7d7ea;font-size:12.5px;font-weight:600;display:flex;flex-direction:column;gap:6px}
.db-area{display:flex;align-items:center;gap:8px;background:#fff;border-radius:12px;height:56px;padding:0 14px}
.db-area input{border:0;width:140px;font-size:26px;font-weight:800;color:var(--cv-ink);padding:0;outline:none;font-family:inherit}
.db-area b{color:var(--cv-mute)}
.db-seg{display:flex;gap:6px}.db-seg input{position:absolute;opacity:0;width:1px;height:1px}
.db-seg span{display:grid;place-items:center;height:56px;min-width:58px;padding:0 12px;border-radius:12px;border:1.5px solid #3b587a;font-weight:700;cursor:pointer;color:#fff}
.db-seg input:checked+span{background:var(--cv-blue);border-color:var(--cv-blue)}.db-seg input:focus-visible+span{outline:3px solid #93c5fd}
.db-go{height:56px;border:0;border-radius:12px;background:var(--cv-amber);color:#1f1300;font-weight:800;font-size:15.5px;padding:0 20px;cursor:pointer}
.db-ask .alt{margin-top:12px;font-size:13px;color:#a5c3e3}.db-ask .alt a{color:#fff;font-weight:700}
.db-stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.db-stat{background:#fff;border:1px solid var(--cv-line);border-radius:14px;padding:14px 16px;text-decoration:none;color:var(--cv-ink)}
.db-stat small{display:block;color:var(--cv-mute);font-size:12.5px;font-weight:600}.db-stat b{font-size:26px;letter-spacing:-.5px}
.db-stat em{display:block;font-style:normal;font-size:12px;color:var(--cv-mute)}
.db-row{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:16px;margin-top:16px}
.db-cont{display:flex;flex-direction:column;gap:12px}
.db-cont h3{margin:0;font-size:18px}.db-cont .next{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.db-mini{display:flex;gap:4px}.db-mini i{flex:1;height:6px;border-radius:4px;background:#e2e8f0}.db-mini i.on{background:var(--cv-teal)}
/* portfolio */
.pf-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0}
.pf-bar input,.pf-bar select{width:auto;padding:9px 12px;border-radius:10px;font-size:14px}
.pf-bar .seg{display:inline-flex;border:1px solid var(--cv-line);border-radius:10px;overflow:hidden;margin-left:auto}
.pf-bar .seg a{padding:8px 14px;font-size:13.5px;font-weight:600;color:var(--cv-mute);text-decoration:none;background:#fff}.pf-bar .seg a.on{background:var(--cv-blue);color:#fff}
.pf-table td,.pf-table th{white-space:nowrap}.pf-table td:first-child{white-space:normal;min-width:180px}
.pf-prog{width:120px;height:6px;border-radius:4px;background:#e2e8f0;display:inline-block;vertical-align:middle;overflow:hidden}.pf-prog i{display:block;height:100%;background:var(--cv-teal)}
.pf-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.pf-card{background:#fff;border:1px solid var(--cv-line);border-radius:14px;padding:16px;text-decoration:none;color:var(--cv-ink);display:flex;flex-direction:column;gap:6px}
.pf-card:hover{box-shadow:0 10px 24px #0f172a14}
/* wizard */
.wz{display:grid;grid-template-columns:220px minmax(0,1fr);gap:22px;max-width:1040px}
.wz-steps{list-style:none;margin:0;padding:0;position:sticky;top:150px;align-self:start}
.wz-steps li{display:flex;gap:10px;align-items:center;padding:9px 0;font-weight:600;color:var(--cv-mute);font-size:14px}
.wz-steps b{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#e2e8f0;color:var(--cv-ink);font-size:13px}
.wz-sec{background:#fff;border:1px solid var(--cv-line);border-radius:16px;padding:20px 22px;margin-bottom:14px;scroll-margin-top:150px}
.wz-sec h2{display:flex;align-items:center;gap:10px;margin:0 0 4px;font-size:18px}.wz-sec h2 b{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--cv-blue);color:#fff;font-size:13px}
.wz-sec .ta{color:var(--cv-mute);font-size:13px;margin:0 0 10px}
.wz-choice{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.wz-choice label{margin:0;cursor:pointer}.wz-choice input{position:absolute;opacity:0;width:1px;height:1px}
.wz-choice span{display:flex;flex-direction:column;gap:4px;height:100%;padding:14px;border:1.5px solid var(--cv-line);border-radius:12px;font-weight:500;font-size:13px;color:var(--cv-mute)}
.wz-choice span b{color:var(--cv-ink);font-size:14.5px}
.wz-choice input:checked+span{border-color:var(--cv-blue);background:#eff6ff;box-shadow:0 0 0 3px #2563eb22}
.wz-choice input:focus-visible+span{outline:3px solid #2563eb80}
/* drawing studio */
.ds{display:grid;grid-template-columns:240px minmax(0,1fr) 330px;gap:14px;align-items:start}
.ds-panel{background:#fff;border:1px solid var(--cv-line);border-radius:14px;padding:14px;color:var(--cv-ink);width:auto;box-shadow:none}
.ds-right .cv-btn{white-space:normal;text-align:center}
.ds-panel h3{margin:0 0 10px;font-size:14px;text-transform:uppercase;letter-spacing:.8px;color:var(--cv-mute)}
.ds-files{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.ds-files a{display:flex;gap:8px;align-items:center;padding:8px;border-radius:10px;text-decoration:none;color:var(--cv-ink);font-size:13.5px;border:1px solid transparent}
.ds-files a:hover{background:#f5f8fc}.ds-files a.on{border-color:var(--cv-blue);background:#eff6ff}
.ds-files .th{width:44px;height:34px;border-radius:6px;background:#f3f6fa;flex-shrink:0;overflow:hidden;display:grid;place-items:center;font-size:10px;font-weight:800;color:var(--cv-mute)}
.ds-files .th img{width:100%;height:100%;object-fit:cover}
.ds-viewer{background:#fff;border:1px solid var(--cv-line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
.ds-tool{display:flex;gap:8px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--cv-line);flex-wrap:wrap;font-size:13px}
.ds-tool button{background:#fff;color:var(--cv-ink);border:1px solid var(--cv-line);border-radius:8px;padding:6px 10px;font-weight:700;min-width:36px}
.ds-tool button:hover{background:#f3f6fa}
.ds-canvas{height:560px;overflow:auto;background:repeating-linear-gradient(0deg,#f3f6fa 0 1px,transparent 1px 24px),repeating-linear-gradient(90deg,#f3f6fa 0 1px,transparent 1px 24px),#fff;display:flex;align-items:flex-start;justify-content:center}
.ds-canvas img{transform-origin:top center;max-width:100%;transition:width .15s}
.ds-kv{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 10px;font-size:13px;margin:0}
.ds-kv dt{color:var(--cv-mute)}.ds-kv dd{margin:0;font-weight:700;text-align:right}
.ds-found{display:flex;align-items:center;gap:10px;background:#f0fdfa;border-radius:12px;padding:10px 12px;margin-bottom:10px}
.ds-found b{font-size:24px;color:var(--cv-teal)}
.ds-sched{margin-top:14px}
@media(max-width:1250px){.ds{grid-template-columns:200px minmax(0,1fr)}.ds-right{grid-column:1/-1}.db-grid,.db-row{grid-template-columns:1fr}}
@media(max-width:900px){.cv-ctx{top:61px;padding:8px 14px 0}.ds{grid-template-columns:1fr}.ds-canvas{height:420px}.wz{grid-template-columns:1fr}.wz-steps{display:none}.wz-choice{grid-template-columns:1fr}}
@media(max-width:640px){.db-ask h2{font-size:24px}.db-area input{width:100px;font-size:22px}.db-seg span{min-width:50px}.db-go{width:100%}.db-stats{grid-template-columns:1fr 1fr}}
/* --- v3.1 cost center, structural studio, bbs studio ------------------------ */
.cc-tabs{display:flex;gap:6px;margin:12px 0 4px;flex-wrap:wrap}
.cc-tabs a{padding:8px 14px;border-radius:30px;background:#e8eef6;color:#334155;font-weight:650;font-size:13.5px;text-decoration:none}
.cc-tabs a.on{background:var(--cv-navy);color:#fff}
.cc-kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-top:14px}
.cc-kpi{background:#fff;border:1px solid var(--cv-line);border-radius:14px;padding:12px 14px;min-width:0}
.cc-kpi small{display:block;color:var(--cv-mute);font-size:12.5px;font-weight:600}.cc-kpi b{display:block;font-size:21px;letter-spacing:-.3px;margin:2px 0}
.cc-kpi em{font-style:normal;font-size:11.5px;color:var(--cv-mute)}
.cc-alerts{display:flex;flex-direction:column;gap:8px;margin-top:14px}.cc-alerts .cv-banner{margin:0}.cc-alerts .cv-banner a{font-weight:700;display:inline-block;margin-top:4px}
.cc-bars{display:flex;flex-direction:column;gap:10px}
.cc-bar{display:grid;grid-template-columns:130px minmax(0,1fr) 90px;gap:10px;align-items:center;font-size:13.5px}
.cc-bar .tr{height:18px;background:#eef2f7;border-radius:6px;overflow:hidden}.cc-bar .tr i{display:block;height:100%;border-radius:6px}
.cc-bar b{text-align:right;font-variant-numeric:tabular-nums}
.cc-stage{border-top:1px solid var(--cv-line);padding:10px 0}
.cc-sh{display:flex;align-items:center;gap:10px;margin-bottom:6px}.cc-sh i{width:12px;height:12px;border-radius:4px}.cc-sh .tot{margin-left:auto}
.cc-item{border:1px solid var(--cv-line);border-radius:12px;margin:6px 0;background:#fff}
.cc-item summary{display:flex;align-items:center;gap:10px;padding:10px 12px;cursor:pointer;list-style:none}
.cc-item summary::-webkit-details-marker{display:none}.cc-item summary::before{content:'\25B8';color:var(--cv-mute)}.cc-item[open] summary::before{content:'\25BE'}
.cc-item summary .nm{flex:1;min-width:0;font-weight:600;font-size:14px}.cc-item summary b{font-variant-numeric:tabular-nums}
.cc-lines{margin:0 12px 10px;width:calc(100% - 24px)}.cc-basis{display:block;color:var(--cv-mute);font-size:11.5px;font-weight:400}
.cc-rate input{width:110px;padding:6px 8px;border-radius:8px;text-align:right}.cc-np{color:#b45309;font-size:12px;font-weight:600}
.cc-charges{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) auto;gap:10px;align-items:end}.cc-charges label{margin:0;font-size:13px}
tr.cc-cur td{background:#eff6ff!important}
.cv-banner.warn{background:#fffbeb;border-color:#fde68a;color:#92400e}
.ss-nav h3{margin-bottom:6px}.ss-group{margin-top:10px}.ss-group h4{margin:0 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.7px;color:var(--cv-mute)}
.ss-nav a{display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:8px;padding:7px 9px;border-radius:9px;text-decoration:none;color:var(--cv-ink);font-size:13px;border:1px solid transparent}
.ss-nav a b{grid-row:1/3}.ss-nav a span{color:var(--cv-mute);font-size:12px}.ss-nav a em{font-style:normal;font-size:12px;font-weight:600;color:var(--cv-teal)}
.ss-nav a:hover{background:#f5f8fc}.ss-nav a.on{border-color:var(--cv-blue);background:#eff6ff}
.ss-nav a.ss-all{display:block;font-weight:700}
.ss-trace{margin:6px 0 0;padding-left:20px;line-height:1.9;font-size:14px}.ss-trace b{color:var(--cv-teal)}
.ss-counts li{justify-content:space-between}
.ss-two{display:grid;grid-template-columns:1fr 1fr;gap:8px}.ss-add label,.ss-side label{margin:8px 0 3px;font-size:13px}.ss-add input,.ss-add select,.ss-side input,.ss-side select{padding:8px 10px;font-size:14px}
.ss-side{margin-top:16px;display:flex;flex-direction:column;gap:14px}
.ds.ss-g3{grid-template-columns:250px minmax(0,1fr) 300px}.ds.ss-g2{grid-template-columns:250px minmax(0,1fr)}.ds.bb-g{grid-template-columns:minmax(0,1fr) 330px}
@media(max-width:1250px){.ds.ss-g3{grid-template-columns:220px minmax(0,1fr)}.ds.ss-g3>.ss-add{grid-column:1/-1}.ds.bb-g{grid-template-columns:1fr}.cc-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.cc-charges{grid-template-columns:1fr 1fr}}
@media(max-width:900px){.ds.ss-g3,.ds.ss-g2{grid-template-columns:1fr}}
@media(max-width:640px){.cc-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.cc-bar{grid-template-columns:90px minmax(0,1fr) 70px}.cc-rate input{width:84px}}
/* --- v3.2 reinforcement detail drawings ------------------------------------ */
.rd-wrap{border:1px solid var(--cv-line);border-radius:12px;padding:12px;background:#fff;margin-top:8px}
.rd-svg{display:block;max-width:100%;height:auto}
.rd-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--cv-mute);margin:6px 0}.rd-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-2px}
.rd-notes{margin:8px 0 0;padding-left:18px;font-size:13.5px;line-height:1.6}.rd-warn{background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:10px;padding:8px 10px;font-size:13px}
.rd-foot{font-size:12px;color:var(--cv-mute);margin:8px 0 0}
.rd-grid{display:flex;flex-direction:column;gap:16px;margin-top:14px}
.cc-rateuse{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px;background:#f0fdfa;border:1px solid #99f6e4;border-radius:10px;padding:8px 12px;font-size:13px;color:#134e4a}
@media print{.rd-sheet{break-inside:avoid;page-break-inside:avoid}.cc-tabs,.cv-ph button{display:none!important}}
/* --- v3.3 Reports Center ------------------------------------------------- */
.cc-kpis.rc-k4{grid-template-columns:repeat(4,minmax(0,1fr))}
.rc-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px}
.rc-doc{display:flex;flex-direction:column;gap:6px;min-width:0}.rc-doc.off{background:#fafbfd}.rc-doc.off .rc-pv{opacity:.7}
.rc-dh{display:flex;gap:10px;align-items:flex-start;color:var(--cv-blue)}.rc-dh>div{flex:1;min-width:0;color:var(--cv-ink)}
.rc-dh h3{margin:0;font-size:16px}.rc-dh .ta,.rc-sec .ta{color:#0f766e;font-size:12.5px;font-weight:500}
.rc-chips{display:flex;gap:5px;flex-wrap:wrap;align-items:center}.rc-ty{font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px;letter-spacing:.3px}
.rc-tag{font-size:11.5px;font-weight:650;padding:2px 8px;border-radius:6px;background:#e0ecff;color:#1d4ed8}.cv-mt td.r,.cv-mt th.r{text-align:right}
.dt-sec{margin-top:14px}.dt-sh{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}.dt-sh h3{margin:0 0 6px}.dt-sh .ta{color:#0f766e;font-size:12.5px;font-weight:500}
.dt-del{display:inline;margin:0}
.dt-row{display:flex;align-items:center;gap:2px}.dt-row>a{flex:1;min-width:0}.dt-x-f{display:inline;margin:0}
.dt-x{border:0;background:none;box-shadow:none;color:#94a3b8;cursor:pointer;font-size:13px;line-height:1;padding:6px 7px;border-radius:8px;margin:0}
.dt-x:hover{color:#b91c1c;background:#fee2e2}.pf-del{color:#b91c1c;font-size:13px;font-weight:600}.cv-btn.dt-danger{background:#b91c1c;border-color:#b91c1c;color:#fff}.cv-btn.dt-danger:hover{background:#991b1b}
.dt-danger-t{color:#b91c1c!important}.cv-inline{display:inline}
.dt-up{margin-top:14px}.dt-upf{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}.dt-upf input[type=file]{flex:1;min-width:200px;margin:0}
.dt-zone{margin-top:18px;border:1.5px solid #fecaca;background:#fff7f7}.dt-zone h3{color:#991b1b}.dt-lab{display:flex;flex-direction:column;gap:4px;font-size:13px;flex:1;min-width:220px;margin:0}.dt-lab input{margin:0}
.cv-rin{position:relative}.cv-rclr{border:0;background:none;color:#94a3b8;cursor:pointer;font-size:13px;padding:4px 6px;margin-left:4px;box-shadow:none}.cv-rclr:hover{color:#b91c1c;background:none}.cv-lang-ta .db-ask .ta,.cv-lang-ta .rc-dh .ta,.cv-lang-ta .rc-sec .ta{display:none}.rc-pv{flex:1}.rc-pv .cv-mt td,.rc-paper .cv-mt td,.rc-table td{vertical-align:top}.r{text-align:right;font-variant-numeric:tabular-nums}
.rc-s{display:block;color:var(--cv-mute);font-size:11.5px;font-weight:400}
.rc-acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:4px}
.rc-filter{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}.rc-filter input{flex:1;min-width:180px;margin:0}.rc-filter select{width:auto;margin:0}
.rc-paper{max-width:980px;padding:28px 32px}.rc-ph{display:flex;justify-content:space-between;gap:16px;border-bottom:3px solid var(--cv-navy);padding-bottom:12px;margin-bottom:12px}
.rc-ph h1{margin:2px 0;font-size:26px}.rc-brand{color:var(--cv-blue);font-size:13px;letter-spacing:.5px}.rc-meta{text-align:right;color:var(--cv-mute);font-size:12.5px}
.rc-steps{display:flex;gap:6px;flex-wrap:wrap;list-style:none;padding:0;margin:0 0 6px}.rc-steps li{font-size:12px;padding:3px 9px;border-radius:20px;background:#f1f5f9;color:#64748b}
.rc-steps li.ok{background:#dcfce7;color:#166534}.rc-steps li.ok::before{content:'\2713  '}
.rc-two{display:grid;grid-template-columns:1fr 1fr;gap:20px}.rc-sec h2{font-size:16px;margin:16px 0 6px;border-bottom:1px solid var(--cv-line);padding-bottom:4px}
.rc-tot td{font-weight:800;border-top:2px solid var(--cv-ink)}.rc-warn{color:#b45309;font-size:12.5px;font-weight:600}
.rc-dis{margin-top:18px;font-size:12px;color:#7f1d1d;background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:10px 12px}
@media(max-width:900px){.rc-grid,.rc-two{grid-template-columns:1fr}.cc-kpis.rc-k4{grid-template-columns:repeat(2,minmax(0,1fr))}.rc-paper{padding:16px}.rc-ph{flex-direction:column}.rc-meta{text-align:left}}
@media print{.rc-noprint,.cv-ctx{display:none!important}.rc-paper{border:0;padding:0;max-width:none}.rc-sec,.rc-two{break-inside:avoid}}
/* --- auth pages ---------------------------------------------------------- */
.cv-auth .cv-content{max-width:1180px}
/* --- responsive ---------------------------------------------------------- */
@media(max-width:1250px){.cv-quick{grid-template-columns:repeat(2,minmax(0,1fr))}.cv-groups{grid-template-columns:1fr}.cv-row{grid-template-columns:minmax(0,1fr)}}
@media(max-width:1100px){.cv-flow{grid-template-columns:repeat(2,minmax(0,1fr))}.cv-cats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){
 .cv-side{position:fixed;left:0;top:0;bottom:0;transform:translateX(-105%);transition:transform .22s;box-shadow:10px 0 30px #0005}
 #cv-navtoggle:checked~.cv-shell .cv-side{transform:none}
 #cv-navtoggle:checked~.cv-shell .cv-scrim{display:block;position:fixed;inset:0;background:#142b4566;z-index:35}
 .cv-burger{display:grid}
 .cv-top{padding:10px 14px;gap:10px}.cv-who,.cv-top .cv-newbtn,.cv-top .cv-bell{display:none}
 html,body{overflow-x:clip}
 .cv-content{padding:16px 14px 92px}
 .cv-steps{grid-template-columns:repeat(3,minmax(0,1fr));row-gap:16px}
 .cv-step:nth-child(3)::after{display:none}
 .cv-bottom{display:flex;position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--cv-line);z-index:30;padding:6px 4px calc(6px + env(safe-area-inset-bottom));justify-content:space-around}
 .cv-bottom a{display:flex;flex-direction:column;align-items:center;gap:2px;font-size:11px;font-weight:600;color:#6b8096;text-decoration:none;padding:4px 8px;border-radius:10px}
 .cv-bottom a.on{color:var(--cv-blue)}
 .cv-bottom a.fab{background:var(--cv-blue);color:#fff;width:50px;height:50px;border-radius:16px;justify-content:center;margin-top:-22px;box-shadow:0 8px 18px #2563eb55;padding:0}
}
@media(max-width:640px){
 .cv-hero{padding:22px 20px;min-height:200px;border-radius:16px}.cv-hero p{font-size:14px}
 .cv-flow{grid-template-columns:1fr}
 .cv-quick{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.cv-qa{padding:11px;flex-direction:column;align-items:flex-start;gap:8px}.cv-qa small{display:none}.cv-qa .ib{width:40px;height:40px}
 .cv-hows{grid-template-columns:1fr;gap:6px}.cv-sumbox{grid-template-columns:1fr}.cv-field{grid-template-columns:1fr}.cv-rate{grid-template-columns:1fr 130px}.cv-stickybar{flex-direction:column;align-items:stretch;text-align:center}
 .cv-cats{gap:10px}.cv-cat .ph{height:84px}
 .cv-stxt small{display:none}.cv-stxt b{font-size:12px}
 .cv-dot{width:34px;height:34px;font-size:13px}.cv-step:not(:last-child)::after{top:16px}
 .cv-search input{font-size:13px}
 .cv-ph h1{font-size:21px}
}
"""

LEGACY_CSS = r""":root{--blue:#2563eb;--ink:#0d2440;--pale:#eef5fc}*{box-sizing:border-box}body{margin:0;background:#eff5fb;color:#152b42;font:15px/1.5 system-ui,Segoe UI,Arial}a{color:inherit;text-decoration:none}.shell{display:flex;min-height:100vh}aside{width:235px;flex-shrink:0;background:linear-gradient(165deg,#071c31,#12344e);color:white;padding:24px 14px}.brand{font-size:23px;font-weight:800;margin:0 8px 28px}.brand b{color:#59aaff}nav a{display:block;padding:12px 14px;border-radius:9px;margin:5px 0;color:#dbeafa}nav a:hover{background:#234863}main{flex:1;min-width:0}header{display:flex;justify-content:space-between;align-items:center;gap:12px;background:white;padding:16px 28px;border-bottom:1px solid #dce6ef}header .right{display:flex;align-items:center;gap:10px}.content{padding:25px;max-width:1350px;margin:auto}h1{margin:0 0 8px;font-size:29px}h2{margin:0 0 14px}p.muted,.muted{color:#64788b}.hero{border-radius:18px;padding:35px;background:linear-gradient(100deg,rgba(8,35,59,.95),rgba(9,66,110,.78)),url('https://images.unsplash.com/photo-1487958449943-2429e8be8625?w=1600') center/cover;color:white;margin-bottom:22px}.hero h1{font-size:34px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px}.card{background:white;padding:22px;border-radius:14px;box-shadow:0 3px 14px #19324b0d;border:1px solid #dce8f1}.card h3{margin:6px 0}.card p{color:#687e91}.primary,button{display:inline-block;background:var(--blue);border:0;color:white;padding:11px 17px;border-radius:9px;cursor:pointer;font:inherit}.small{padding:8px 11px;border-radius:8px}button:hover,.primary:hover{filter:brightness(.92)}.form{max-width:570px}label{display:block;margin:15px 0 5px;font-weight:650}input,select{width:100%;padding:12px;border:1px solid #c5d5e5;border-radius:8px;font:inherit}input[type=file]{background:white}.hint{font-size:13px;color:#667e92}.guest{background:#eaf5ff;padding:15px;border-radius:10px;margin-top:15px}.checkline{display:flex;align-items:center;gap:9px;margin-top:15px}.checkline input{width:auto}.msg{padding:12px;background:#fff1e8;border-radius:8px;color:#8d3800}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}.pill{font-size:12px;color:#1455a8;background:#e9f3ff;padding:5px 10px;border-radius:20px}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border-bottom:1px solid #e0e9f1;text-align:left}th{background:#e8f2fb}.scroll{overflow-x:auto}@media(max-width:760px){.shell{display:block}aside{width:100%;padding:13px}.brand{margin:0 0 8px}nav{display:flex;overflow-x:auto;gap:4px}nav a{white-space:nowrap;padding:7px}header{padding:12px}.content{padding:14px}.hero{padding:23px}.hero h1{font-size:25px}}

/* Civora 0.3 — Option B application system */
:root{--blue:#0865f5;--ink:#0b2137;--pale:#f0f5fb}body{background:#edf3f9;color:#102b45}aside{background:linear-gradient(175deg,#071a2b,#0d304b);width:244px;padding:23px 15px;box-shadow:4px 0 22px #081f3210}.brand{letter-spacing:-.8px;font-size:23px;white-space:nowrap}.brandmark{display:inline-grid;place-items:center;background:linear-gradient(135deg,#27b4f5,#0865f5);border-radius:10px;width:34px;height:34px;font-size:18px;color:white;margin-right:4px}nav a{font-weight:550;transition:background .2s}nav a:first-child{background:#214761;color:white}header{min-height:74px;padding:14px 30px}.toplabel{font-size:13px;color:#526c85;letter-spacing:.4px}.content{max-width:1500px;padding:28px 30px}.card{border:1px solid #dce7f3;border-radius:16px;box-shadow:0 10px 28px #0e34560b;transition:transform .18s,box-shadow .18s}.card:hover{box-shadow:0 12px 30px #0e34561b}.primary,button{background:#0865f5;border-radius:10px;font-weight:650}.hero{position:relative;min-height:300px;display:flex;flex-direction:column;justify-content:center;overflow:hidden;background:linear-gradient(100deg,rgba(6,24,42,.96) 0%,rgba(7,38,67,.83) 52%,rgba(8,59,91,.26) 100%),url('https://images.unsplash.com/photo-1487958449943-2429e8be8625?w=1600') center/cover}.hero h1{font-size:clamp(28px,3vw,46px);letter-spacing:-1.2px;line-height:1.14}.hero .pill{width:max-content;background:#cfeaff}.eyebrow{font-size:12px;letter-spacing:1.7px;text-transform:uppercase;color:#4789df;font-weight:800}.featuregrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:18px 0 26px}.feature{display:block;background:white;border:1px solid #dbe6f1;padding:17px;border-radius:15px;min-height:117px}.feature b{display:block;margin-top:9px}.feature small{color:#607b92}.featureicon{display:grid;place-items:center;width:39px;height:39px;border-radius:11px;background:#e9f2ff;color:#0865f5;font-size:21px}.categorygrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px}.category{min-height:170px;background:white;border-radius:15px;overflow:hidden;border:1px solid #dce6ef;display:block}.category .photo{height:102px;background-size:cover;background-position:center}.category .desc{padding:10px 14px}.category .desc b{display:block}.category .desc small{color:#6a8297}.steps{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 22px}.steps span{padding:8px 13px;border-radius:999px;background:#e0eafb;color:#345775;font-size:12px;font-weight:700}.steps span:first-child{background:#0865f5;color:white}.loginwrap{min-height:72vh;display:grid;grid-template-columns:minmax(0,1fr) minmax(350px,470px);gap:0;border-radius:23px;overflow:hidden;box-shadow:0 15px 50px #0d315b18;background:white}.loginart{background:linear-gradient(180deg,#0b253e70,#07192ef2),url('https://images.unsplash.com/photo-1487958449943-2429e8be8625?w=1200') center/cover;color:white;padding:45px;display:flex;flex-direction:column;justify-content:end}.loginart h2{font-size:35px;line-height:1.12}.loginpanel{padding:35px}.loginpanel .card{box-shadow:none;border:0;padding:0}.muted{color:#6b8094}.notice{padding:14px 17px;background:#eaf4ff;border-radius:12px;color:#23537c}.stagecard{padding:17px;border:1px solid #dbe6f1;background:white;border-radius:15px}.stagecard h3{margin:0 0 5px}.stagecard p{font-size:13px;color:#637d93;margin:0}.preview-lock{background:#edf3fa;border:1px dashed #a8bdd3;border-radius:14px;padding:18px}.preview-lock a{color:#0865f5;font-weight:700}.reporttable{width:100%;border-radius:12px;overflow:hidden}.reporttable td:last-child{text-align:right;font-weight:650}
@media(max-width:1100px){.featuregrid,.categorygrid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){aside{width:100%;padding:12px}.brand{font-size:20px}.content{padding:15px}.hero{min-height:250px;padding:24px}.featuregrid,.categorygrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.feature{min-height:125px;padding:13px}.category .photo{height:78px}.loginwrap{grid-template-columns:1fr}.loginart{min-height:180px;padding:22px}.loginart h2{font-size:25px}.loginpanel{padding:18px}header{min-height:55px}.toplabel{display:none}}@media(max-width:400px){.categorygrid{grid-template-columns:1fr}}"""

AUTH_ART = ('<div class="loginwrap"><div class="loginart"><span class="eyebrow" style="color:#91d3ff">WELCOME TO CIVORA AI</span>'
            '<h2>From an idea to a built reality.</h2><p>Plan · Estimate · Design · Build · Manage — one connected workspace.</p></div>'
            '<div class="loginpanel">{body}</div></div>')


def page(title, body, user=None, pid=None, path='/', csrf_token='', auth_page=False, query='', context=None, prefs=None):
    """Full HTML document. `user` is a mapping with name/username (or None). v3.0: `context` = project context bar data,
    `prefs` = {'mode': 'guided'|'expert', 'lang': 'en'|'ta'}."""
    prefs = prefs or {}
    lang = prefs.get('lang', 'en')
    mode = prefs.get('mode', 'guided')
    nav = nav_html(user, pid, path, lang)
    if auth_page:
        body = AUTH_ART.replace('{body}', body)
    if user:
        name = user['name'] if 'name' in user.keys() else ''
        uname = user['username'] if 'username' in user.keys() else ''
        right = (f'<a class="cv-btn cv-newbtn" href="/projects/new">{icon("plus", 18)}New Project</a>'
                 f'<span class="cv-iconbtn cv-bell" title="Notifications">{icon("bell", 19)}</span>'
                 f'<span class="cv-avatar" title="{esc(name)}">{esc(_initials(name))}</span>'
                 f'<span class="cv-who"><b>{esc(name)}</b><small>@{esc(uname)} · {_acct(user)}</small></span>'
                 f'<form class="cv-logout" method="post" action="/logout"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">'
                 f'<button class="cv-iconbtn" title="Log out" aria-label="Log out">{icon("logout", 19)}</button></form>')
        search = (f'<form class="cv-search" method="get" action="/projects" role="search">{icon("search", 18)}'
                  f'<input name="q" value="{esc(query)}" placeholder="Search projects by name, type or location…" aria-label="Search projects"></form>')
        p = (lambda s: f'/projects/{pid}/{s}') if pid else (lambda s: '/projects/new')
        bottom_items = [('home', 'Home', '/'), ('folder', 'Projects', '/projects'), ('calc', '', '/estimate'),
                        ('beam', 'Structure', '/structure'), ('menu', 'More', '/more')]
        bottom = '<div class="cv-bottom">' + ''.join(
            f'<a class="{"fab" if not lb else ("on" if _is_active(h, path) else "")}" href="{esc(h)}" aria-label="{esc(lb or "Smart Estimate")}">{icon(ic, 22)}{esc(lb)}</a>'
            for ic, lb, h in bottom_items) + '</div>'
    else:
        right = ('<a class="cv-btn ghost sm" href="/guest">Guest Preview</a><a class="cv-btn ghost sm" href="/login">Sign in</a>'
                 '<a class="cv-btn sm" href="/register">Get started</a>')
        search = '<div class="cv-search" style="visibility:hidden"></div>'
        bottom = ''
    side_foot = ('<div class="cv-sidefoot"><div class="cv-help"><b>Engineer review required</b>Civora gives quantities and guidance. '
                 'Structural designs must be checked and approved by a licensed engineer.</div></div>')
    doc = f'''<!doctype html><html lang="{"ta" if lang == "ta" else "en"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} | Civora AI</title><link rel="icon" href="/favicon.svg" type="image/svg+xml"><meta name="theme-color" content="#142b45">
<style>{LEGACY_CSS}{CSS}</style></head><body class="{"cv-auth " if auth_page else ""}cv-mode-{esc(mode)} cv-lang-{esc(lang)}">
<input type="checkbox" id="cv-navtoggle" aria-hidden="true">
<div class="cv-shell">
<label class="cv-scrim" for="cv-navtoggle"></label>
<div class="cv-side"><a class="cv-brand" href="/">{LOGO}<span><b>Civora <i>AI</i></b><small>Construction Intelligence Workspace</small></span></a>
<div class="cv-nav">{nav}</div>{side_foot}</div>
<div class="cv-main"><div class="cv-top"><label class="cv-burger cv-iconbtn" for="cv-navtoggle" aria-label="Menu">{icon("menu", 20)}</label>{search}<div class="cv-topr">{right}</div></div>
{context_bar(context)}<div class="cv-content">{body}</div></div></div>{bottom}</body></html>'''
    if lang == 'ta':  # v3.3: Tamil interface (exact whole-text matches only; numbers and form values untouched)
        import i18n_v330
        doc = i18n_v330.translate_html(doc)
    return doc


# ---------------------------------------------------------------- home dashboard
QUICK = [
    # icon, label, sub-line, colour, link-key
    ('calc', 'Smart Estimate', 'Drawing → full estimate', '#2563eb', 'smart'),
    ('plus', 'New Project', 'Start a new building', '#16a34a', 'new'),
    ('rupee', 'Rate Master', 'Your local prices', '#ea580c', 'rates'),
    ('report', 'Reports', 'Excel, PDF, Download All', '#0ea5e9', 'reports'),
]
HOW = [('upload', 'Upload your drawing', 'PDF, CAD (DXF), photo or scan'),
       ('check', 'Check what is missing', 'Civora fills the rest with typical values'),
       ('report', 'Get the full estimate', 'Materials, steel, cost & reports')]


def _stage_chip(done):
    nxt = next((s for s in STEPS if s[0] not in set(done)), None)
    if not nxt:
        return '<span class="cv-chip" style="background:#dcfce7;color:#15803d">Reports ready</span>'
    c = nxt[4]
    return f'<span class="cv-chip" style="background:{c}1a;color:{c}">Next: {esc(nxt[2])}</span>'


def recent_html(recent):
    if not recent:
        return ('<div class="cv-empty"><b>No projects yet</b>Create your first project to start the workflow.'
                '<div style="margin-top:10px"><a class="cv-btn sm" href="/projects/new">' + icon('plus', 16) + 'New Project</a></div></div>')
    out = []
    role_names = {'engineer': 'Engineer', 'colleague': 'Colleague', 'dealer': 'Dealer', 'customer': 'Customer'}
    for r in recent:
        done = r.get('done', ())
        shared = (f'<span class="cv-chip" style="background:#eef2f7;color:#475569;margin-left:6px">Shared · {role_names[r["role"]]}</span>'
                  if r.get('role') in role_names else '')
        pct = round(100 * len(done) / len(STEPS))
        colour = CATEGORY_COLOURS.get(r.get('type'), '#2563eb')
        out.append(f'''<a class="cv-ri" href="/projects/{esc(r['id'])}/workflow"><span class="bx" style="background:{colour}">{icon('site', 20)}</span>
<span class="mid"><b>{esc(r['name'])}{shared}</b><small>{esc(r.get('type', ''))} · {esc(r.get('location', ''))}</small>
<span class="cv-bar"><i style="width:{pct}%;background:{colour}"></i></span></span>
<span style="text-align:right">{_stage_chip(done)}<small style="display:block;margin-top:4px">{pct}% done</small></span></a>''')
    return '<div class="cv-recent">' + ''.join(out) + '</div>'


def home_html(user, recent=(), latest=None, workflow_cards='', rates_set=0, csrf_token=''):
    """v2.6 clean dashboard: one main action, how-it-works, recent projects, 4 shortcuts."""
    pid = latest['id'] if latest else None

    def plink(sub):
        if not user:
            return '/register'
        if sub == 'new':
            return '/projects/new'
        if sub == 'rates':
            return '/rates'
        if sub == 'smart' and not pid:
            return '/projects/new?next=smart'
        return f'/projects/{pid}/{sub}' if pid else '/projects/new'

    greet = f'Welcome back, {esc(user["name"].split()[0])}' if user and user['name'] else 'CIVORA AI'
    cont = (f'<a class="cv-btn light" href="/projects/{esc(pid)}/workflow">Continue {esc(latest["name"])} {icon("arrow", 16)}</a>' if pid
            else ('' if user else '<a class="cv-btn light" href="/guest">Try Guest Preview</a>'))
    how = ''.join(f'<div class="cv-how"><span class="n">{i}</span>{icon(ic, 22)}<span><b>{esc(t)}</b><small>{esc(d)}</small></span></div>'
                  for i, (ic, t, d) in enumerate(HOW, 1))
    hero = f'''<div class="cv-hero"><span class="tag">{icon('site', 14)} {greet}</span>
<h1>Enter the area. Get the full estimate.</h1>
<p>Materials · Steel · Cost · Reports — type the built-up area, or upload the drawing for an exact estimate.</p>
<form class="cv-quickform" method="post" action="/quick"><input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
<label class="qa"><span>Built-up area</span><span class="qi"><input name="area" inputmode="numeric" required placeholder="1000" aria-label="Built-up area in sq.ft"><b>sq.ft</b></span></label>
<label class="qa"><span>Floors</span><select name="floors" aria-label="Floors"><option value="1">G (ground)</option><option value="2">G + 1</option><option value="3">G + 2</option><option value="4">G + 3</option></select></label>
<button class="cv-btn qgo">Get full estimate {icon('arrow', 16)}</button></form>
<div class="acts" style="margin-top:14px"><a class="cv-btn light" href="{plink('smart')}">{icon('upload', 18)}Upload a drawing instead</a>{cont}</div>
<div class="cv-hows">{how}</div></div>'''
    quick = ''.join(f'<a class="cv-qa" href="{esc(plink(key))}"><span class="ib" style="background:{c}17;color:{c}">{icon(ic, 23)}</span>'
                    f'<span><b>{esc(lb)}</b><small>{esc(sub)}</small></span></a>' for ic, lb, sub, c, key in QUICK)
    recent_block = recent_html(recent) if user else (
        '<div class="cv-empty"><b>Sign in to see your projects</b>Your projects, drawings and reports are saved privately.'
        '<div style="margin-top:10px"><a class="cv-btn sm" href="/register">Create free account</a></div></div>')
    rates_card = ''
    if user:
        total = len(__import__('rates_v260').RATE_KEYS)
        rates_card = (f'''<div class="cv-card cv-ratecard"><h3>{icon('rupee', 18)} Your rates</h3>
<p class="sub">{'Set your local cement, steel, sand and labour rates once — every estimate is priced automatically.' if not rates_set else f'{rates_set} of {total} rates set. New estimates are priced automatically.'}</p>
<div class="cv-bar" style="margin:4px 0 12px"><i style="width:{round(100 * rates_set / total)}%;background:#ea580c"></i></div>
<a class="cv-btn sm{' ghost' if rates_set else ''}" href="/rates">{'Update rates' if rates_set else 'Set my rates'}</a></div>''')
    return f'''{hero}
<div class="cv-quick">{quick}</div>
<div class="cv-row"><div><div class="cv-sec"><h2>Recent Projects</h2>{'<a href="/projects">View all →</a>' if user else ''}</div>
<div class="cv-card" style="padding:10px">{recent_block}</div></div><div><div class="cv-sec"><h2>Pricing</h2></div>{rates_card or '<div class="cv-empty"><b>Free account</b>Save projects, rates and reports.</div>'}</div></div>
<p class="cv-disclaim">{icon('shield', 16)}<span>Quantities, costs and structural sizes are planning estimates. All structural design must be reviewed and approved by a qualified, licensed engineer before construction.</span></p>'''
