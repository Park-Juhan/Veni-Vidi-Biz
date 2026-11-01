from decimal import Decimal
import unittest

from app.common.validation import ValidationError
from tests.module_support import StandaloneModuleChecks, model_for


class MenuPricingTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'menu_pricing'

    def test_menu_price_margin_and_scenarios(self):
        model=model_for('menu_pricing')
        record=model.analyze(model.defaults(),'a')
        self.assertEqual(record.result['metrics'][0][1],Decimal(4300))
        self.assertEqual(record.result['rows'][0][3],Decimal(4500000))
        self.assertEqual(record.result['rows'][0][5],Decimal(3000000))
        self.assertGreaterEqual(record.result['rows'][1][6],Decimal(65))


    def test_menu_limits(self):
        model=model_for('menu_pricing')
        for changes in ({'margin':'100'},{'volume':'0.5'},{'material':'-1'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                model.analyze(model.defaults()|changes,'a')


    def test_menu_zero_price_does_not_divide_by_zero(self):
        model=model_for('menu_pricing')
        record=model.analyze(model.defaults()|{'price':'0'},'a')
        self.assertEqual(record.result['rows'][0][6],'산출 불가')


if __name__ == "__main__":
    unittest.main()
