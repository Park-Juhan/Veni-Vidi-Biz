from decimal import Decimal
import unittest

from app.common.validation import ValidationError
from tests.module_support import StandaloneModuleChecks, model_for


class CostOptimizationTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'cost_optimization'

    def test_operations_savings_and_breakeven(self):
        model=model_for('cost_optimization');r=model.analyze(model.defaults(),'a').result
        self.assertEqual(r['total'],Decimal(8000000))
        self.assertEqual(r['savings'],Decimal(300000))
        self.assertAlmostEqual(r['breakeven'],Decimal('6947368.421052631578947368421'),places=10)
        self.assertEqual(sum(row[1] for row in r['rows']),r['total'])


    def test_operations_unsolvable_breakeven_and_zero_cost(self):
        model=model_for('cost_optimization')
        for revenue in ('0','100','2500000'):
            self.assertIsNone(model.analyze(model.defaults()|{'revenue':revenue},'a').result['breakeven'])
        v={f.name: '0' for f in model.fields}
        r=model.analyze(v,'a').result
        self.assertEqual(r['total'],0)
        self.assertTrue(all(row[2]==0 for row in r['rows']))


if __name__ == "__main__":
    unittest.main()
