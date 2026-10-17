import unittest
import unittest
try:
    import cv2
except ImportError as _e:  # e.g. Windows Application Control blocking the OpenCV DLL
    raise unittest.SkipTest('OpenCV (cv2) cannot load: %s - Recognition/Intelligence image features unavailable' % _e)
import numpy as np
from intelligent_recognition import detect,union_area,calculate
class TestIntelligence(unittest.TestCase):
 def test_regions_lines(self):
  a=np.full((400,500,3),255,np.uint8);cv2.rectangle(a,(80,70),(360,320),(0,0,0),3)
  result=detect(a);self.assertGreater(len(result['lines']),0);self.assertGreater(len(result['regions']),0)
 def test_union(self):self.assertEqual(union_area([(0,0,10,10),(5,0,10,10)]),150)
 def test_partial(self):
  d={'lines':[],'regions':[]};r=calculate({'floor_area':20,'slab_area':None,'wall_thickness':None,'waste':5,'rcc_mode':'rmc'},set(),set(),d,lambda **kw:{'items':[{'material':'Tile','quantity':1,'unit':'Nos'}]})
  self.assertTrue(any(x[0]=='Floor tiles' for x in r['rows']));self.assertTrue(any(x.startswith('Brick masonry') for x in r['skipped']))
 def test_wall_length(self):
  d={'lines':[(0,0,100,0,100,'horizontal')],'regions':[]};r=calculate({'scale':.1,'height':3,'wall_thickness':.23,'waste':5},set(),{0},d,lambda **kw:{'items':[]})
  self.assertAlmostEqual(r['wall_length'],10);self.assertAlmostEqual(r['wall_area'],30)
if __name__=='__main__':unittest.main()
