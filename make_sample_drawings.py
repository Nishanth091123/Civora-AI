"""Civora AI v3.7.0 - builds the two sample drawings in sample_drawings/ (PDF, PNG and DXF each):

  Civora_Sample_Estimate_Plan  - 12.0 m x 10.0 m 2BHK ground floor with a full notes block
                                 (sizes, walls, heights, door/window schedule, tiles) for
                                 Smart Estimate / Multi-drawing / material calculation.
  Civora_Sample_Vastu_Plan     - east-facing 3 x 3 house with room names in every zone and a
                                 North arrow, for the Vastu check (one deliberate mistake:
                                 a store room in the North-East corner).

    python make_sample_drawings.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'sample_drawings'

# ------------------------------------------------------------------ drawing specs (metres, y downwards, north up)
ESTIMATE = {
    'name': 'Civora_Sample_Estimate_Plan',
    'title': 'CIVORA AI SAMPLE ESTIMATE PLAN - GROUND FLOOR 2BHK',
    'size': (12.0, 10.0),
    'rooms': [  # name, x0, y0, x1, y1, label position (x, y), size text
        ('BEDROOM 1', 0, 0, 4.2, 4.5, (2.1, 2.0), '4.20 X 4.50 M'),
        ('LIVING', 4.2, 0, 12, 4.5, (8.1, 2.0), '7.80 X 4.50 M'),
        ('BEDROOM 2', 0, 4.5, 4.2, 10, (2.1, 5.6), '4.20 X 5.50 M'),
        ('DINING', 4.2, 4.5, 8.4, 7.5, (6.3, 5.6), '4.20 X 3.00 M'),
        ('KITCHEN', 8.4, 4.5, 12, 7.5, (10.2, 5.6), '3.60 X 3.00 M'),
        ('TOILET', 4.2, 7.5, 6.2, 10, (5.2, 8.4), '2.00 X 2.50 M'),
        ('BATHROOM', 6.2, 7.5, 8.4, 10, (7.3, 8.4), '2.20 X 2.50 M'),
        ('UTILITY', 8.4, 7.5, 12, 10, (10.2, 8.4), ''),
    ],
    'notes': [
        'OVERALL EXTERNAL SIZE 12.00 X 10.00 M',
        'GROSS FOOTPRINT 120.00 M2',
        'EXTERNAL WALL THICKNESS 230 MM',
        'INTERNAL WALL THICKNESS 115 MM',
        'INTERNAL WALL LENGTH 37.80 M',
        'WALL HEIGHT 3.00 M',
        'RCC SLAB THICKNESS 125 MM',
        'PLINTH HEIGHT 0.45 M',
        'PARAPET HEIGHT 0.90 M',
        'INTERNAL PLASTER 12 MM',
        'EXTERNAL PLASTER 15 MM',
        'DOOR D1 MAIN 1.05 X 2.10 M 1 NO',
        'DOOR D2 INTERNAL 0.90 X 2.10 M 3 NOS',
        'DOOR D3 INTERNAL TOILET 0.75 X 2.10 M 2 NOS',
        'WINDOW W1 1.50 X 1.20 M 5 NOS',
        'WINDOW W2 1.20 X 1.20 M 2 NOS',
        'VENTILATOR V1 0.60 X 0.45 M 2 NOS',
        'FLOOR TILE SIZE 600 X 600 MM',
        'KITCHEN WALL TILE 300 X 300 MM; HEIGHT 0.60 M',
        'BATHROOM WALL TILE 300 X 300 MM; HEIGHT 2.10 M',
        'ROOF WATERPROOFING 120.00 M2',
    ],
    'north': True,
}

VASTU = {
    'name': 'Civora_Sample_Vastu_Plan',
    'title': 'CIVORA AI SAMPLE VASTU PLAN - EAST FACING HOUSE',
    'size': (12.0, 12.0),
    'rooms': [
        ('BEDROOM 2', 0, 0, 4.0, 4.0, (2.0, 1.6), ''),
        ('TOILET', 0, 3.0, 1.8, 4.0, None, ''),
        ('LIVING', 4.0, 0, 8.0, 4.0, (6.0, 2.0), ''),
        ('POOJA', 8.0, 0, 10.0, 2.0, (9.0, 1.0), ''),
        ('STORE', 10.0, 0, 12.0, 2.0, (11.0, 1.0), ''),
        ('SIT OUT', 8.0, 2.0, 12.0, 4.0, (10.0, 3.0), ''),
        ('DINING', 0, 4.0, 4.0, 8.0, (2.0, 6.0), ''),
        ('PASSAGE', 4.0, 4.0, 8.0, 8.0, (6.0, 6.0), ''),
        ('CAR PARKING', 8.0, 4.0, 12.0, 8.0, (10.0, 6.0), ''),
        ('MASTER BEDROOM', 0, 8.0, 4.0, 12.0, (2.0, 10.0), ''),
        ('STAIRCASE', 4.0, 8.0, 8.0, 12.0, (6.0, 10.0), ''),
        ('KITCHEN', 8.0, 8.0, 12.0, 12.0, (10.0, 10.0), ''),
    ],
    'extra_labels': [('TOILET', 0.9, 3.5), ('MAIN ENTRANCE', 10.0, 4.8), ('SUMP', 11.0, 0.45),
                     ('SEPTIC TANK', 1.6, 0.5), ('OHT', 1.0, 11.4)],
    'notes': ['EAST FACING PLOT - ROAD ON EAST SIDE', 'ROOM NAMES ARE READ FOR THE VASTU CHECK',
              'NORTH ARROW POINTS TO THE TOP OF THE SHEET'],
    'north': True,
}


# ------------------------------------------------------------------ writers
def _walls(spec):
    """Unique wall segments (outer rectangle + room edges)."""
    segs = set()
    W, H = spec['size']
    for (x0, y0, x1, y1) in [(0, 0, W, H)] + [r[1:5] for r in spec['rooms']]:
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1))):
            segs.add(tuple(sorted((a, b))))
    return sorted(segs)


def _texts(spec):
    """(text, x, y, size) in metres; notes go to the right of the plan."""
    W, H = spec['size']
    out = [(spec['title'], 0, -1.6, 0.42)]
    for name, *_r, pos, size in spec['rooms']:
        if pos:
            out.append((name, pos[0], pos[1], 0.27))
            if size:
                out.append((size, pos[0], pos[1] + 0.55, 0.20))
    for t, x, y in spec.get('extra_labels', []):
        out.append((t, x, y, 0.24))
    for i, n in enumerate(spec['notes']):          # notes block BELOW the plan, one column (OCR reads it line by line)
        out.append((n, 0.0, H + 1.2 + i * 0.6, 0.24))
    return out


def write_png(spec, path, ppm=110):
    from PIL import Image, ImageDraw, ImageFont
    W, H = spec['size']
    margin = 1.0
    notes_w = 3.0
    img = Image.new('RGB', (int((max(W, 14.5) + notes_w + 2 * margin) * ppm), int((H + 2 * margin + 2.2 + 1.5 + 0.6 * len(spec['notes'])) * ppm)), 'white')
    d = ImageDraw.Draw(img)
    ox, oy = margin * ppm, (margin + 2.2) * ppm
    P = lambda x, y: (ox + x * ppm, oy + y * ppm)
    for a, b in _walls(spec):
        outer = (a[0] == b[0] and a[0] in (0, W)) or (a[1] == b[1] and a[1] in (0, H))
        d.line([P(*a), P(*b)], fill='black', width=int(0.23 * ppm) if outer else 7)
    font = lambda s: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', int(s * ppm))
    for t, x, y, s in _texts(spec):
        f = font(s)
        if x <= W and y >= -0.5 and t not in spec['notes']:
            w = d.textlength(t, font=f)
            d.text((P(x, y)[0] - w / 2, P(x, y)[1] - s * ppm / 2), t, fill='black', font=f)
        else:
            d.text(P(x, y), t, fill='black', font=f)
    if spec.get('north'):                      # North arrow at the top right of the plan
        cx, cy = P(W + 1.5, -1.2)
        d.polygon([(cx, cy - 55), (cx - 22, cy + 25), (cx, cy + 10), (cx + 22, cy + 25)], fill='black')
        d.text((cx - 12, cy - 100), 'N', fill='black', font=font(0.4))
    img.save(path)


def write_pdf(spec, path):
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.pdfgen import canvas
    W, H = spec['size']
    pw, ph = landscape(A3)
    sc = min((pw - 80) / (max(W, 14.5) + 3), (ph - 120) / (H + 3 + 0.6 * len(spec['notes'])))
    ox, oy = 40, ph - 90
    P = lambda x, y: (ox + x * sc, oy - y * sc)
    c = canvas.Canvas(str(path), pagesize=landscape(A3))
    c.setTitle(spec['title'])
    for a, b in _walls(spec):
        outer = (a[0] == b[0] and a[0] in (0, W)) or (a[1] == b[1] and a[1] in (0, H))
        c.setLineWidth(4 if outer else 2)
        c.line(*P(*a), *P(*b))
    for t, x, y, s in _texts(spec):
        c.setFont('Helvetica-Bold', max(s * sc * 0.8, 7))
        px, py = P(x, y)
        if x <= W and y >= -0.5 and t not in spec['notes']:
            c.drawCentredString(px, py - 4, t)
        else:
            c.drawString(px, py, t)
    if spec.get('north'):
        cx, cy = P(W + 1.5, -1.0)
        pth = c.beginPath(); pth.moveTo(cx, cy + 22); pth.lineTo(cx - 9, cy - 10); pth.lineTo(cx, cy - 4); pth.lineTo(cx + 9, cy - 10); pth.close()
        c.drawPath(pth, fill=1)
        c.setFont('Helvetica-Bold', 14); c.drawCentredString(cx, cy + 28, 'N')
    c.showPage(); c.save()


def write_dxf(spec, path):
    """Plain ASCII DXF (R12): walls on layer WALL, labels as TEXT. Y is flipped so North stays up."""
    W, H = spec['size']
    L = ['0', 'SECTION', '2', 'HEADER', '9', '$ACADVER', '1', 'AC1009', '9', '$INSUNITS', '70', '6', '0', 'ENDSEC',
         '0', 'SECTION', '2', 'ENTITIES']
    for a, b in _walls(spec):
        L += ['0', 'LINE', '8', 'WALL', '10', f'{a[0]:.3f}', '20', f'{H - a[1]:.3f}', '30', '0', '11', f'{b[0]:.3f}', '21', f'{H - b[1]:.3f}', '31', '0']
    for t, x, y, s in _texts(spec):
        layer = 'NOTES' if t in spec['notes'] or y < 0 else 'ROOMS'
        centred = layer == 'ROOMS'
        L += ['0', 'TEXT', '8', layer, '10', f'{x:.3f}', '20', f'{H - y:.3f}', '30', '0', '40', f'{s:.3f}', '1', t]
        if centred:
            L += ['72', '1', '11', f'{x:.3f}', '21', f'{H - y:.3f}', '31', '0']
    if spec.get('north'):
        L += ['0', 'TEXT', '8', 'NORTH', '10', f'{W + 1.5:.3f}', '20', f'{H + 1.6:.3f}', '30', '0', '40', '0.5', '1', 'N']
        L += ['0', 'LINE', '8', 'NORTH', '10', f'{W + 1.6:.3f}', '20', f'{H + 0.4:.3f}', '30', '0', '11', f'{W + 1.6:.3f}', '21', f'{H + 1.5:.3f}', '31', '0']
    L += ['0', 'ENDSEC', '0', 'EOF']
    Path(path).write_text('\n'.join(L) + '\n', encoding='ascii')


def main():
    OUT.mkdir(exist_ok=True)
    for spec in (ESTIMATE, VASTU):
        base = OUT / spec['name']
        write_png(spec, base.with_suffix('.png'))
        write_pdf(spec, base.with_suffix('.pdf'))
        write_dxf(spec, base.with_suffix('.dxf'))
        print('made', base.name, '(.png .pdf .dxf)')


if __name__ == '__main__':
    main()
