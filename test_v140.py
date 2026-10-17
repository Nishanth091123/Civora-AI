import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from drawing_schedule import extract
class Tests(unittest.TestCase):
    def test_dxf_annotations(self):
        p=Path(__file__).resolve().parent/'sample_drawings'/'Civora_Complete_Test_Plan.dxf'
        if not p.exists():self.skipTest('Sample DXF not bundled')
        import importlib.util
        if importlib.util.find_spec('ezdxf') is None:self.skipTest('ezdxf not installed')
        x=extract(p)
        self.assertAlmostEqual(x['evidence']['floor_area']['value'],108)
        self.assertAlmostEqual(x['evidence']['slab_thickness']['value'],.15)
        self.assertEqual(len(x['rooms']),6)
        self.assertEqual(sum(a['count'] for a in x['openings']),14)
        self.assertAlmostEqual(x['opening_area_sum'],23.31)
    def test_module(self):
        import intelligent_recognition
        self.assertTrue(callable(intelligent_recognition.calculate))
if __name__=='__main__':unittest.main()
