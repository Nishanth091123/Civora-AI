"""Civora AI Lite (Streamlit) engine tests: same numbers as the web app's Quick Estimate, downloads work."""
import importlib.util, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


@unittest.skipIf(importlib.util.find_spec('fastapi') is None, 'fastapi not installed')
class LiteTests(unittest.TestCase):
    def test_same_engine_as_web_quick_estimate(self):
        import civora_lite as cl, quick_v280 as q
        from engineering import takeoff
        p = cl.run(1000, 2)
        _, _, res = q.quick_estimate(1000, 2, takeoff)
        self.assertEqual([r['work'] for r in p['rows']], [r[0] for r in res['rows']])
        self.assertGreater(cl.headline(p)['cement_bags'], 50)
        self.assertEqual(cl.cost(p)['total'], 0)               # no rates -> not priced, never invented

    def test_rates_and_downloads(self):
        import civora_lite as cl
        p = cl.run(1200, 1, {'cement_bag': 420, 'steel': 68, 'labour_sqft': 450, 'tax_percent': 18})
        c = cl.cost(p)
        self.assertGreater(c['total'], c['subtotal'])
        self.assertEqual(cl.excel(p)[:2], b'PK')
        self.assertEqual(cl.pdf(p)[:5], b'%PDF-')

    def test_bad_area(self):
        import civora_lite as cl
        with self.assertRaises(ValueError):
            cl.run(10, 1)


if __name__ == '__main__':
    unittest.main()
