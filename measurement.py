"""Civora v2.4.1 measurement basis for rectangular wall layouts.

Pure functions, no web code. Every result carries the basis name and the formula
so reports can show exactly how a quantity was measured.

Convention (outer plan dimensions L x W, external wall thickness t):
  External face : perimeter = 2(L + W)              - outer face of the wall
  Centreline    : perimeter = 2(L + W) - 4t         - usual basis for masonry volume
  Internal face : perimeter = 2(L + W) - 8t         - inner face (internal plaster/paint)

The choice of basis is the user's; no basis is "correct" for every item.
External plaster is always measured on the external face because that is the
surface physically plastered.
"""
import math

BASES = {
    'external': 'External face',
    'centreline': 'Centreline',
    'internal': 'Internal face',
}
DEFAULT_BASIS = 'external'          # keeps every pre-v2.4.1 result unchanged
_OFFSET = {'external': 0, 'centreline': 1, 'internal': 2}   # multiples of t removed per dimension


def _positive(value, label):
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label}: enter a number')
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f'{label}: must be greater than zero')
    return x


def normalise_basis(basis):
    b = str(basis or DEFAULT_BASIS).strip().lower()
    if b not in BASES:
        raise ValueError('Measurement basis must be external, centreline or internal')
    return b


def rectangle_perimeter(length, width, thickness, basis=DEFAULT_BASIS):
    """Perimeter of a rectangular outer wall on the chosen basis."""
    b = normalise_basis(basis)
    L = _positive(length, 'Overall length (m)')
    W = _positive(width, 'Overall width (m)')
    t = _positive(thickness, 'External wall thickness (m)')
    k = _OFFSET[b]
    l, w = L - k * t, W - k * t
    if l <= 0 or w <= 0:
        raise ValueError('Wall thickness is too large for the overall dimensions')
    formulas = {
        'external': f'2 × ({L:g} + {W:g})',
        'centreline': f'2 × (({L:g} − {t:g}) + ({W:g} − {t:g}))',
        'internal': f'2 × (({L:g} − 2×{t:g}) + ({W:g} − 2×{t:g}))',
    }
    return {'basis': b, 'basis_label': BASES[b], 'length': l, 'width': w,
            'perimeter': 2 * (l + w), 'formula': formulas[b] + f' = {2 * (l + w):.3f} m'}


def wall_faces(length, width, thickness, height, opening_area=0.0, basis=DEFAULT_BASIS):
    """Gross and net face area of the rectangular outer wall on the chosen basis."""
    p = rectangle_perimeter(length, width, thickness, basis)
    H = _positive(height, 'Wall height (m)')
    try:
        op = float(opening_area or 0)
    except (TypeError, ValueError):
        raise ValueError('Opening area: enter a number')
    if not math.isfinite(op) or op < 0:
        raise ValueError('Opening area cannot be negative')
    gross = p['perimeter'] * H
    if op > gross:
        raise ValueError('Opening deduction exceeds the gross wall face')
    return {**p, 'height': H, 'gross': gross, 'openings': op, 'net': gross - op,
            'face_formula': f"{p['perimeter']:.3f} m × {H:g} m = {gross:.3f} m²; − openings {op:.3f} m² = {gross - op:.3f} m²"}


def grid_partition_length(length, width, thickness, basis=DEFAULT_BASIS, columns=3, rows=2):
    """Provisional partition length for a regular columns × rows room grid.

    Partitions run across the building between the external walls. On the external
    basis they are taken to the outer face (pre-v2.4.1 behaviour: 2W + L for 3 × 2);
    on centreline / internal they stop at the external wall centreline / inner face.
    """
    b = normalise_basis(basis)
    L = _positive(length, 'Overall length (m)')
    W = _positive(width, 'Overall width (m)')
    t = _positive(thickness, 'External wall thickness (m)')
    k = _OFFSET[b]
    across_w, across_l = W - k * t, L - k * t
    if across_w <= 0 or across_l <= 0:
        raise ValueError('Wall thickness is too large for the overall dimensions')
    total = (columns - 1) * across_w + (rows - 1) * across_l
    return {'basis': b, 'length': total,
            'formula': f'{columns - 1} × {across_w:g} + {rows - 1} × {across_l:g} = {total:.3f} m (provisional {columns}×{rows} grid)'}
