"""v2.4 regression tests: opening-schedule parsing (no PDF/DXF libraries needed)."""
import unittest
from pathlib import Path
import drawing_schedule
from drawing_schedule import opening_label, extract

# Exact TEXT entities from Civora_Complete_Test_Plan.dxf / sample.dxf
DXF_LINES = [
    'BEDROOM 1 4.00 x 4.00 m', 'BEDROOM 2 4.00 x 4.00 m', 'KITCHEN 4.00 x 4.00 m',
    'LIVING 4.00 x 5.00 m', 'DINING 4.00 x 5.00 m', 'BEDROOM 3 4.00 x 5.00 m',
    'OVERALL 12000 mm x 9000 mm', 'EXTERNAL WALL 230 mm', 'INTERNAL WALL 115 mm',
    'WALL HEIGHT 3000 mm', 'SLAB THICKNESS 150 mm', 'M25 RCC',
    'MAIN DOOR 1.20 x 2.10 m 1 No', 'INTERNAL DOOR 0.90 x 2.10 m 5 Nos',
    'WINDOW 1.50 x 1.20 m 6 Nos', 'VENT 0.60 x 0.45 m 2 Nos',
    'FLOOR TILE 600 x 600 mm', 'KITCHEN WALL TILE 300 x 300 mm HEIGHT 600 mm',
    'TOILET WALL TILE 300 x 300 mm HEIGHT 2100 mm',
    'BBS NOT AVAILABLE - STRUCTURAL SCHEDULE REQUIRED',
]

def run_extract(lines, name='plan.dxf'):
    original = drawing_schedule.text_from_drawing
    drawing_schedule.text_from_drawing = lambda path, page=0: ([drawing_schedule._normal(s) for s in lines], 'TEST LINES')
    try:
        return extract(Path(name))
    finally:
        drawing_schedule.text_from_drawing = original


class OpeningLabelTests(unittest.TestCase):
    def test_schedule_codes(self):
        self.assertEqual(opening_label('Door D1 - main 1 No. @ 1.20 x 2.10 m'), 'DOOR D1')
        self.assertEqual(opening_label('Door D2 - internal 5 Nos. @ 0.90 x 2.10 m'), 'DOOR D2')
        self.assertEqual(opening_label('Window W1 6 Nos. @ 1.50 x 1.20 m'), 'WINDOW W1')
        self.assertEqual(opening_label('Ventilator V1 2 Nos. @ 0.60 x 0.45 m'), 'VENTILATOR V1')

    def test_size_digits_are_not_labels(self):
        # Before v2.4 these became 'DOOR 1' and 'DOOR 0' (first digit of the size).
        self.assertEqual(opening_label('MAIN DOOR 1.20 x 2.10 m 1 No'), 'MAIN DOOR')
        self.assertEqual(opening_label('INTERNAL DOOR 0.90 x 2.10 m 5 Nos'), 'INTERNAL DOOR')
        self.assertEqual(opening_label('WINDOW 1.50 x 1.20 m 6 Nos'), 'WINDOW')
        self.assertEqual(opening_label('VENT 0.60 x 0.45 m 2 Nos'), 'VENTILATOR')

    def test_no_opening(self):
        self.assertIsNone(opening_label('SLAB THICKNESS 150 mm'))


class ScheduleExtractionTests(unittest.TestCase):
    def test_dxf_schedule(self):
        s = run_extract(DXF_LINES)
        e = s['evidence']
        self.assertAlmostEqual(e['floor_area']['value'], 108)
        self.assertAlmostEqual(e['slab_thickness']['value'], .15)
        self.assertAlmostEqual(e['external_thickness']['value'], .23)
        self.assertAlmostEqual(e['internal_thickness']['value'], .115)
        self.assertEqual(len(s['rooms']), 6)
        labels = {o['label']: o for o in s['openings']}
        self.assertEqual(set(labels), {'MAIN DOOR', 'INTERNAL DOOR', 'WINDOW', 'VENTILATOR'})
        self.assertEqual(sum(o['count'] for o in s['openings']), 14)
        self.assertAlmostEqual(s['opening_area_sum'], 23.31)
        # Internal / external split used by Drawing Intelligence: 9.45 internal, 13.86 external.
        internal = sum(o['area'] for o in s['openings'] if 'D2' in o['label'] or 'INTERNAL' in o['source'])
        self.assertAlmostEqual(internal, 9.45)
        self.assertAlmostEqual(s['opening_area_sum'] - internal, 13.86)

    def test_two_doors_same_leading_digit_both_kept(self):
        # Regression: both labels used to collapse to 'DOOR 0', silently dropping the second door.
        s = run_extract(['MAIN DOOR 0.90 x 2.10 m 1 No', 'INTERNAL DOOR 0.80 x 2.10 m 4 Nos'])
        self.assertEqual(len(s['openings']), 2)
        self.assertAlmostEqual(s['opening_area_sum'], 0.9*2.1 + 4*0.8*2.1)

    def test_repeated_row_not_double_counted(self):
        s = run_extract(['WINDOW 1.50 x 1.20 m 6 Nos', 'WINDOW 1.50 x 1.20 m 6 Nos'])
        self.assertEqual(len(s['openings']), 1)

    def test_two_window_sizes_both_kept(self):
        s = run_extract(['WINDOW 1.50 x 1.20 m 6 Nos', 'WINDOW 1.00 x 1.20 m 2 Nos'])
        self.assertEqual(len(s['openings']), 2)


if __name__ == '__main__':
    unittest.main()
