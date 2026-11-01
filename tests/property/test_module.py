from decimal import Decimal
import unittest

from app.common.validation import ValidationError
from tests.module_support import StandaloneModuleChecks, model_for


class PropertyTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'property'

    def test_startup_cash_includes_all_components(self):
        model=model_for('property');r=model.analyze(model.defaults(),'a').result
        by_name={row[0]:row for row in r['rows']}
        self.assertEqual(by_name['가상 역세권 A'][4],Decimal(52300000))
        self.assertEqual(by_name['가상 주거지 B'][4],Decimal(49700000))
        self.assertEqual(r['metrics'][0][1],'가상 주거지 B')
        self.assertEqual(len(r['trace']),2)


if __name__ == "__main__":
    unittest.main()
