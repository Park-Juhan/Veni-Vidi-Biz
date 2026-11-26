from decimal import Decimal
import unittest

from app.common.validation import ValidationError
from tests.module_support import StandaloneModuleChecks, model_for


class PropertyTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'property'

    def run_model(self, **changes):
        model = model_for('property')
        return model.analyze(model.defaults() | {'rent_band': '상관없음'} | changes, 'a').result

    def test_area_and_costs_follow_seats_and_rent_per_m2(self):
        r = self.run_model()
        # 16 seats x 1.8㎡ + 15㎡ = 43.8 -> 44㎡; 망원역 at 40,000원/㎡ -> 1,760,000원.
        self.assertEqual(r['metrics'][3][1], Decimal(44))
        rows = {row[1].split(' (')[0]: row for row in r['rows']}
        self.assertEqual(rows['망원역'][2], Decimal(1760000))
        # deposit 10 months + first rent + interior 550,000 x 44 + equipment + stock + other
        self.assertEqual(rows['망원역'][3], Decimal(17600000 + 1760000 + 24200000 + 25000000 + 2000000 + 5000000))
        self.assertEqual(len(r['trace']), 4)

    def test_top_five_skip_thin_areas_and_respect_band_and_districts(self):
        r = self.run_model()
        names = [row[1].split(' (')[0] for row in r['rows']]
        self.assertNotIn('작은골목', names)          # only 2 stores
        self.assertEqual(len(names), 4)
        self.assertEqual([row[0] for row in r['rows']], [1, 2, 3, 4])
        scores = [row[7] for row in r['rows']]
        self.assertEqual(scores, sorted(scores, reverse=True))
        # 홍대입구 costs 60,000원/㎡ x 44 = 2,640,000원: outside 100~200만 원.
        band = self.run_model(rent_band='100~200만 원')
        self.assertNotIn('홍대입구', [row[1] for row in band['rows']])
        only_jung = model_for('property')
        r = only_jung.analyze(only_jung.defaults() | {'rent_band': '상관없음', 'districts': ['중구']}, 'a').result
        self.assertEqual([row[1].split(' (')[0] for row in r['rows']], ['시청'])

    def test_advice_and_exports(self):
        model = model_for('property')
        record = model.analyze(model.defaults() | {'rent_band': '상관없음', 'available': '1000'}, 'a')
        self.assertTrue(any('부족합니다' in line for line in record.result['advice']))
        snapshot = model.export_location('a')
        self.assertEqual(snapshot.area_name, record.result['best_name'])
        self.assertEqual(model.export_operating_costs('a').monthly_rent, record.result['best_rent'])

    def test_no_area_in_budget_or_unknown_industry(self):
        model = model_for('property')
        with self.assertRaises(ValidationError):
            model.analyze(model.defaults() | {'rent_band': '100만 원 이하'}, 'a')
        with self.assertRaises(ValidationError):
            model.analyze(model.defaults() | {'industry': '없는 업종'}, 'a')

    def test_without_public_data_explains_how_to_import(self):
        model = model_for('property')
        model.area_provider = None
        with self.assertRaisesRegex(ValidationError, 'import_data'):
            model.analyze(model.defaults(), 'a')


if __name__ == "__main__":
    unittest.main()
