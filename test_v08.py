import unittest, math
from engineering import takeoff, WORKS
class V08(unittest.TestCase):
    def test_rcc_approved_mix(self):
        r=takeoff('rcc',10,2,.2,waste=0,rcc_mode='site',rcc_site_method='design',rcc_cement_kg=350,rcc_msand_kg=700,rcc_aggregate_kg=1100,rcc_water_l=175)
        items={x['material']:x['quantity'] for x in r['items']}
        self.assertEqual(items['Cement'],1400)
        self.assertEqual(items['M-sand'],2800)
        self.assertEqual(items['Coarse aggregate'],4400)
        self.assertEqual(items['Cement 50 kg bags'],28)
    def test_rcc_grade_does_not_invent_mix(self):
        r=takeoff('rcc',10,2,.2)
        self.assertFalse(any(x['material']=='Cement' for x in r['items']))
    def test_rcc_partial_mix_rejected(self):
        with self.assertRaises(ValueError):
            takeoff('rcc',10,2,.2,rcc_mode='site',rcc_site_method='design',rcc_cement_kg=350)
    def test_steel(self):
        r=takeoff('steel',10,2,.1,steel_diameter_mm=12,steel_total_length_m=162,waste=0)
        self.assertEqual(r['items'][0]['quantity'],144)
    def test_other_works(self):
        for work in ['backfill','shuttering','waterproofing','screed','excavation']:
            self.assertTrue(takeoff(work,10,2,.1)['items'])
    def test_aac_whole(self):
        r=takeoff('blockwork',15,10,.2,joint=.004)
        self.assertIsInstance(r['items'][0]['quantity'],int)
if __name__=='__main__':unittest.main()
