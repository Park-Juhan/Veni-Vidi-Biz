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

    def test_demand_model_matches_lerner_rule(self):
        model=model_for('menu_pricing')
        r=model.analyze(model.defaults()|{'elasticity':'높음 2.5 · 주변에 대체 메뉴 많음'},'a').result
        # Optimal price = cost × e / (e - 1) = 1500 × 2.5 / 1.5.
        self.assertEqual(r['metrics'][2][1],Decimal(2500))
        self.assertEqual(r['rows'][2][2],Decimal(4347))   # 1000 × (2500/4500)^-2.5
        self.assertTrue(any('2배를 넘습니다' in n for n in r['notes']))
        self.assertEqual(r['model'],'가격탄력성 수요 모델')

    def test_higher_price_lowers_volume_and_low_elasticity_hits_cap(self):
        model=model_for('menu_pricing')
        r=model.analyze(model.defaults()|{'elasticity':'낮음 0.8 · 단골·대체 메뉴 적음'},'a').result
        self.assertLess(r['rows'][2][2],r['rows'][0][2])
        self.assertEqual(r['metrics'][2][1],Decimal(9000))
        self.assertTrue(any('탐색 상한' in n for n in r['notes']))

    def test_zero_price_falls_back_to_constant_volume(self):
        model=model_for('menu_pricing')
        r=model.analyze(model.defaults()|{'price':'0'},'a').result
        self.assertEqual(len(r['rows']),2)
        self.assertEqual(r['rows'][1][2],Decimal(1000))
        self.assertTrue(any('수요 반응 모델을 적용할 수 없습니다' in n for n in r['notes']))


if __name__ == "__main__":
    unittest.main()
