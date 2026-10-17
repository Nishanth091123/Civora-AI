"""v3.7.0: the sample drawings in sample_drawings/ must read correctly (estimate + Vastu)."""
import importlib.util
import shutil
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = HERE / 'sample_drawings'
HAVE = {'png': shutil.which('tesseract') is not None, 'pdf': importlib.util.find_spec('fitz') is not None,
        'dxf': importlib.util.find_spec('ezdxf') is not None}
HAVE_CALC = importlib.util.find_spec('fastapi') is not None


class EstimateSample(unittest.TestCase):
    def check(self, ext):
        if not HAVE[ext]:
            self.skipTest(f'{ext} reader not installed')
        from drawing_schedule import extract
        s = extract(S / f'Civora_Sample_Estimate_Plan.{ext}')
        ev = {k: v['value'] for k, v in s['evidence'].items()}
        self.assertEqual((ev['overall_length'], ev['overall_width']), (12.0, 10.0))
        self.assertAlmostEqual(ev['internal_wall_length'], 37.8)
        self.assertAlmostEqual(ev['slab_thickness'], 0.125)
        self.assertAlmostEqual(ev['plinth_height'], 0.45)
        ops = {o['label']: (o['width'], o['height'], o['count']) for o in s['openings']}
        self.assertEqual(ops['DOOR D1'], (1.05, 2.1, 1))
        self.assertEqual(ops['WINDOW W1'], (1.5, 1.2, 5))
        self.assertEqual(len(ops), 6)
        self.assertEqual({r['name'] for r in s['rooms']} >= {'KITCHEN', 'TOILET', 'BATHROOM'}, True)
        if HAVE_CALC:
            import smart_estimate_v260 as se
            inp = se.build_inputs(s, 1291)
            self.assertAlmostEqual(inp['ext_open']['value'], 1.05 * 2.1 + 5 * 1.8 + 2 * 1.44 + 2 * 0.27)
            self.assertAlmostEqual(inp['int_open']['value'], 3 * 1.89 + 2 * 1.575)
            self.assertAlmostEqual(inp['wall_tile']['value'], 42.78, places=2)   # kitchen 7.92 + toilet 17.01 + bath 17.85
            self.assertEqual([k for k, v in inp.items() if v['source'] == 'typical' and se.FIELD[k][4] != 'frame'], ['floors'])

    def test_png(self):
        self.check('png')

    def test_pdf(self):
        self.check('pdf')

    def test_dxf(self):
        self.check('dxf')


class VastuSample(unittest.TestCase):
    def check(self, ext):
        if not HAVE[ext]:
            self.skipTest(f'{ext} reader not installed')
        import vastu_reader as vr
        import vastu_v360 as vv
        rooms = vr.read_plan(S / f'Civora_Sample_Vastu_Plan.{ext}', 'up')['rooms']
        z = {r['label']: r['zone'] for r in rooms}
        for label, zone in (('POOJA', 'NE'), ('KITCHEN', 'SE'), ('MASTER BEDROOM', 'SW'), ('STAIRCASE', 'S'),
                            ('LIVING', 'N'), ('STORE', 'NE'), ('CAR PARKING', 'E')):
            self.assertEqual(z.get(label), zone, label)
        ev = vv.evaluate_list('E', rooms)
        self.assertEqual([i['label'] for i in ev['items'] if i['status'] == 'avoid'], ['STORE'])   # the deliberate mistake

    def test_png(self):
        self.check('png')

    def test_pdf(self):
        self.check('pdf')

    def test_dxf(self):
        self.check('dxf')


class ReaderUnits(unittest.TestCase):
    def test_north_rotation(self):
        import vastu_reader as vr
        # a room in the top-right corner of the sheet
        self.assertEqual(vr.zone_of(*vr.compass_position(0.9, 0.1, 'up')), 'NE')
        self.assertEqual(vr.zone_of(*vr.compass_position(0.9, 0.1, 'right')), 'NW')   # right = North -> top is West
        self.assertEqual(vr.zone_of(*vr.compass_position(0.9, 0.1, 'down')), 'SW')
        self.assertEqual(vr.zone_of(*vr.compass_position(0.9, 0.1, 'left')), 'SE')

    def test_notes_are_not_rooms(self):
        import vastu_reader as vr
        self.assertIsNone(vr.classify('KITCHEN WALL TILE 300 X 300 MM'))
        self.assertEqual(vr.classify('MASTER BEDROOM'), 'master')
        self.assertEqual(vr.classify('BEDROOM 2'), 'bedroom')
        self.assertEqual(vr.classify('Pooja'), 'pooja')


if __name__ == '__main__':
    unittest.main()
