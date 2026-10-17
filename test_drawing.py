import unittest
from drawing_workspace import measured_geometry,polygon_area
class DrawingTests(unittest.TestCase):
 def test_polygon(self):self.assertEqual(polygon_area([[0,0],[10,0],[10,10],[0,10]]),100)
 def test_calibrated_area(self):
  r=measured_geometry({'calibration':[[0,0],[100,0]],'known_length':10,'unit':'ft','points':[[0,0],[100,0],[100,100],[0,100]],'mode':'area'})
  self.assertAlmostEqual(r['amount'],9.290304)
 def test_calibrated_length(self):
  r=measured_geometry({'calibration':[[0,0],[100,0]],'known_length':10,'unit':'m','points':[[0,0],[50,0]],'mode':'length'})
  self.assertEqual(r['amount'],5)
 def test_reject_uncalibrated(self):
  with self.assertRaises(ValueError):measured_geometry({'calibration':[[0,0],[0,0]],'known_length':10,'unit':'m','points':[[0,0],[50,0]],'mode':'length'})
if __name__=='__main__':unittest.main()
