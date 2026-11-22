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

    def test_topsis_ranks_within_budget_and_area_groups(self):
        model=model_for('property')
        result=model.analyze(model.defaults(),'a').result
        scores={row[0]:row[6] for row in result['rows']}
        # A is closer to the ideal but over the rent budget, so B (meets all conditions) ranks first.
        self.assertGreater(scores['가상 역세권 A'],scores['가상 주거지 B'])
        self.assertEqual(result['rows'][0][0],'가상 주거지 B')
        self.assertAlmostEqual(sum(scores.values()),Decimal(100),places=10)
        # Once both fit the budget, TOPSIS decides; heavier customer-fit weight widens A's lead.
        relaxed=model.analyze(model.defaults()|{'budget':'2000000'},'a').result
        self.assertEqual(relaxed['metrics'][0][1],'가상 역세권 A')
        weighted=model.analyze(model.defaults()|{'budget':'2000000','w_fit':'80','w_rent':'0','w_startup':'0'},'a').result
        self.assertGreater(weighted['rows'][0][6],relaxed['rows'][0][6])
        criteria=weighted['extra_tables'][0]['rows']
        self.assertEqual(sum(row[1] for row in criteria).quantize(Decimal(1)),Decimal(100))

    def test_topsis_requires_some_weight(self):
        model=model_for('property')
        with self.assertRaises(ValidationError):
            model.analyze(model.defaults()|{f'w_{key}':'0' for key in ('fit','traffic','facility','rent','startup','area')},'a')


if __name__ == "__main__":
    unittest.main()
