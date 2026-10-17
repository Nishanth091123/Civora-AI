import unittest
from unittest.mock import patch
import unittest
try:
    import cv2
except ImportError as _e:  # e.g. Windows Application Control blocking the OpenCV DLL
    raise unittest.SkipTest('OpenCV (cv2) cannot load: %s - Recognition/Intelligence image features unavailable' % _e)
import numpy as np
from intelligent_recognition import detect

class RecognitionShapeTests(unittest.TestCase):
    def setUp(self):
        self.img=np.full((300,400,3),255,dtype=np.uint8)
        cv2.line(self.img,(20,30),(350,30),(0,0,0),2)
    def test_standard_opencv_n_1_4(self):
        lines=np.array([[[20,30,350,30]]],dtype=np.int32)
        with patch('cv2.HoughLinesP',return_value=lines):
            self.assertGreaterEqual(len(detect(self.img)['lines']),1)
    def test_flat_opencv_n_4(self):
        lines=np.array([[20,30,350,30]],dtype=np.int32)
        with patch('cv2.HoughLinesP',return_value=lines):
            self.assertGreaterEqual(len(detect(self.img)['lines']),1)
    def test_none(self):
        with patch('cv2.HoughLinesP',return_value=None):
            self.assertEqual(detect(self.img)['lines'],[])

if __name__=='__main__': unittest.main()
