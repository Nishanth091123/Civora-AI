"""v2.4.1 measurement-basis tests. Expected values are hand calculations for the
sample plan: 12.00 × 9.00 m outer, t = 0.23 m, H = 3.00 m, external openings 13.86 m²."""
import unittest
from measurement import rectangle_perimeter, wall_faces, grid_partition_length, normalise_basis

L, W, T, H, OPEN = 12, 9, .23, 3, 13.86


class BasisGeometry(unittest.TestCase):
    def test_external_face(self):
        r = wall_faces(L, W, T, H, OPEN, 'external')
        self.assertAlmostEqual(r['perimeter'], 42.00)          # 2(12+9)
        self.assertAlmostEqual(r['gross'], 126.00)
        self.assertAlmostEqual(r['net'], 112.14)

    def test_centreline(self):
        r = wall_faces(L, W, T, H, OPEN, 'centreline')
        self.assertAlmostEqual(r['perimeter'], 41.08)          # 2(11.77+8.77)
        self.assertAlmostEqual(r['gross'], 123.24)
        self.assertAlmostEqual(r['net'], 109.38)

    def test_internal_face(self):
        r = wall_faces(L, W, T, H, OPEN, 'internal')
        self.assertAlmostEqual(r['perimeter'], 40.16)          # 2(11.54+8.54)
        self.assertAlmostEqual(r['gross'], 120.48)
        self.assertAlmostEqual(r['net'], 106.62)

    def test_formula_is_reported(self):
        r = wall_faces(L, W, T, H, OPEN, 'centreline')
        self.assertEqual(r['basis_label'], 'Centreline')
        self.assertIn('41.080', r['formula'])
        self.assertIn('109.380', r['face_formula'])

    def test_default_is_external(self):
        self.assertEqual(normalise_basis(None), 'external')
        self.assertAlmostEqual(rectangle_perimeter(L, W, T)['perimeter'], 42)

    def test_grid_partitions(self):
        self.assertAlmostEqual(grid_partition_length(L, W, T, 'external')['length'], 30.00)   # 2×9 + 12 (unchanged)
        self.assertAlmostEqual(grid_partition_length(L, W, T, 'centreline')['length'], 29.31) # 2×8.77 + 11.77
        self.assertAlmostEqual(grid_partition_length(L, W, T, 'internal')['length'], 28.62)   # 2×8.54 + 11.54

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError): normalise_basis('outer')
        with self.assertRaises(ValueError): rectangle_perimeter(1, 1, .6, 'internal')
        with self.assertRaises(ValueError): wall_faces(L, W, T, H, 500)
        with self.assertRaises(ValueError): wall_faces(L, W, T, H, -1)
        with self.assertRaises(ValueError): rectangle_perimeter(0, W, T)



class IntelligenceWithBasis(unittest.TestCase):
    """calculate() from Drawing Intelligence, using the real takeoff engine."""
    def run_calc(self, basis):
        from intelligent_recognition import calculate
        from engineering import takeoff
        v = {'overall_length': L, 'overall_width': W, 'height': H, 'wall_thickness': T,
             'external_opening_area': OPEN, 'external_plaster_thickness': .015, 'waste': 5,
             'measurement_basis': basis}
        return calculate(v, set(), set(), {'regions': [], 'lines': []}, takeoff)

    def test_external_default_unchanged(self):
        r = self.run_calc(None)
        b = {k: v for k, v, _ in r['breakdown']}
        self.assertEqual(r['measurement_basis'], 'external')
        self.assertAlmostEqual(b['External wall net face (indicative)'], 112.14)
        self.assertIn('External masonry – indicative (net openings)', [x[0] for x in r['rows']])

    def test_centreline_masonry_external_plaster(self):
        r = self.run_calc('centreline')
        b = {k: v for k, v, _ in r['breakdown']}
        rows = {name: area for name, area, _ in r['rows']}
        self.assertAlmostEqual(b['Masonry net face – Centreline'], 109.38)
        self.assertAlmostEqual(rows['External masonry – indicative (net openings, centreline)'], 109.38)
        self.assertAlmostEqual(rows['External plaster – indicative (outer face)'], 112.14)   # plaster stays on outer face
        self.assertTrue(any('Centreline' in n and '41.080' in n for n in r['notes']))

    def test_centreline_uses_fewer_bricks(self):
        def bricks(r):
            return next(i['quantity'] for n, _, items in r['rows'] if n.startswith('External masonry') for i in items if i['material'] == 'Bricks')
        self.assertLess(bricks(self.run_calc('centreline')), bricks(self.run_calc('external')))


if __name__ == '__main__':
    unittest.main()
