from decimal import Decimal
import unittest

from app.common.validation import ValidationError
from tests.module_support import StandaloneModuleChecks, model_for


class MenuPricingTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'menu_pricing'

    def test_break_even_and_profit(self):
        model = model_for('menu_pricing')
        v = model.defaults() | {'material': '1000', 'other': '500', 'price': '5000', 'volume': '900',
                                'rent': '1500000', 'labor': '3000000', 'fixed_other': '500000'}
        r = model.analyze(v, 'a').result
        # fixed 5,000,000 / margin 3,500 = 1,428.6 -> 1,429 a month, 48 a day
        self.assertEqual(r['metrics'][0][1], '하루 48')
        self.assertEqual(r['metrics'][1][1], Decimal(1429 * 5000))
        self.assertEqual(r['metrics'][3][1], Decimal(3500 * 900 - 5000000))
        self.assertTrue(any('모자랍니다' in line for line in r['advice']))
        # 900 a month covers 5,000,000 only with a margin of 5,556 or more -> price 7,100.
        self.assertTrue(any('7,100원 이상' in line for line in r['advice']))

    def test_price_below_cost_never_breaks_even(self):
        model = model_for('menu_pricing')
        r = model.analyze(model.defaults() | {'material': '3000', 'price': '3000'}, 'a').result
        self.assertEqual(r['metrics'][0][1], '도달 불가')
        self.assertIn('팔수록 손해', r['advice'][0])

    def test_menu_limits(self):
        model = model_for('menu_pricing')
        for changes in ({'volume': '0.5'}, {'material': '-1'}, {'price': '0'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                model.analyze(model.defaults() | changes, 'a')


if __name__ == "__main__":
    unittest.main()
