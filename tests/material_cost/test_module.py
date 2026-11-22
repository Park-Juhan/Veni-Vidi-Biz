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

    def test_yield_raises_usable_unit_cost(self):
        model=model_for('material_cost')
        result=model.analyze(model.defaults()|{'yield_rate':'80'},'a').result
        self.assertEqual(result['usage_cost'],Decimal(450))   # 360 / 0.8
        self.assertEqual(dict(result['chart'])['1회 사용분의 손질·폐기 손실'],Decimal(90))
        # 2kg bought at 1% yield leaves 20g usable, so 21g cannot be used.
        with self.assertRaises(ValidationError):
            model.analyze(model.defaults()|{'yield_rate':'1','usage':'21'},'a')
        for bad in ('0','101'):
            with self.subTest(yield_rate=bad),self.assertRaises(ValidationError):
                model.analyze(model.defaults()|{'yield_rate':bad},'a')


if __name__ == "__main__":
    unittest.main()
