"""v3.7.0 calculation audit: every main formula checked against a hand calculation
(standard Indian site practice). Numbers in comments are worked out by hand."""
import importlib.util
import unittest

from engineering import takeoff
import structural_v210 as s210

HAVE_CALC = importlib.util.find_spec('fastapi') is not None


def q(res, name, unit=None):
    return sum(i['quantity'] for i in res['items'] if i['material'] == name and (unit is None or i['unit'] == unit))


class TakeoffHandChecks(unittest.TestCase):
    def test_brickwork_one_cubic_metre(self):
        # 190x90x90 brick + 10 mm joint -> module 0.2x0.1x0.1 = 0.002 m3 -> 500 bricks
        r = takeoff('brickwork', 1, 1, 1, waste=0)
        self.assertEqual(q(r, 'Bricks'), 500)
        # wet mortar = 1 - 500 x 0.001539 = 0.2305 ; dry x1.33 = 0.30657 ; 1:6 cement = 0.30657/7 x 1440/50 = 1.261 bags
        self.assertAlmostEqual(q(r, 'Cement'), 1.261, places=2)
        self.assertAlmostEqual(q(r, 'Sand'), 0.30657 * 6 / 7, places=3)

    def test_pcc_148_per_cubic_metre(self):
        # dry 1.54 ; cement 1.54/13 x 28.8 = 3.41 bags ; sand 0.474 ; aggregate 0.948
        r = takeoff('pcc', 1, 1, 1, waste=0, pcc_ratio='1:4:8')
        self.assertAlmostEqual(q(r, 'Cement'), 3.412, places=2)
        self.assertAlmostEqual(q(r, 'Sand'), 0.4738, places=3)
        self.assertAlmostEqual(q(r, 'Coarse aggregate'), 0.9477, places=3)

    def test_m20_nominal_per_cubic_metre(self):
        # dry 1.54 ; cement 1.54/5.5 x 1440 = 403.2 kg = 8.06 bags -> 9 whole bags ordered
        r = takeoff('rcc', 1, 1, 1, waste=0, rcc_mode='site', rcc_site_method='nominal', rcc_nominal_ratio='1:1.5:3')
        self.assertAlmostEqual(q(r, 'Cement', 'kg'), 403.2, places=1)
        self.assertEqual(q(r, 'Cement 50 kg bags'), 9)
        self.assertAlmostEqual(q(r, 'M-sand'), 0.42, places=3)
        self.assertAlmostEqual(q(r, 'Coarse aggregate'), 0.84, places=3)

    def test_plaster_12mm_100_m2(self):
        # wet 1.2 m3 ; dry x1.33 = 1.596 ; 1:4 -> cement 1.596/5 x 28.8 = 9.19 bags ; sand 1.277 m3
        r = takeoff('plaster', 100, 1, 0.012, waste=0, plaster_ratio='1:4')
        self.assertAlmostEqual(q(r, 'Cement'), 9.193, places=2)
        self.assertAlmostEqual(q(r, 'Sand'), 1.2768, places=3)

    def test_tiles_and_paint(self):
        r = takeoff('flooring', 100, 1, 0.01, waste=0, tile_length=0.6, tile_width=0.6)
        self.assertEqual(q(r, 'Tiles'), 278)                    # 100 / 0.36 = 277.8 -> 278
        p = takeoff('painting', 100, 1, 0.001, waste=0, coats=2, paint_coverage=10)
        self.assertAlmostEqual(q(p, 'Paint'), 20)              # 100 m2 x 2 coats / 10 m2 per litre
        self.assertAlmostEqual(q(p, 'Primer'), 10)

    def test_steel_unit_weight(self):
        r = takeoff('steel', 1, 1, 1, waste=0, steel_diameter_mm=12, steel_total_length_m=100)
        self.assertAlmostEqual(q(r, 'Reinforcement steel'), 88.889, places=2)   # 12²/162 = 0.8889 kg/m

    def test_bbs_bends_shorten_the_bar(self):
        # 10 bars, 3.0 m along the shape, two 90° bends of a 12 mm bar (2d each = 0.048 m), no hooks, no laps
        r = s210.bar_schedule(12, 10, 3.0, bend_allowance=0.048, hook_allowance=0, lap_allowance=0)
        self.assertAlmostEqual(r['cut_length_m'], 2.952)
        self.assertAlmostEqual(r['steel_kg'], 10 * 2.952 * 144 / 162, places=3)
        with self.assertRaises(ValueError):
            s210.bar_schedule(12, 1, 0.1, bend_allowance=0.2)


@unittest.skipUnless(HAVE_CALC, 'needs fastapi (calculation module imports it)')
class SmartEstimateHandChecks(unittest.TestCase):
    def setUp(self):
        import smart_estimate_v260 as se
        from test_v260_smart import plan_schedule
        self.se, self.sch = se, plan_schedule()
        self.inp = se.build_inputs(self.sch, 1162)

    def rows(self, r):
        return {k: v for k, v, in ((label, items) for label, _, items in r['rows'])}

    def test_carpet_area_used_for_floor_and_ceiling(self):
        se = self.se
        r = se.estimate(self.inp, se.default_options(), takeoff, self.sch)
        # (12 - 2x0.23) x (9 - 2x0.23) - 29.31 x 0.115 = 98.5516 - 3.37065 = 95.18095 m2
        carpet = dict((m, v) for m, v, _ in r['breakdown'])['Carpet area inside walls (tiles, ceiling) per floor']
        self.assertAlmostEqual(carpet, 95.18095, places=4)
        areas = {label: area for label, area, _ in r['rows']}
        self.assertAlmostEqual(areas['Floor tiles'], carpet)
        self.assertAlmostEqual(areas['Ceiling plaster'], carpet)
        self.assertNotIn('Floor screed', areas)
        self.assertNotIn('Tile adhesive', [i['material'] for i in self.rows(r)['Floor tiles']])

    def test_masonry_less_beams_columns_lintels(self):
        se = self.se
        r = se.estimate(self.inp, se.default_options(), takeoff, self.sch)
        ext = next((label, area) for label, area, _ in r['rows'] if label.startswith('External masonry'))
        # centreline face 109.38 - [41.08 x 0.15 beam drop + 12 wall columns x 0.30 x 2.85 + 14.1 m lintel x 0.15] = 90.843
        self.assertAlmostEqual(ext[1], 109.38 - (41.08 * 0.15 + 12 * 0.30 * 2.85 + 14.1 * 0.15), places=3)
        # without the RCC frame only lintels come off
        off = se.estimate(self.inp, dict(se.default_options(), frame=False), takeoff, self.sch)
        ext_off = next(area for label, area, _ in off['rows'] if label.startswith('External masonry'))
        self.assertAlmostEqual(ext_off, 109.38 - 14.1 * 0.15, places=3)

    def test_beams_below_slab_and_columns_to_plinth(self):
        se = self.se
        r = se.estimate(self.inp, se.default_options(), takeoff, self.sch)
        b = dict((m, v) for m, v, _ in r['breakdown'])
        # beam length 2(12+9) - 4x0.23 + 29.31 = 70.39 m ; plinth 70.39x0.23x0.30 ; roof beam below 150 mm slab 70.39x0.23x0.15
        self.assertAlmostEqual(b['RCC beams (plinth + floors)'], 70.39 * 0.23 * 0.30 + 70.39 * 0.23 * 0.15, places=4)
        # 16 columns 0.23x0.30: below ground (1.5-0.3-0.1) + above (3.0 + 0.15 slab + 0.45 plinth)
        self.assertAlmostEqual(b['RCC columns'], 16 * 0.069 * (1.1 + 3.15 + 0.45), places=4)

    def test_parapet_plinth_and_staircase(self):
        se = self.se
        two = dict(self.inp); two['floors'] = {'value': 2, 'source': 'user', 'note': ''}
        r = se.estimate(two, se.default_options(), takeoff, self.sch)
        labels = [label for label, _, _ in r['rows']]
        self.assertEqual(sum(1 for x in labels if x.startswith('Parapet wall')), 1)              # top roof only
        self.assertEqual(sum(1 for x in labels if x.startswith('Plinth filling')), 1)            # ground floor only
        self.assertTrue(any(x.startswith('RCC staircase') for x in labels))
        par = next(area for label, area, _ in r['rows'] if label.startswith('Parapet wall'))
        self.assertAlmostEqual(par, (2 * 21 - 4 * 0.115) * 0.9, places=4)

    def test_wall_tiles_priced_separately(self):
        import rates_v260
        self.assertEqual(rates_v260.rate_key_for({'material': 'Wall tiles', 'unit': 'nos'}), 'wall_tile')
        self.assertEqual(rates_v260.rate_key_for({'material': 'Tiles', 'unit': 'nos'}), 'tile')

    def test_thumb_rules_for_a_1000_sqft_house(self):
        import quick_v280 as qk
        inp, opts, r = qk.quick_estimate(1000, 1, takeoff)
        agg = qk.material_totals(r['rows'])
        steel = agg[('Steel planning allowance (not BBS)', 'kg')]
        self.assertTrue(3000 < steel < 4500, steel)            # 3 - 4.5 kg per sq.ft
        bags = agg[('Cement', 'bags (50 kg)')]
        rmc = agg.get(('Ready-mix concrete (RMC)', 'm³'), 0)
        total_bags = bags + rmc * 8                             # RMC ~8 bags per m³
        self.assertTrue(300 < total_bags < 500, total_bags)    # ~0.4 bag per sq.ft


if __name__ == '__main__':
    unittest.main()
