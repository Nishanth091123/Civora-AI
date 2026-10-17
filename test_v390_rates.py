"""v3.9.0: complete Rate Master - item-wise labour, doors/windows/services, contingency + margin."""
import importlib.util
import unittest

import rates_v260 as rv

HAVE_CALC = importlib.util.find_spec('fastapi') is not None


def priced(area, floors, saved=None):
    import quick_v280 as q
    import workflow_v250 as wf
    from engineering import takeoff
    inp, opts, r = q.quick_estimate(area, floors, takeoff)
    pl = {'rows': [{'work': l, 'area': a, 'items': it} for l, a, it in r['rows']], 'builtup_sqft': r['builtup_sqft'],
          'floors': floors, 'options': opts, 'inputs': [{'key': k, 'value': x['value']} for k, x in inp.items()], 'cost_extras': {}}
    rv.apply_rates(pl, rv.effective_rates(saved or {}), pl['builtup_sqft'])
    return pl, wf.boq_cost(pl)


class RateMasterTests(unittest.TestCase):
    def test_every_rate_has_a_market_value(self):
        self.assertEqual(set(rv.MARKET_RATES), set(rv.RATE_KEYS))
        self.assertGreaterEqual(len(rv.RATE_KEYS), 40)

    @unittest.skipUnless(HAVE_CALC, 'needs fastapi')
    def test_complete_house_cost_is_realistic(self):
        pl, bc = priced(1000, 1)
        total = bc['material'] + bc['labour'] + bc['transport'] + bc['other']
        # Tamil Nadu turnkey construction ~ ₹2,000–2,500 per sq.ft (Trichy ₹2,048–2,460)
        self.assertTrue(1900 < total / 1000 < 2600, total / 1000)
        self.assertEqual(bc['unrated'], 0)
        works = [r['work'] for r in pl['rows']]
        self.assertIn(rv.LABOUR_WORK, works)
        self.assertIn(rv.SERVICES_WORK, works)
        self.assertGreater(bc['labour'], 0.12 * total)            # labour is a real share of the cost

    @unittest.skipUnless(HAVE_CALC, 'needs fastapi')
    def test_lump_sum_labour_replaces_item_labour(self):
        pl, bc = priced(1000, 1, {'labour_sqft': 450})
        labour_lines = [i for r in pl['rows'] for i in r['items'] if str(i.get('rate_key', '')).startswith('lab_')]
        self.assertEqual(labour_lines, [])
        self.assertAlmostEqual(bc['labour'], 450 * pl['builtup_sqft'], delta=1)

    @unittest.skipUnless(HAVE_CALC, 'needs fastapi')
    def test_reapplying_does_not_duplicate(self):
        pl, _ = priced(1000, 1)
        rv.apply_rates(pl, rv.effective_rates({}), pl['builtup_sqft'])
        self.assertEqual(sum(1 for r in pl['rows'] if r.get(rv.AUTO_TAG)), 2)

    def test_doors_from_schedule(self):
        pl = {'floors': 1, 'openings': [
            {'label': 'DOOR D1', 'width': 1.05, 'count': 1, 'source': 'MAIN'},
            {'label': 'DOOR D2', 'width': 0.9, 'count': 3, 'source': 'INTERNAL'},
            {'label': 'DOOR D3', 'width': 0.75, 'count': 2, 'source': 'INTERNAL TOILET'},
            {'label': 'WINDOW W1', 'width': 1.5, 'count': 5, 'area': 9.0}]}
        main, internal, toilet, win, _ = rv._openings(pl)
        self.assertEqual((main, internal, toilet, win), (1, 3, 2, 9.0))


if __name__ == '__main__':
    unittest.main()


class ManualEditTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_CALC, 'needs fastapi')
    def test_hand_edits_survive_repricing(self):
        pl, _ = priced(1000, 1)
        lab = next(r for r in pl['rows'] if r['work'] == rv.LABOUR_WORK)
        plaster = next(i for i in lab['items'] if i['rate_key'] == 'lab_plaster')
        plaster.update(rate=250, manual_rate=True)
        cement = next(i for r in pl['rows'] for i in r['items'] if i['material'] == 'Cement' and 'bag' in i['unit'])
        cement.update(rate=380, manual_rate=True)
        pl['cost_extras']['transport'] = 1234; pl['cost_extras']['manual'] = ['transport']
        pl['removed_auto'] = ['Sump (underground tank)']
        rv.apply_rates(pl, rv.effective_rates({}), pl['builtup_sqft'])
        lab = next(r for r in pl['rows'] if r['work'] == rv.LABOUR_WORK)
        self.assertEqual(next(i for i in lab['items'] if i['rate_key'] == 'lab_plaster')['rate'], 250)
        self.assertEqual(cement['rate'], 380)
        self.assertEqual(pl['cost_extras']['transport'], 1234)
        svc = next(r for r in pl['rows'] if r['work'] == rv.SERVICES_WORK)
        self.assertNotIn('Sump (underground tank)', [i['material'] for i in svc['items']])

    @unittest.skipUnless(HAVE_CALC, 'needs fastapi')
    def test_old_estimate_is_upgraded(self):
        import json, sqlite3
        pl, _ = priced(1000, 1)
        pl['rows'] = [r for r in pl['rows'] if not r.get(rv.AUTO_TAG)]
        pl.pop('pricing_version', None)
        pl['cost_extras'] = {'labour': 500000, 'transport': 0, 'other': 0, 'tax_percent': 0}
        c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
        c.executescript('CREATE TABLE projects(id TEXT, owner_id TEXT, area REAL); CREATE TABLE civora_boq_reports(id TEXT, project_id TEXT, payload TEXT);'
                        'CREATE TABLE civora_rate_master_v260(user_id TEXT, key TEXT, rate REAL, updated INTEGER)')
        c.execute("INSERT INTO projects VALUES('p','u',1000)")
        c.execute("INSERT INTO civora_boq_reports VALUES('b','p',?)", (json.dumps(pl),))
        p = c.execute('SELECT * FROM projects').fetchone()
        self.assertEqual(rv.upgrade_saved(c, p, c.execute('SELECT * FROM civora_boq_reports').fetchall()), ['b'])
        d = json.loads(c.execute('SELECT payload FROM civora_boq_reports').fetchone()[0])
        self.assertEqual(d['pricing_version'], rv.PRICING_VERSION)
        self.assertEqual(d['cost_extras']['labour'], 0)                      # lump sum replaced by item-wise labour
        self.assertIn(rv.LABOUR_WORK, [r['work'] for r in d['rows']])
        self.assertEqual(rv.upgrade_saved(c, p, c.execute('SELECT * FROM civora_boq_reports').fetchall()), [])   # only once
