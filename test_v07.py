import unittest, math
from engineering import takeoff, UNIT_TO_M, WORKS
class V07(unittest.TestCase):
    def test_feet_conversion(self):
        r=takeoff('blockwork',15,10,0.2/UNIT_TO_M['ft'],unit='ft',brick_length=.6,brick_height=.2,brick_width=.2,joint=.004,adhesive_coverage=5)
        self.assertAlmostEqual(r['net_area_m2'],13.935456,places=4)
        self.assertAlmostEqual(r['net_volume_m3'],2.7870912,places=4)
        self.assertEqual(r['items'][0]['unit'],'nos')
        self.assertIsInstance(r['items'][0]['quantity'],int)
        self.assertEqual(r['items'][1]['unit'],'kg')
        self.assertEqual(r['items'][2]['unit'],'bags (40 kg)')
        self.assertEqual(r['items'][2]['quantity'],math.ceil(r['items'][1]['quantity']/40))
    def test_excavation(self):
        r=takeoff('excavation',10,2,1,waste=0)
        self.assertEqual(r['items'][0]['quantity'],20)
    def test_brick_whole(self):
        r=takeoff('brickwork',5,3,.23)
        self.assertIsInstance(r['items'][0]['quantity'],int)
    def test_invalid_coverage(self):
        with self.assertRaises(ValueError):takeoff('blockwork',5,3,.2,joint=.004,adhesive_coverage=0)
if __name__=='__main__': unittest.main()
