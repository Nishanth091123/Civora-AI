import unittest
from drawing_workspace import measured_geometry
class TestRepair(unittest.TestCase):
 def test_rectangle(self):
  g=measured_geometry({'mode':'rectangle','points':[[0,0],[100,50]],'calibration':[[0,0],[100,0]],'known_length':10,'unit':'m'})
  self.assertAlmostEqual(g['amount'],50)
 def test_polygon(self):
  g=measured_geometry({'mode':'area','points':[[0,0],[100,0],[100,50],[0,50]],'calibration':[[0,0],[100,0]],'known_length':10,'unit':'m'})
  self.assertAlmostEqual(g['amount'],50)
 def test_length(self):
  g=measured_geometry({'mode':'length','points':[[0,0],[100,0]],'calibration':[[0,0],[100,0]],'known_length':10,'unit':'m'})
  self.assertAlmostEqual(g['amount'],10)
if __name__=='__main__':unittest.main()
