"""Civora AI v3.2 - Reinforcement detail sketches for footings, columns, beams and slabs.

Draws plan / section / elevation SVGs from what the user has ENTERED:
  * element sizes from the Structural Studio (civora_structural_v210)
  * bars from the BBS Studio, linked by mark: F1-MESH / F1-X / F1-Y, C1-MAIN / C1-TIES,
    B1-TOP / B1-BOT / B1-STIR, S1-MAIN / S1-DIST (a bar with only the element mark counts as main)

It shows WHERE the rods go, WHERE they bend or hook, and WHERE laps are usually placed, with
spacing worked out from the entered bar counts. It is a site-checking sketch of common practice,
not a design: bar sizes, numbers, laps and covers must come from the approved structural drawing.
"""
from html import escape as _e

FOOTINGS = ('isolated_footing', 'combined_footing', 'raft', 'strip_footing', 'stepped_footing', 'pile_cap')
COLUMNS = ('column', 'pedestal')
BEAMS = ('plinth_beam', 'grade_beam', 'roof_beam', 'lintel', 'tie_beam', 'ring_beam', 'cantilever_beam', 'secondary_beam')
SLABS = ('slab', 'flat_slab', 'sunken_slab', 'cantilever_slab', 'porch_slab', 'loft')
DETAILABLE = FOOTINGS + COLUMNS + BEAMS + SLABS
TYPICAL_COVER_MM = {'footing': 50, 'column': 40, 'beam': 25, 'slab': 20}

C_CONC, C_EDGE, C_MAIN, C_TIE, C_LAP, C_DIM, C_TXT, C_PCC = '#eef2f7', '#475569', '#1d4ed8', '#0d9488', '#f59e0b', '#64748b', '#0f172a', '#e2e8f0'


def family(kind):
    if kind in FOOTINGS:
        return 'footing'
    if kind in COLUMNS:
        return 'column'
    if kind in BEAMS:
        return 'beam'
    if kind in SLABS:
        return 'slab'
    return None


ROLE_WORDS = {'': 'main', 'MAIN': 'main', 'LONG': 'main', 'VERT': 'main',
              'TIE': 'ties', 'TIES': 'ties', 'RING': 'ties', 'RINGS': 'ties', 'STIR': 'ties', 'STIRRUP': 'ties', 'STIRRUPS': 'ties', 'LINKS': 'ties',
              'TOP': 'top', 'BOT': 'bottom', 'BTM': 'bottom', 'BOTTOM': 'bottom',
              'X': 'x', 'LX': 'x', 'Y': 'y', 'LY': 'y', 'MESH': 'mesh',
              'DIST': 'dist', 'DISTRIBUTION': 'dist', 'CRANK': 'main', 'EXTRA': 'extra', 'CHAIR': 'extra'}


def bar_role(bar_mark, element_mark):
    """Role of a bar from the part of its mark after the element mark (C1-TIES -> ties)."""
    m, e = str(bar_mark).strip().upper(), str(element_mark).strip().upper()
    if m != e and not m.startswith(e + '-') and not m.startswith(e + '_') and not m.startswith(e + ' '):
        return None
    suffix = m[len(e):].lstrip('-_ ')
    word = suffix.split('-')[0].split(' ')[0]
    return ROLE_WORDS.get(word, 'extra')


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def linked_bars(element, bars):
    """{role: {'dia', 'per', 'lap', 'bend', 'hook', 'mark'}} with bar counts per single element."""
    n_el = max(int(_f(element['p'].get('count')) or 1), 1)
    out = {}
    for b in bars:
        role = bar_role(b['mark'], element['mark'])
        if not role or role in out:
            continue
        p = b['p']
        out[role] = {'dia': int(_f(p.get('diameter_mm'))), 'per': max(1, round(_f(p.get('count')) / n_el)), 'total': int(_f(p.get('count'))),
                     'lap': _f(p.get('lap')), 'bend': _f(p.get('bend')), 'hook': _f(p.get('hook')), 'mark': b['mark']}
    return out


def spacing_mm(span_m, n, cover_mm):
    """Centre-to-centre spacing when n bars are spread over span_m with cover each side."""
    if n is None or n < 2 or span_m <= 0:
        return None
    return max(round((span_m * 1000 - 2 * cover_mm) / (n - 1)), 1)


# ------------------------------------------------------------------ tiny svg helper
class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label, self.p = w, h, label, []

    def rect(self, x, y, w, h, fill=C_CONC, stroke=C_EDGE, sw=1.5, dash=None, rx=0):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, .5):.1f}" height="{max(h, .5):.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def line(self, x1, y1, x2, y2, c=C_MAIN, sw=2, dash=None, cap='round'):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.p.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c}" stroke-width="{sw}" stroke-linecap="{cap}"{d}/>')

    def path(self, d, c=C_MAIN, sw=2, fill='none'):
        self.p.append(f'<path d="{d}" fill="{fill}" stroke="{c}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')

    def dot(self, x, y, r=3.2, c=C_MAIN):
        self.p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{c}"/>')

    def text(self, x, y, s, anchor='start', size=11, weight=400, c=C_TXT):
        self.p.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}" fill="{c}">{_e(str(s))}</text>')

    def band(self, x, y, w, h, c=C_LAP, op=.28):
        self.p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, .5):.1f}" height="{max(h, .5):.1f}" fill="{c}" fill-opacity="{op}"/>')

    def hdim(self, x1, x2, y, label):
        self.line(x1, y, x2, y, C_DIM, 1, cap='butt')
        for x in (x1, x2):
            self.line(x, y - 4, x, y + 4, C_DIM, 1, cap='butt')
        self.text((x1 + x2) / 2, y - 5, label, 'middle', 10, 400, C_DIM)

    def vdim(self, x, y1, y2, label):
        self.line(x, y1, x, y2, C_DIM, 1, cap='butt')
        for y in (y1, y2):
            self.line(x - 4, y, x + 4, y, C_DIM, 1, cap='butt')
        self.p.append(f'<text x="{x - 6:.1f}" y="{(y1 + y2) / 2:.1f}" text-anchor="middle" font-size="10" fill="{C_DIM}" '
                      f'transform="rotate(-90 {x - 6:.1f} {(y1 + y2) / 2:.1f})">{_e(label)}</text>')

    def title(self, x, y, s):
        self.text(x, y, s, 'start', 12, 700, C_TXT)

    def render(self):
        return (f'<svg class="rd-svg" viewBox="0 0 {self.w} {self.h}" width="100%" role="img" aria-label="{_e(self.label)}" '
                f'font-family="Segoe UI, system-ui, sans-serif">' + ''.join(self.p) + '</svg>')


def _fit(real_w, real_h, box_w, box_h, min_h=0):
    """Pixel size of a real_w x real_h shape fitted in a box (keeps aspect; optional minimum height)."""
    s = min(box_w / max(real_w, 1e-6), box_h / max(real_h, 1e-6))
    return real_w * s, max(real_h * s, min_h), s


def _bar_txt(b, fallback):
    return f'{b["per"]} nos {b["dia"]} mm' if b else fallback


def _mm(v):
    return f'{v * 1000:,.0f} mm'


def legend():
    return ('<div class="rd-legend"><span><i style="background:#1d4ed8"></i>Main bars</span><span><i style="background:#0d9488"></i>Ties / stirrups / distribution</span>'
            '<span><i style="background:#f59e0b;opacity:.6"></i>Lap zone</span><span><i style="background:#eef2f7;border:1px solid #475569"></i>Concrete</span></div>')


# ------------------------------------------------------------------ footing
def footing(el, bars):
    p = el['p']
    L, W, D = _f(p.get('length_m')), _f(p.get('width_m')), _f(p.get('depth_m'))
    cover = TYPICAL_COVER_MM['footing']
    bx, by = bars.get('x'), bars.get('y')
    mesh = bars.get('mesh') or bars.get('main') or bars.get('bottom')
    if mesh and not bx and not by:
        half = max(1, round(mesh['per'] / 2))
        bx = dict(mesh, per=half)
        by = dict(mesh, per=max(1, mesh['per'] - half))
    sv = Svg(730, 330, f'Footing {el["mark"]} reinforcement sketch: plan and section')
    # plan
    sv.title(20, 22, 'PLAN')
    pw, ph, s = _fit(L, W, 250, 210)
    x0, y0 = 40, 50
    sv.rect(x0, y0, pw, ph)
    c = cover / 1000 * s
    nx = min((bx or {}).get('per', 7), 26)          # bars running along L (drawn horizontal)
    ny = min((by or {}).get('per', 7), 26)          # bars running along W (drawn vertical)
    for i in range(nx):
        y = y0 + c + (ph - 2 * c) * (i / max(nx - 1, 1))
        sv.line(x0 + c, y, x0 + pw - c, y, C_MAIN, 1.6)
    for i in range(ny):
        x = x0 + c + (pw - 2 * c) * (i / max(ny - 1, 1))
        sv.line(x, y0 + c, x, y0 + ph - c, C_TIE, 1.6)
    col = min(pw, ph) * .22
    sv.rect(x0 + pw / 2 - col / 2, y0 + ph / 2 - col / 2, col, col, fill='#ffffff', stroke=C_TXT, sw=1.2, dash='4 3')
    sv.text(x0 + pw / 2, y0 + ph / 2 + 4, 'column', 'middle', 9, 600, C_DIM)
    sv.hdim(x0, x0 + pw, y0 + ph + 18, f'L = {L:g} m')
    sv.vdim(x0 - 14, y0, y0 + ph, f'W = {W:g} m')
    sxa = spacing_mm(W, (bx or {}).get('per'), cover)
    sya = spacing_mm(L, (by or {}).get('per'), cover)
    sv.text(x0, y0 + ph + 40, f'Along L: {_bar_txt(bx, "bars (add F-X / F-MESH in BBS)")}' + (f' @ ≈{sxa} c/c' if sxa else ''), 'start', 10.5, 600, C_MAIN)
    sv.text(x0, y0 + ph + 55, f'Along W: {_bar_txt(by, "bars (add F-Y / F-MESH in BBS)")}' + (f' @ ≈{sya} c/c' if sya else ''), 'start', 10.5, 600, C_TIE)
    # section
    sv.title(360, 22, 'SECTION A–A')
    sw_, sh_, s2 = _fit(L, D, 280, 120, 46)
    xs, ys = 370, 70
    sv.rect(xs - 12, ys + sh_, sw_ + 24, 12, fill=C_PCC, stroke=C_DIM, sw=1)
    sv.text(xs + sw_ + 16, ys + sh_ + 10, 'PCC bed', 'start', 9.5, 400, C_DIM)
    sv.rect(xs, ys, sw_, sh_)
    cc = max(cover / 1000 * s2, 6)
    yb = ys + sh_ - cc
    up = min(sh_ - 2 * cc, 30)
    sv.path(f'M{xs + cc} {yb - up} L{xs + cc} {yb} L{xs + sw_ - cc} {yb} L{xs + sw_ - cc} {yb - up}', C_MAIN, 2.4)
    nd = min(ny, 14)
    for i in range(nd):
        sv.dot(xs + cc + 4 + (sw_ - 2 * cc - 8) * (i / max(nd - 1, 1)), yb - 5, 2.6, C_TIE)
    cx = xs + sw_ / 2
    for dx in (-10, 10):
        sv.path(f'M{cx + dx} {ys - 34} L{cx + dx} {yb - 8} L{cx + dx + (14 if dx > 0 else -14)} {yb - 8}', C_MAIN, 1.8)
    sv.rect(cx - 16, ys - 40, 32, 40, fill='none', stroke=C_TXT, sw=1, dash='4 3')
    sv.text(cx + 22, ys - 24, 'column starter bars', 'start', 9.5, 600, C_TXT)
    sv.text(cx + 22, ys - 12, 'with L-foot resting on the mesh', 'start', 9.5, 400, C_DIM)
    sv.text(xs + cc + 4, yb - up - 6, 'L-bend up', 'start', 9.5, 600, C_MAIN)
    sv.vdim(xs - 22, ys, ys + sh_, f'{D:g} m')
    sv.hdim(xs, xs + sw_, ys + sh_ + 30, f'{L:g} m')
    sv.text(xs, ys + sh_ + 52, f'Bottom cover ≈ {cover} mm (typical) on cover blocks.', 'start', 9.5, 400, C_DIM)
    notes = [f'Bottom mesh in both directions{f" — along L: {_bar_txt(bx, "")}, along W: {_bar_txt(by, "")}" if (bx or by) else ""}; the bars along the LONGER side go at the bottom unless the drawing says otherwise.',
             'Ends of the mesh bars are bent up (L-bend) as shown on the drawing' + (f' — bend allowance entered: {_mm(bx["bend"])}' if bx and bx.get('bend') else '') + '.',
             'Column starter bars sit on the mesh with an L-foot and are tied to it before concreting.',
             f'Use cover blocks for about {cover} mm bottom cover; never place bars directly on the soil or PCC.']
    return sv.render(), notes


# ------------------------------------------------------------------ column
def column(el, bars):
    p = el['p']
    b, d, H = _f(p.get('length_m')), _f(p.get('width_m')), _f(p.get('depth_m'))
    cover = TYPICAL_COVER_MM['column']
    main, ties = bars.get('main'), bars.get('ties')
    n = main['per'] if main else 4
    sv = Svg(730, 380, f'Column {el["mark"]} reinforcement sketch: section and elevation')
    # section
    sv.title(20, 22, 'SECTION')
    pw, ph, s = _fit(b, d, 170, 170)
    x0, y0 = 50, 60
    sv.rect(x0, y0, pw, ph)
    c = max(cover / 1000 * s, 8)
    sv.rect(x0 + c, y0 + c, pw - 2 * c, ph - 2 * c, fill='none', stroke=C_TIE, sw=2, rx=3)
    sv.path(f'M{x0 + c + 2} {y0 + c + 12} L{x0 + c + 12} {y0 + c + 22} M{x0 + c + 12} {y0 + c + 2} L{x0 + c + 22} {y0 + c + 12}', C_TIE, 2)
    sv.text(x0 + c + 26, y0 + c + 22, '135° hooks', 'start', 9, 600, C_TIE)
    # bars round the perimeter: 4 corners first, the rest on the longer faces
    ix0, iy0, ix1, iy1 = x0 + c + 4, y0 + c + 4, x0 + pw - c - 4, y0 + ph - c - 4
    pts = [(ix0, iy0), (ix1, iy0), (ix1, iy1), (ix0, iy1)][:max(n, 1)]
    extra = max(n - 4, 0)
    long_h = (ix1 - ix0) >= (iy1 - iy0)
    per_face = [extra // 2 + extra % 2, extra // 2]
    for face, k in enumerate(per_face):
        for i in range(1, k + 1):
            t = i / (k + 1)
            if long_h:
                pts.append((ix0 + (ix1 - ix0) * t, iy0 if face == 0 else iy1))
            else:
                pts.append((ix0 if face == 0 else ix1, iy0 + (iy1 - iy0) * t))
    for x, y in pts:
        sv.dot(x, y, 4, C_MAIN)
    sv.hdim(x0, x0 + pw, y0 + ph + 18, f'{_mm(b)}')
    sv.vdim(x0 - 14, y0, y0 + ph, f'{_mm(d)}')
    sv.text(x0 - 30, y0 + ph + 44, f'Main: {_bar_txt(main, "4 corner bars (typical — add C-MAIN in BBS)")}', 'start', 10.5, 600, C_MAIN)
    tie_sp = round(H * 1000 / ties['per']) if ties and H else None
    sv.text(x0 - 30, y0 + ph + 60, f'Ties: {ties["dia"]} mm, {ties["per"]} nos' + (f' (≈{tie_sp} mm c/c average)' if tie_sp else '') if ties else 'Ties: add C-TIES in BBS', 'start', 10.5, 600, C_TIE)
    sv.text(x0 - 30, y0 + ph + 76, f'Cover ≈ {cover} mm (typical)', 'start', 10, 400, C_DIM)
    # elevation
    sv.title(330, 22, 'ELEVATION (one storey)')
    eh, ew = 300, max(min(70, 70 * b / max(d, b, .01) + 30), 40)
    ex, ey = 440, 50
    sv.rect(ex - 50, ey - 14, ew + 100, 14, fill='#cbd5e1', stroke=C_EDGE, sw=1)
    sv.rect(ex - 50, ey + eh, ew + 100, 14, fill='#cbd5e1', stroke=C_EDGE, sw=1)
    sv.text(ex + ew + 56, ey - 3, 'beam / slab above', 'start', 9, 400, C_DIM)
    sv.text(ex + ew + 56, ey + eh + 11, 'floor / beam below', 'start', 9, 400, C_DIM)
    sv.rect(ex, ey, ew, eh)
    lo_m = max(max(b, d), H / 6 if H else 0, .45)
    lo = min(eh * lo_m / max(H, .1), eh * .3) if H else eh * .2
    lap_top, lap_bot = ey + eh * .25, ey + eh * .75
    lap_len_px = min((eh * (main['lap'] / H)) if (main and main.get('lap') and H) else eh * .2, eh * .5)
    mid = ey + eh / 2
    sv.band(ex - 6, mid - lap_len_px / 2, ew + 12, lap_len_px, C_LAP, .35)
    for xb in (ex + 9, ex + ew - 9):
        sv.line(xb, ey - 14, xb, mid + lap_len_px / 2, C_MAIN, 2.4)
        sv.line(xb + 4, mid - lap_len_px / 2, xb + 4, ey + eh + 14, C_MAIN, 2.4)
    # ties: closer in the end zones
    for zone_top, zone_bot, step in ((ey + 4, ey + lo, 7), (ey + lo, ey + eh - lo, 15), (ey + eh - lo, ey + eh - 4, 7)):
        y = zone_top
        while y <= zone_bot:
            sv.line(ex + 4, y, ex + ew - 4, y, C_TIE, 1.4)
            y += step
    sv.vdim(ex - 18, ey, ey + lo, f'{lo_m:.2f} m')
    sv.vdim(ex - 18, ey + eh - lo, ey + eh, f'{lo_m:.2f} m')
    sv.text(ex + ew + 12, ey + lo / 2 + 4, 'closer ties', 'start', 9.5, 600, C_TIE)
    sv.text(ex + ew + 12, ey + eh - lo / 2 + 4, 'closer ties', 'start', 9.5, 600, C_TIE)
    sv.text(ex + ew + 12, mid - 4, 'LAP ZONE', 'start', 10, 700, '#b45309')
    sv.text(ex + ew + 12, mid + 10, f'lap {_mm(main["lap"])} (entered)' if main and main.get('lap') else 'lap length as per drawing', 'start', 9.5, 400, '#b45309')
    sv.text(ex + ew + 12, mid + 23, 'middle half of the height', 'start', 9.5, 400, '#b45309')
    sv.vdim(ex + ew + 145, ey, ey + eh, f'H = {H:g} m' if H else 'storey height')
    notes = [f'Main bars ({_bar_txt(main, "as per drawing")}) run full height; lap them in the MIDDLE HALF of the storey height — never at the floor or beam level.',
             'Do not lap more than half of the bars at the same level — stagger the laps.' + (f' Lap length entered: {_mm(main["lap"])}.' if main and main.get('lap') else ''),
             f'Ties closer near the top and bottom (about {lo_m:.2f} m each end, the larger of the column size, H/6 or 450 mm) and through the beam-column joint.',
             f'Tie ends bent to 135° hooks into the core, about {cover} mm cover to the ties — typical practice; follow the structural drawing.']
    return sv.render(), notes


# ------------------------------------------------------------------ beam
def beam(el, bars):
    p = el['p']
    L, bw, D = _f(p.get('length_m')), _f(p.get('width_m')), _f(p.get('depth_m'))
    cover = TYPICAL_COVER_MM['beam']
    top, bot = bars.get('top'), bars.get('bottom') or bars.get('main')
    st = bars.get('ties')
    sv = Svg(730, 340, f'Beam {el["mark"]} reinforcement sketch: elevation and section')
    sv.title(20, 22, 'ELEVATION (one span)')
    x0, y0, span = 60, 66, 420
    dh = max(min(span * D / max(L, .1), 100), 76)
    sv.rect(x0 - 26, y0 - 30, 26, dh + 60, fill='#cbd5e1', stroke=C_EDGE, sw=1)
    sv.rect(x0 + span, y0 - 30, 26, dh + 60, fill='#cbd5e1', stroke=C_EDGE, sw=1)
    sv.text(x0 - 13, y0 + dh + 44, 'column', 'middle', 9, 400, C_DIM)
    sv.text(x0 + span + 13, y0 + dh + 44, 'column', 'middle', 9, 400, C_DIM)
    sv.rect(x0, y0, span, dh)
    c = max(cover / 1000 * (dh / max(D, .1)), 7)
    yt, yb = y0 + c, y0 + dh - c
    # top bars: L-bend down into the columns, lap at mid-span
    sv.band(x0 + span * .4, y0 - 2, span * .2, dh * .35, C_LAP, .35)
    sv.path(f'M{x0 - 18} {yt + 26} L{x0 - 18} {yt} L{x0 + span * .6} {yt}', C_MAIN, 2.4)
    sv.path(f'M{x0 + span * .4} {yt + 4} L{x0 + span + 18} {yt + 4} L{x0 + span + 18} {yt + 30}', C_MAIN, 2.4)
    # bottom bars: L-bend up into the columns, laps near the supports, not at mid-span
    sv.band(x0 + span * .06, yb - dh * .3, span * .16, dh * .32, C_LAP, .35)
    sv.path(f'M{x0 - 18} {yb - 26} L{x0 - 18} {yb} L{x0 + span * .22} {yb}', C_MAIN, 2.4)
    sv.path(f'M{x0 + span * .06} {yb - 4} L{x0 + span + 18} {yb - 4} L{x0 + span + 18} {yb - 30}', C_MAIN, 2.4)
    # stirrups: closer within about 2 x depth of each support
    zone = min(span * 2 * D / max(L, .1), span * .3)
    for a, b_, step in ((x0 + 6, x0 + zone, 7), (x0 + zone, x0 + span - zone, 15), (x0 + span - zone, x0 + span - 6, 7)):
        x = a
        while x <= b_:
            sv.line(x, y0 + 4, x, y0 + dh - 4, C_TIE, 1.3)
            x += step
    sv.text(x0 + span / 2, y0 - 8, 'LAP top bars here (mid-span)', 'middle', 9.5, 700, '#b45309')
    sv.text(x0 + span * .14, y0 + dh + 16, 'LAP bottom bars here', 'middle', 9.5, 700, '#b45309')
    sv.text(x0 + span * .14, y0 + dh + 28, '(near support, not mid-span)', 'middle', 9, 400, '#b45309')
    sv.text(x0 + zone / 2, y0 - 8, 'closer stirrups', 'middle', 9, 700, C_TIE)
    sv.text(x0 + span - zone / 2, y0 - 8, 'closer stirrups', 'middle', 9, 700, C_TIE)
    sv.hdim(x0, x0 + span, y0 + dh + 50, f'clear span ≈ {L:g} m')
    sv.vdim(x0 - 36, y0, y0 + dh, f'{_mm(D)}')
    # section
    sv.title(540, 22, 'SECTION')
    pw, ph, s = _fit(bw, D, 90, 150)
    sx, sy = 575, 60
    sv.rect(sx, sy, pw, ph)
    cc = max(cover / 1000 * s, 7)
    sv.rect(sx + cc, sy + cc, pw - 2 * cc, ph - 2 * cc, fill='none', stroke=C_TIE, sw=2, rx=3)
    sv.path(f'M{sx + cc + 2} {sy + cc + 10} L{sx + cc + 11} {sy + cc + 19}', C_TIE, 2)
    nt, nb = (top or {}).get('per', 2), (bot or {}).get('per', 3)
    for k, yy in ((nt, sy + cc + 5), (nb, sy + ph - cc - 5)):
        k = max(min(k, 8), 1)
        for i in range(k):
            sv.dot(sx + cc + 5 + (pw - 2 * cc - 10) * (i / max(k - 1, 1)) if k > 1 else sx + pw / 2, yy, 3.6, C_MAIN)
    sv.hdim(sx, sx + pw, sy + ph + 16, _mm(bw))
    sv.text(sx - 30, sy + ph + 38, f'Top: {_bar_txt(top, "add B-TOP")}', 'start', 10, 600, C_MAIN)
    sv.text(sx - 30, sy + ph + 52, f'Bottom: {_bar_txt(bot, "add B-BOT")}', 'start', 10, 600, C_MAIN)
    st_sp = round(L * 1000 / st['per']) if st and L else None
    sv.text(sx - 30, sy + ph + 66, f'Stirrups: {st["dia"]} mm, {st["per"]} nos' + (f' ≈{st_sp} c/c avg' if st_sp else '') if st else 'Stirrups: add B-STIR', 'start', 10, 600, C_TIE)
    notes = [f'Top bars ({_bar_txt(top, "as per drawing")}) bend DOWN into the columns at both ends; if they must be lapped, lap them in the middle third of the span.',
             f'Bottom bars ({_bar_txt(bot, "as per drawing")}) bend UP into the columns; lap them near the supports — never at mid-span.' + (f' Lap length entered: {_mm(bot["lap"])}.' if bot and bot.get("lap") else ''),
             'Stirrups closer for about twice the beam depth from each column face; 135° hooks; first stirrup about 50 mm from the column face.',
             f'Side and bottom cover about {cover} mm (typical) using cover blocks — follow the structural drawing.']
    return sv.render(), notes


# ------------------------------------------------------------------ slab
def slab(el, bars):
    p = el['p']
    L, W, t = _f(p.get('length_m')), _f(p.get('width_m')), _f(p.get('depth_m'))
    cover = TYPICAL_COVER_MM['slab']
    short, long_ = (min(L, W), max(L, W))
    main = bars.get('main') or bars.get('x') or bars.get('bottom')
    dist = bars.get('dist') or bars.get('y')
    sv = Svg(730, 330, f'Slab {el["mark"]} reinforcement sketch: plan and section')
    sv.title(20, 22, 'PLAN')
    pw, ph, s = _fit(long_, short, 300, 190)
    x0, y0 = 40, 50
    sv.rect(x0, y0, pw, ph)
    c = max(cover / 1000 * s, 5)
    nm = min((main or {}).get('per', 12), 30)
    nd = min((dist or {}).get('per', 8), 24)
    for i in range(nm):        # main bars span the SHORT direction (drawn vertical)
        x = x0 + c + (pw - 2 * c) * (i / max(nm - 1, 1))
        sv.line(x, y0 + c, x, y0 + ph - c, C_MAIN, 1.8 if i % 2 == 0 else 1.2)
        if i % 2 == 1:         # alternate bars cranked near the supports
            for yy in (y0 + ph / 7, y0 + ph - ph / 7):
                sv.dot(x, yy, 2.2, '#b45309')
    for i in range(nd):
        y = y0 + c + (ph - 2 * c) * (i / max(nd - 1, 1))
        sv.line(x0 + c, y, x0 + pw - c, y, C_TIE, 1.1)
    sv.hdim(x0, x0 + pw, y0 + ph + 18, f'{long_:g} m (long span)')
    sv.vdim(x0 - 14, y0, y0 + ph, f'{short:g} m short span')
    sm = spacing_mm(long_, (main or {}).get('per'), cover)
    sd = spacing_mm(short, (dist or {}).get('per'), cover)
    sv.text(x0, y0 + ph + 40, f'Main (short span): {_bar_txt(main, "add S-MAIN in BBS")}' + (f' @ ≈{sm} c/c' if sm else ''), 'start', 10.5, 600, C_MAIN)
    sv.text(x0, y0 + ph + 55, f'Distribution (long span): {_bar_txt(dist, "add S-DIST in BBS")}' + (f' @ ≈{sd} c/c' if sd else ''), 'start', 10.5, 600, C_TIE)
    sv.text(x0, y0 + ph + 70, '• orange dots: alternate bars cranked up at about 1/7 of the span from each support', 'start', 9.5, 400, '#b45309')
    # section along the short span
    sv.title(380, 22, 'SECTION (short span)')
    sx, sy, sw_ = 390, 90, 260
    th = max(min(sw_ * t / max(short, .1) * 3, 40), 22)
    sv.rect(sx - 16, sy - 20, 16, th + 50, fill='#cbd5e1', stroke=C_EDGE, sw=1)
    sv.rect(sx + sw_, sy - 20, 16, th + 50, fill='#cbd5e1', stroke=C_EDGE, sw=1)
    sv.rect(sx, sy, sw_, th)
    cb, ct = sy + th - 5, sy + 5
    k = sw_ / 7
    sv.line(sx - 10, cb, sx + sw_ + 10, cb, C_MAIN, 2)
    sv.text(sx + sw_ / 2, sy + th + 16, 'straight bar (bottom)', 'middle', 9.5, 600, C_MAIN)
    sv.path(f'M{sx - 10} {ct} L{sx + k} {ct} L{sx + k + 14} {cb} L{sx + sw_ - k - 14} {cb} L{sx + sw_ - k} {ct} L{sx + sw_ + 10} {ct}', '#b45309', 2)
    sv.text(sx + sw_ / 2, sy - 10, 'alternate bar cranked up near supports', 'middle', 9.5, 700, '#b45309')
    sv.hdim(sx, sx + k, sy + th + 34, 'span/7')
    sv.hdim(sx + sw_ - k, sx + sw_, sy + th + 34, 'span/7')
    for i in range(9):
        sv.dot(sx + 14 + (sw_ - 28) * i / 8, cb - 5, 2.2, C_TIE)
    sv.vdim(sx + sw_ + 32, sy, sy + th, f'{_mm(t)}')
    sv.text(sx, sy + th + 64, f'Cover ≈ {cover} mm (typical); distribution bars sit on top of the main bars.', 'start', 9.5, 400, C_DIM)
    notes = [f'Main bars ({_bar_txt(main, "as per drawing")}) span the SHORTER direction ({short:g} m) and sit at the bottom; distribution bars go above them.',
             'Every alternate main bar is cranked up near the supports (about 1/7 of the span) to carry the top tension at the beams — or provide extra top bars as the drawing shows.',
             'Laps in bottom bars near the supports, laps in top bars near mid-span; stagger laps.' + (f' Lap length entered: {_mm(main["lap"])}.' if main and main.get('lap') else ''),
             f'Use cover blocks for about {cover} mm bottom cover and chairs to hold the top (cranked) bars in place during concreting.']
    return sv.render(), notes


DRAW = {'footing': footing, 'column': column, 'beam': beam, 'slab': slab}


def detail(el, bars):
    """(svg, notes, linked bars) for a detailable element, else None."""
    fam = family(el['kind'])
    if not fam:
        return None
    linked = linked_bars(el, bars)
    svg, notes = DRAW[fam](el, linked)
    return svg, notes, linked


def detail_block(el, bars, compact=False):
    d = detail(el, bars)
    if not d:
        return ''
    svg, notes, linked = d
    fam = family(el['kind'])
    missing = {'footing': ('x', 'y', 'mesh', 'main'), 'column': ('main', 'ties'), 'beam': ('top', 'bottom', 'ties'), 'slab': ('main', 'dist')}[fam]
    have = set(linked)
    hint = ''
    if not have:
        sfx = {'footing': '-MESH (or -X and -Y)', 'column': '-MAIN and -TIES', 'beam': '-TOP, -BOT and -STIR', 'slab': '-MAIN and -DIST'}[fam]
        hint = (f'<p class="rd-warn">No bars linked yet — the sketch shows a TYPICAL arrangement only. Add bars in the BBS Studio named '
                f'{_e(el["mark"])}{_e(sfx)} to draw your real bar numbers and spacing.</p>')
    elif fam == 'footing' and not have & set(missing):
        hint = ''
    items = ''.join(f'<li>{_e(n)}</li>' for n in notes)
    return (f'<div class="rd-wrap">{svg}{legend()}{hint}<ul class="rd-notes">{items}</ul>'
            '<p class="rd-foot">Site-checking sketch of common practice — not to scale and not a design. The approved structural drawing '
            'and the engineer’s instructions always take priority.</p></div>')
