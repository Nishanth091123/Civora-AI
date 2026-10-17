import unittest
from pathlib import Path
from drawing_schedule import extract
from intelligent_recognition import calculate
from engineering import takeoff
ROOT=Path(__file__).parent/'sample_drawings'
import importlib.util
def _has(mod):return importlib.util.find_spec(mod) is not None
def _has_tesseract():
    try:
        import pytesseract;pytesseract.get_tesseract_version();return True
    except Exception:return False
NEEDS={'png':_has_tesseract,'pdf':lambda:_has('fitz'),'dxf':lambda:_has('ezdxf')}
class SampleWorkflow(unittest.TestCase):
    def test_schedule_all_three_formats(self):
        for ext in ('png','pdf','dxf'):
            with self.subTest(ext=ext):
                if not NEEDS[ext]():self.skipTest(ext+' support not installed (PyMuPDF / ezdxf / Tesseract)')
                s=extract(ROOT/('Civora_Complete_Test_Plan.'+ext))
                e=s['evidence']
                self.assertAlmostEqual(e['floor_area']['value'],108)
                self.assertAlmostEqual(e['slab_thickness']['value'],.15)
                self.assertAlmostEqual(e['external_thickness']['value'],.23)
                self.assertEqual(len(s['rooms']),6)
                self.assertEqual(len(s['openings']),4)
                self.assertAlmostEqual(s['opening_area_sum'],23.31)
    def test_real_takeoff_with_external_deductions(self):
        if not _has('fitz'):self.skipTest('PyMuPDF not installed')
        s=extract(ROOT/'Civora_Complete_Test_Plan.pdf')
        e=s['evidence'];v={
            'floor_area':e['floor_area']['value'],'slab_area':e['slab_area']['value'],
            'height':e['height']['value'],'wall_thickness':e['external_thickness']['value'],
            'slab_thickness':e['slab_thickness']['value'],
            'overall_length':e['overall_length']['value'],'overall_width':e['overall_width']['value'],
            'external_opening_area':sum(o['area'] for o in s['openings'] if 'D2' not in o['label']),
            'external_plaster_thickness':.015,'waste':5}
        r=calculate(v,set(),set(),{'regions':[],'lines':[]},takeoff)
        names=[x[0] for x in r['rows']]
        for n in ('Floor tiles','Floor screed','RCC slab (rmc)','External masonry – indicative (net openings)','External plaster – indicative (outer face)'):
            self.assertIn(n,names)
        b={k:value for k,value,_ in r['breakdown']}
        self.assertAlmostEqual(b['RCC slab concrete volume'],16.2)
        self.assertAlmostEqual(b['External wall net face (indicative)'],112.14)
    def test_no_invention_on_blank(self):
        r=calculate({},set(),set(),{'regions':[],'lines':[]},takeoff)
        self.assertEqual(r['rows'],[])
if __name__=='__main__':unittest.main()
