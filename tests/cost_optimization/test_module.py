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

    def test_monte_carlo_matches_normal_theory(self):
        from statistics import NormalDist
        model=model_for('cost_optimization')
        r=model.analyze(model.defaults()|{'cost_volatility':'0'},'a').result
        # Only revenue varies: loss iff revenue < break-even, i.e. Z < (BEP/R - 1)/sigma.
        expected=NormalDist().cdf((float(r['breakeven'])/12000000-1)/0.2)*100
        self.assertAlmostEqual(float(r['loss_before']),expected,delta=0.7)
        self.assertLessEqual(r['loss_after'],r['loss_before'])
        self.assertEqual(r['model'],'몬테카를로 적자 위험 시뮬레이션')

    def test_simulation_is_deterministic_and_zero_volatility_is_certain(self):
        model=model_for('cost_optimization')
        first=model.analyze(model.defaults(),'a').result;second=model.analyze(model.defaults(),'b').result
        self.assertEqual(first['metrics'],second['metrics'])
        certain=model.analyze(model.defaults()|{'revenue_volatility':'0','cost_volatility':'0'},'a').result
        self.assertEqual(certain['loss_before'],0)
        self.assertEqual(dict((m[0],m[1]) for m in certain['metrics'])['하위 5% 월 손익 (절감 후)'],Decimal(4300000))
        risky=model.analyze(model.defaults()|{'revenue':'7000000'},'a').result
        self.assertGreater(risky['loss_before'],40)


if __name__ == "__main__":
    unittest.main()
