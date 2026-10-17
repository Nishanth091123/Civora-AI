import unittest
from engineering import takeoff
class TestV06(unittest.TestCase):
 def test_aac_3mm(self):
  x=takeoff('blockwork',5,3,.2,brick_length=.6,brick_height=.2,brick_width=.2,joint=.003);self.assertGreater(x['items'][0]['quantity'],0);self.assertGreater(x['items'][1]['quantity'],0)
 def test_aac_4mm(self):
  x=takeoff('blockwork',5,3,.2,brick_length=.6,brick_height=.2,brick_width=.2,joint=.004);self.assertGreater(x['items'][0]['quantity'],0)
 def test_aac_5mm(self):
  x=takeoff('blockwork',5,3,.2,brick_length=.6,brick_height=.2,brick_width=.2,joint=.005);self.assertGreater(x['items'][1]['quantity'],0)
 def test_aac_invalid(self):
  with self.assertRaises(ValueError):takeoff('blockwork',5,3,.2,brick_length=.6,brick_height=.2,brick_width=.2,joint=.006)
 def test_units(self):
  a=takeoff('pcc',3.048,3.048,.3048);b=takeoff('pcc',10,10,1,unit='ft');self.assertAlmostEqual(a['net_volume_m3'],b['net_volume_m3'])
 def test_masonry(self):
  self.assertGreater(takeoff('brickwork',5,3,.23)['items'][0]['quantity'],0)
if __name__=='__main__':unittest.main()
