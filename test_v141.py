import unittest
from intelligent_recognition import calculate

def fake_takeoff(**kw):
    return {'items':[{'material':'Test','quantity':kw['length']*kw['depth'],'unit':'m3'}]}

class Tests(unittest.TestCase):
    def test_manual_floor_and_slab(self):
        v={'floor_area':108,'slab_area':108,'slab_thickness':.15,'waste':5,'rcc_mode':'rmc'}
        r=calculate(v,set(),set(),{'regions':[],'lines':[]},fake_takeoff)
        self.assertTrue(any('Floor tiles' in x[0] for x in r['rows']))
        self.assertTrue(any('RCC slab' in x[0] for x in r['rows']))
        self.assertAlmostEqual(dict((k,val) for k,val,_ in r['breakdown'])['RCC slab concrete volume'],16.2)
    def test_opening_deduction(self):
        v={'wall_length':40,'height':3,'opening_area':23.31,'wall_thickness':.23,'finish_faces':2,'paint_from_plaster':True,'waste':5}
        r=calculate(v,set(),set(),{'regions':[],'lines':[]},fake_takeoff)
        self.assertAlmostEqual(r['wall_area'],96.69)
        self.assertTrue(any('Painting'==x[0] for x in r['rows']))
    def test_no_invented_quantities(self):
        r=calculate({},set(),set(),{'regions':[],'lines':[]},fake_takeoff)
        self.assertFalse(r['rows'])
if __name__=='__main__':unittest.main()
