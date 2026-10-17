import unittest
from engineering import takeoff,convert_length
class TestTakeoff(unittest.TestCase):
    def test_units(self):
        for unit,vals in [('m',(3.048,3.048,.2286)),('ft',(10,10,.75)),('in',(120,120,9)),('mm',(3048,3048,228.6))]:
            result=takeoff('brickwork',*vals,unit=unit,waste=0)
            self.assertAlmostEqual(result['net_volume_m3'],2.123,places=2)
    def test_mortar_selection(self):
        a=takeoff('plaster',5,3,.012,plaster_ratio='1:4',waste=0)
        b=takeoff('plaster',5,3,.012,plaster_ratio='1:8',waste=0)
        self.assertGreater(a['items'][0]['quantity'],b['items'][0]['quantity'])
    def test_rcc_grade_not_mix(self):
        # v0.9+: default supply is RMC volume only; a grade never invents a mix (updated v2.4).
        r=takeoff('rcc',5,4,.2,rcc_grade='M35')
        self.assertEqual(len(r['items']),1)
        self.assertIn('RMC',r['items'][0]['material'])
        self.assertFalse(any(x['material']=='Cement' for x in r['items']))
    def test_pcc(self):
        self.assertEqual(len(takeoff('pcc',3,3,.1,pcc_ratio='1:3:6')['items']),3)
    def test_invalid(self):
        with self.assertRaises(ValueError): takeoff('rcc',3,3,.1,unit='yards')
        with self.assertRaises(ValueError): takeoff('rcc',3,3,.1,rcc_grade='M100')
if __name__=='__main__': unittest.main()
