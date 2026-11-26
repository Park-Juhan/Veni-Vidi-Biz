from decimal import Decimal
import unittest

from app.common.validation import ValidationError
from app.modules.material_cost.models import recipes
from tests.module_support import StandaloneModuleChecks, model_for


class MaterialCostTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'material_cost'

    def test_dish_cost_purchase_and_export(self):
        model = model_for('material_cost')
        record = model.analyze(model.defaults() | {'dish': '카페라떼', 'monthly_volume': '900'}, 'a')
        r = record.result
        # 원두 18g x 25원 + 우유 220mL x 2.4원 = 450 + 528
        self.assertEqual(r['usage_cost'], Decimal(978))
        rows = {row[0]: row for row in r['rows']}
        self.assertEqual(rows['원두'][7], '1kg 봉 × 17')        # 16.2kg a month
        self.assertEqual(rows['우유'][7], '1L 팩 × 198')
        self.assertEqual(r['metrics'][1][1], Decimal(17 * 25000 + 198 * 2400))
        self.assertEqual(model.export_usage_cost('a').usage_cost, Decimal(978))

    def test_yield_raises_cost_and_amount_to_buy(self):
        model = model_for('material_cost')
        lines = {l['name']: l for l in model.analyze(model.defaults() | {'dish': '바나나라떼'}, 'a').result['lines']}
        # 100g used at 65% yield -> 153.8g bought at 2.5원.
        self.assertAlmostEqual(lines['바나나']['cost'], Decimal(100) / Decimal('0.65') * Decimal('2.5'), places=10)

    def test_unknown_dish_lists_choices(self):
        model = model_for('material_cost')
        with self.assertRaisesRegex(ValidationError, '아메리카노'):
            model.analyze(model.defaults() | {'dish': '없는 음식'}, 'a')
        with self.assertRaises(ValidationError):
            model.analyze(model.defaults() | {'monthly_volume': '0'}, 'a')

    def test_every_recipe_calculates(self):
        model = model_for('material_cost')
        for name in recipes.names():
            with self.subTest(dish=name):
                self.assertGreater(model.analyze(model.defaults() | {'dish': name}, 'a').result['usage_cost'], 0)


if __name__ == "__main__":
    unittest.main()
