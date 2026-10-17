import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import unittest
try:
    import cv2
except ImportError as _e:  # e.g. Windows Application Control blocking the OpenCV DLL
    raise unittest.SkipTest('OpenCV (cv2) cannot load: %s - Recognition/Intelligence image features unavailable' % _e)
import numpy as np
from recognition import analyze_image,annotated_png,raster
import importlib.util
_has=lambda m:importlib.util.find_spec(m) is not None

class RecognitionTests(unittest.TestCase):
    def test_rectangular_regions(self):
        im=np.full((600,800,3),255,np.uint8)
        cv2.rectangle(im,(80,70),(340,320),(0,0,0),5)
        cv2.rectangle(im,(410,70),(680,320),(0,0,0),5)
        found=analyze_image(im)
        self.assertGreaterEqual(len(found),2)
        self.assertTrue(annotated_png(im,found).startswith(b'\x89PNG'))
    def test_blank_drawing(self):
        im=np.full((400,400,3),255,np.uint8)
        self.assertEqual(analyze_image(im),[])
    def test_image_input(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'drawing.png';cv2.imwrite(str(path),np.full((300,400,3),255,np.uint8))
            self.assertEqual(raster(path).shape[:2],(300,400))
    @unittest.skipUnless(_has('ezdxf'),'ezdxf not installed')
    def test_dxf_input(self):
        import tempfile,ezdxf
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'drawing.dxf';doc=ezdxf.new();m=doc.modelspace();m.add_lwpolyline([(0,0),(10,0),(10,5),(0,5)],close=True);doc.saveas(path)
            self.assertEqual(len(raster(path).shape),3)
    @unittest.skipUnless(_has('fitz'),'PyMuPDF not installed')
    def test_pdf_input(self):
        import tempfile,fitz
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'drawing.pdf';doc=fitz.open();page=doc.new_page();page.draw_rect(fitz.Rect(30,30,180,200));doc.save(path);doc.close()
            self.assertEqual(len(raster(path).shape),3)
if __name__=='__main__':unittest.main()
