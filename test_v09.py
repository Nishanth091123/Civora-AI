import unittest
from engineering import takeoff
class TestV09(unittest.TestCase):
 def test_rmc(self):
  r=takeoff('rcc',10,2,.2,rcc_mode='rmc');self.assertEqual(len(r['items']),1);self.assertIn('RMC',r['items'][0]['material'])
 def test_site_nominal(self):
  r=takeoff('rcc',10,2,.2,rcc_mode='site');self.assertTrue(any(x['material']=='Cement' for x in r['items']));self.assertFalse(any('RMC' in x['material'] for x in r['items']))
 def test_m25_nominal_rejected(self):
  with self.assertRaises(ValueError):takeoff('rcc',10,2,.2,rcc_mode='site',rcc_grade='M25')
 def test_design(self):
  r=takeoff('rcc',10,2,.2,rcc_mode='site',rcc_site_method='design',rcc_grade='M25',rcc_cement_kg=350,rcc_msand_kg=700,rcc_aggregate_kg=1100,rcc_water_l=175,waste=0)
  self.assertEqual(next(x['quantity'] for x in r['items'] if x['material']=='Cement'),1400)
 def test_steel_count(self):
  r=takeoff('steel',10,2,.1,steel_bar_count=10,steel_cut_length_m=12,steel_diameter_mm=12,waste=0)
  self.assertAlmostEqual(r['items'][0]['quantity'],106.667,places=2)
if __name__=='__main__':unittest.main()
