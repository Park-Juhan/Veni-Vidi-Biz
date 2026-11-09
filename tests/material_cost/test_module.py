from decimal import Decimal
import unittest

from app.common.validation import ValidationError
from tests.module_support import StandaloneModuleChecks, model_for


class MaterialCostTests(StandaloneModuleChecks, unittest.TestCase):
    module_name = 'material_cost'

    def test_material_cost_and_conversion(self):
        model=model_for('material_cost')
        record=model.analyze(model.defaults(),'a')
        self.assertEqual(record.result['usage_cost'],Decimal(360))
        self.assertEqual(record.result['metrics'][0][1],Decimal(40000))
        snapshot=model.export_usage_cost('a')
        self.assertEqual(snapshot.usage_cost,Decimal(360))
        self.assertTrue(snapshot.updated_at)


    def test_volume_conversion(self):
        model=model_for('material_cost');v=model.defaults()
        v.update(unit='L',usage_unit='mL',purchase_price='3000',quantity='2',usage='200')
        self.assertEqual(model.analyze(v,'a').result['usage_cost'],Decimal(600))


    def test_material_rejects_dimension_mismatch_or_excess(self):
        model=model_for('material_cost')
        for changes in ({'usage_unit':'mL'},{'usage':'2001'},{'quantity':'0'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                model.analyze(model.defaults()|changes,'a')

    def test_eoq_order_plan_and_shelf_life_cap(self):
        model=model_for('material_cost')
        r=model.analyze(model.defaults(),'a').result
        # D = 3000 x 18g = 54kg/month, S = 3000, H = 20000 x 2% = 400 -> sqrt(810) kg.
        self.assertAlmostEqual(r['eoq'],Decimal(810).sqrt(),places=20)
        self.assertEqual(r['model'],'경제적 주문량 (EOQ) 모델')
        capped=model.analyze(model.defaults()|{'shelf_months':'0.25'},'a').result
        self.assertEqual(capped['eoq'],Decimal('13.5'))
        self.assertTrue(any('보관 가능 기간' in n for n in capped['notes']))
        self.assertIsNone(model.analyze(model.defaults()|{'monthly_uses':'0'},'a').result['eoq'])


if __name__ == "__main__":
    unittest.main()
