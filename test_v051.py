import unittest
from engineering import takeoff
class Tests(unittest.TestCase):
 def test_aac(self):
  r=takeoff('blockwork',3,2,.2,brick_length=.6,brick_height=.2,brick_width=.2,joint=.004)
  self.assertTrue(any(i['material']=='AAC blocks' for i in r['items']))
  self.assertTrue(any('adhesive' in i['material'].lower() for i in r['items']))
  self.assertFalse(any(i['material']=='Cement' for i in r['items']))
 def test_aac_joint_bounds(self):
  with self.assertRaises(ValueError): takeoff('blockwork',3,2,.2,joint=.01)
 def test_brick_mortar(self):
  r=takeoff('brickwork',3,2,.23,mortar_ratio='1:6')
  self.assertTrue(any(i['material']=='Cement' for i in r['items']))
 def test_unrelated_ratio_ignored(self):
  r=takeoff('blockwork',3,2,.2,joint=.003,mortar_ratio='not-applicable')
  self.assertEqual(r['work'],'AAC block masonry')
if __name__=='__main__':unittest.main()
