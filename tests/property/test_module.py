from decimal import Decimal
import unittest

from app.common.decision import Criterion, topsis
from app.common.validation import ValidationError
from tests.module_support import StandaloneModuleChecks, model_for


class TopsisTests(unittest.TestCase):
    def test_known_values(self):
        rows = [{'x': Decimal(v)} for v in (1, 2, 3)]
        closeness = topsis(rows, [Criterion('x', 'x', Decimal(1))])
        self.assertEqual(closeness[0], 0)
        self.assertAlmostEqual(closeness[1], Decimal('0.5'), places=20)
        self.assertEqual(closeness[2], 1)
        # Cost criterion reverses the order.
        self.assertEqual(topsis(rows, [Criterion('x', 'x', Decimal(1), benefit=False)])[0], 1)

    def test_identical_and_zero_columns(self):
        rows = [{'x': Decimal(0), 'y': Decimal(2)}, {'x': Decimal(0), 'y': Decimal(2)}]
        self.assertEqual(topsis(rows, [Criterion('x', 'x', Decimal(1)), Criterion('y', 'y', Decimal(1))]), [Decimal('0.5')] * 2)
        with self.assertRaises(ValueError):
            topsis(rows, [Criterion('x', 'x', Decimal(0))])


class PropertyTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'property'

    def test_startup_cash_includes_all_components(self):
        model=model_for('property');r=model.analyze(model.defaults(),'a').result
        by_name={row[0]:row for row in r['rows']}
        self.assertEqual(by_name['가상 역세권 A'][4],Decimal(52300000))
        self.assertEqual(by_name['가상 주거지 B'][4],Decimal(49700000))
        self.assertEqual(r['metrics'][0][1],'가상 주거지 B')
        self.assertEqual(len(r['trace']),3)
        self.assertEqual(r['model'],'TOPSIS 다기준 의사결정')

    def test_feasible_candidate_beats_higher_closeness(self):
        model=model_for('property')
        # Make A better on every criterion but over the rent budget.
        v=model.defaults()|{'a_rent':'1600000','a_deposit':'1','a_interior':'1','a_area':'90','a_fit':'5','a_traffic':'5','a_facility':'5'}
        r=model.analyze(v,'a').result
        by_name={row[0]:row for row in r['rows']}
        self.assertGreater(by_name['가상 역세권 A'][7],by_name['가상 주거지 B'][7])
        self.assertEqual(by_name['가상 역세권 A'][6],'미충족')
        self.assertEqual(r['metrics'][0][1],'가상 주거지 B')
        # Once the budget allows A, the better candidate is recommended.
        r=model.analyze(v|{'budget':'2000000'},'a').result
        self.assertEqual(r['metrics'][0][1],'가상 역세권 A')

    def test_weights_change_ranking_and_sensitivity_is_reported(self):
        model=model_for('property')
        v=model.defaults()|{'budget':'2000000'}  # both feasible
        cheap=model.analyze(v|{'w_rent':'5','w_startup':'5','w_fit':'0','w_facility':'0','w_area':'0','w_traffic':'0'},'a').result
        self.assertEqual(cheap['metrics'][0][1],'가상 주거지 B')
        # A is better on every criterion that still counts: full closeness, stable ranking.
        fit=model.analyze(v|{'w_rent':'0','w_startup':'0','w_fit':'5','w_facility':'5','w_area':'5','w_traffic':'0'},'a').result
        self.assertEqual(fit['metrics'][0][1],'가상 역세권 A')
        self.assertEqual(fit['metrics'][1][1],100)
        self.assertEqual(fit['metrics'][3][1],0)
        # Defaults are a close call: rent weight 0 or facility weight 5 flips B to A.
        close=model.analyze(v,'a').result
        self.assertEqual(close['metrics'][0][1],'가상 주거지 B')
        self.assertEqual(close['metrics'][3][1],2)
        self.assertTrue(any('월 임대료 중요도 0' in note for note in close['notes']))

    def test_all_zero_weights_rejected(self):
        model=model_for('property')
        zero={name:'0' for name in ('w_rent','w_startup','w_area','w_fit','w_traffic','w_facility')}
        with self.assertRaises(ValidationError):
            model.analyze(model.defaults()|zero,'a')

    def test_wizard_markup_and_declared_step_order(self):
        html=self.standalone_client().get(self.module_path).get_data(as_text=True)
        self.assertIn('data-wizard',html)
        self.assertEqual(html.count('class="wizard-step"'),5)
        order=[html.index(f'data-step-title="{t}"') for t in ('기본 조건','공통 초기 자금','후보 A','후보 B','평가 기준 중요도')]
        self.assertEqual(order,sorted(order))


if __name__ == "__main__":
    unittest.main()
