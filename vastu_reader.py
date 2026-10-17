"""Civora AI v3.7.0 - find rooms and where they are on an uploaded plan, for the Vastu check.

1. Read every text label WITH its position (DXF text, PDF words, OCR boxes on images).
2. Keep short labels that name a room / item (KITCHEN, POOJA, MASTER BED, TOILET, STAIR,
   SUMP, PARKING ...). Notes and schedules ("KITCHEN WALL TILE 300 X 300") are ignored.
3. The building extent is taken from the wall lines (DXF layer WALL) when available, else from
   the spread of the room labels themselves.
4. With the side of the sheet that points North (asked from the user), every room gets one of
   9 zones: NW N NE / W C E / SW S SE.
"""
import re
from pathlib import Path

ROOM_PATTERNS = [   # (item key, regex) - order matters: master bedroom before bedroom
    ('master', r'\b(MASTER\s*BED(ROOM)?|M\.?\s*BED(ROOM)?|MBR)\b'),
    ('pooja', r'\b(POOJA|PUJA|PRAYER|MANDIR|SHRINE)\b'),
    ('kitchen', r'\b(KITCHEN|KIT\.)\b'),
    ('toilet', r'\b(TOILET|BATH(ROOM)?|W\.?C\.?|T\s*&\s*B|WASH\s*ROOM)\b'),
    ('stair', r'\b(STAIR(CASE|S)?|STAIR\s*CASE)\b'),
    ('sump', r'\b(SUMP|BORE\s*WELL|BOREWELL|U\.?G\.?\s*TANK|UNDERGROUND\s*TANK)\b'),
    ('ohtank', r'\b(OHT|O\.H\.T|OVERHEAD\s*TANK)\b'),
    ('septic', r'\bSEPTIC\b'),
    ('parking', r'\b(PARKING|CAR\s*PARK|PORTICO|GARAGE)\b'),
    ('study', r'\b(STUDY|OFFICE)\b'),
    ('store', r'\b(STORE|STORAGE)\b'),
    ('dining', r'\bDINING\b'),
    ('living', r'\b(LIVING|HALL|LOUNGE|DRAWING\s*ROOM|SIT\s*OUT)\b'),
    ('bedroom', r'\b(BED\s*ROOM|BEDROOM|BED|CHILDREN|KIDS|GUEST\s*ROOM)\b'),
    ('entrance', r'\b(MAIN\s*(DOOR|ENTRANCE|ENTRY)|ENTRANCE|ENTRY)\b'),
]
NOT_A_ROOM = re.compile(r'\b(TILE|TILES|WALL|PLASTER|PAINT|SCHEDULE|NOTE|NOTES|THICK|THICKNESS|MM|SIZE|DADO|HEIGHT|'
                        r'AREA|LEVEL|SLAB|BEAM|COLUMN|FOOTING|WINDOW|VENT|SKIRTING|FLOOR\s*TILE|SPECIFICATION|LEGEND)\b')
NORTH_SIDES = {'up': 'Top of the drawing', 'right': 'Right side', 'down': 'Bottom', 'left': 'Left side'}
GRID = [['NW', 'N', 'NE'], ['W', 'C', 'E'], ['SW', 'S', 'SE']]


def _norm(s):
    return re.sub(r'\s+', ' ', str(s).replace('×', 'x')).strip().upper()


# ------------------------------------------------------------------ text with positions
def _lines_from_words(words):
    """words: (text, x0, y0, x1, y1, group) -> lines [(text, cx, cy)] grouped by `group` (same text line)."""
    groups = {}
    for t, x0, y0, x1, y1, g in words:
        if str(t).strip():
            groups.setdefault(g, []).append((x0, y0, x1, y1, str(t)))
    out = []
    for ws in groups.values():
        ws.sort()
        # split a "line" where there is a big gap (two room names on one row of the sheet)
        chunk = [ws[0]]
        h = max(1e-6, sum(w[3] - w[1] for w in ws) / len(ws))
        for w in ws[1:]:
            if w[0] - chunk[-1][2] > 2.5 * h:
                out.append(chunk); chunk = [w]
            else:
                chunk.append(w)
        out.append(chunk)
    res = []
    for ch in out if groups else []:
        text = ' '.join(w[4] for w in ch)
        cx = (min(w[0] for w in ch) + max(w[2] for w in ch)) / 2
        cy = (min(w[1] for w in ch) + max(w[3] for w in ch)) / 2
        res.append((text, cx, cy))
    return res


def text_items(path, page=0):
    """[(text, x, y)] with y growing DOWNWARDS, the sheet extent (x0, y0, x1, y1) or None, and the method."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == '.dxf':
        import ezdxf
        doc = ezdxf.readfile(str(path))
        items, wall_pts, all_pts = [], [], []
        for e in doc.modelspace():
            t = e.dxftype()
            try:
                if t == 'TEXT':
                    p = e.dxf.insert; items.append((str(e.dxf.text), float(p.x), -float(p.y)))
                elif t == 'MTEXT':
                    p = e.dxf.insert; items.append((e.plain_text().replace('\n', ' '), float(p.x), -float(p.y)))
                elif t == 'LINE':
                    pts = [(float(e.dxf.start.x), -float(e.dxf.start.y)), (float(e.dxf.end.x), -float(e.dxf.end.y))]
                    all_pts += pts
                    if 'WALL' in str(e.dxf.layer).upper():
                        wall_pts += pts
                elif t == 'LWPOLYLINE':
                    pts = [(float(x), -float(y)) for x, y, *_ in e.get_points()]
                    all_pts += pts
                    if 'WALL' in str(e.dxf.layer).upper():
                        wall_pts += pts
            except (AttributeError, ValueError, TypeError):
                continue
        box = None
        if wall_pts:
            xs, ys = [p[0] for p in wall_pts], [p[1] for p in wall_pts]
            box = (min(xs), min(ys), max(xs), max(ys))
        return items, box, 'DXF text'
    if ext == '.pdf':
        import fitz
        with fitz.open(str(path)) as d:
            if not 0 <= page < len(d):
                raise ValueError('Invalid PDF page')
            pg = d[page]
            words = pg.get_text('words')
            if len(words) >= 5:
                lines = _lines_from_words([(w[4], w[0], w[1], w[2], w[3], (w[5], w[6])) for w in words])
                return lines, None, 'PDF text'
            pix = pg.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            from PIL import Image
            img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            return _ocr(img) + ('PDF OCR',)
    if ext in ('.png', '.jpg', '.jpeg'):
        from PIL import Image
        return _ocr(Image.open(path).convert('RGB')) + ('Image OCR',)
    raise ValueError('Upload a PDF, DXF, PNG or JPG drawing')


def _without_lines(img):
    """Remove long wall / grid lines so OCR sees the room names (walls touching text hide words)."""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        g = np.array(img.convert('L'))
        bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        k = max(40, min(g.shape) // 30)
        h = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
        v = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, k)))
        clean = 255 - cv2.subtract(bw, cv2.dilate(h | v, np.ones((3, 3), np.uint8)))
        return Image.fromarray(clean)
    except Exception:
        return img


def _ocr(img):
    import pytesseract
    d = pytesseract.image_to_data(_without_lines(img), output_type=pytesseract.Output.DICT, config='--psm 11')
    words = [(d['text'][i], d['left'][i], d['top'][i], d['left'][i] + d['width'][i], d['top'][i] + d['height'][i],
              (d['block_num'][i], d['par_num'][i], d['line_num'][i]))
             for i in range(len(d['text'])) if str(d['text'][i]).strip() and float(d['conf'][i]) > 30]
    return _lines_from_words(words), None


# ------------------------------------------------------------------ rooms and zones (pure, unit tested)
def classify(text):
    """Item key for a room label, or None. Notes / schedule lines are rejected."""
    t = _norm(text)
    if not t or len(t) > 32 or len(t.split()) > 5 or NOT_A_ROOM.search(t):
        return None
    for key, pat in ROOM_PATTERNS:
        if re.search(pat, t):
            return key
    return None


def compass_position(u, v, north):
    """(east-ness, south-ness) 0..1 from sheet position (u right, v down) and the side pointing North."""
    if north == 'up':
        return u, v
    if north == 'down':
        return 1 - u, 1 - v
    if north == 'right':
        return v, 1 - u
    if north == 'left':
        return 1 - v, u
    raise ValueError('Tell Civora which side of the drawing is North')


def zone_of(e, s):
    col = 0 if e < 1 / 3 else (1 if e <= 2 / 3 else 2)
    row = 0 if s < 1 / 3 else (1 if s <= 2 / 3 else 2)
    return GRID[row][col]


def find_rooms(items, box=None):
    """[(key, label, x, y)] for the room labels, and the extent used (x0, y0, x1, y1)."""
    rooms = [(classify(t), _norm(t), x, y) for t, x, y in items]
    rooms = [r for r in rooms if r[0]]
    if box:
        x0, y0, x1, y1 = box
        rooms = [r for r in rooms if x0 <= r[2] <= x1 and y0 <= r[3] <= y1]   # labels outside the building are notes
    if not rooms:
        return [], box
    if not box:
        xs, ys = [r[2] for r in rooms], [r[3] for r in rooms]
        px, py = (max(xs) - min(xs)) * 0.2 or 1.0, (max(ys) - min(ys)) * 0.2 or 1.0
        box = (min(xs) - px, min(ys) - py, max(xs) + px, max(ys) + py)
    return rooms, box


def locate(rooms, box, north):
    """[{key, label, zone}] for every room label found."""
    x0, y0, x1, y1 = box
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    out = []
    for key, label, x, y in rooms:
        e, s = compass_position((x - x0) / w, (y - y0) / h, north)
        out.append({'key': key, 'label': label, 'zone': zone_of(e, s)})
    return out


def read_plan(path, north, page=0):
    """Rooms with zones for one drawing. Returns dict(rooms, method, found)."""
    items, box, method = text_items(path, page)
    rooms, box = find_rooms(items, box)
    return {'rooms': locate(rooms, box, north) if rooms else [], 'method': method, 'labels_read': len(items)}
