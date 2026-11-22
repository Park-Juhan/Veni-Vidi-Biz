from decimal import Decimal
from html import unescape
import re
import unittest

from app.main.application import create_app

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

    def test_import_operating_costs_from_other_modules(self):
        providers={name:model_for(name) for name in ('property','menu_pricing','marketing')}
        model=model_for('cost_optimization')
        model.cost_providers=tuple((name,provider) for name,provider in providers.items())
        empty=model.import_operating_costs('a')
        self.assertEqual(empty['values'],{})
        self.assertEqual(empty['missing'],['property','menu_pricing','marketing'])
        for provider in providers.values():
            provider.analyze(provider.defaults(),'a','가상 예시 · 실제 시장 자료 아님')
        imported=model.import_operating_costs('a')
        self.assertEqual(imported['missing'],[])
        # Defaults: candidate B ranks first (rent 1,200,000); menu 4,500 x 1,000 with material 1,200; budget 300,000.
        self.assertEqual(imported['values'],{'rent':'1200000','revenue':'4500000','material':'1200000','advertising':'300000'})
        self.assertIn('1순위 후보 가상 주거지 B',imported['origins']['rent'])
        self.assertIn('가상 예시',imported['origins']['revenue'])
        # Other workspaces see nothing.
        self.assertEqual(model.import_operating_costs('b')['values'],{})

    def test_import_action_fills_form_without_saving_and_credits_kept_values(self):
        client=create_app({'TESTING':True}).test_client()
        client.get('/property/')
        with client.session_transaction() as session:
            token=session['csrf']
        client.post('/property/',data=model_for('property').defaults()|{'csrf':token})
        cost_defaults=model_for('cost_optimization').defaults()
        response=client.post('/cost-optimization/',data=cost_defaults|{'csrf':token,'action':'import'})
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn('1개 값을 불러왔습니다',html)
        self.assertIn('id="rent" name="rent" type="number" value="1200000"',html)
        self.assertIn('계산 기록이 없어 건너뜀',html)
        self.assertNotIn('<table>',html)  # nothing calculated or saved yet
        hidden=re.search(r'name="import_rent" value="([^"]+)"',html).group(1)
        response=client.post('/cost-optimization/',data=cost_defaults|{'csrf':token,'rent':'1200000','import_rent':unescape(hidden)},follow_redirects=True)
        self.assertIn('다른 모듈 값 사용: 임대료 ← 01 부동산 및 업장 관리',response.get_data(as_text=True))
        # A value changed after import is not credited to the other module.
        response=client.post('/cost-optimization/',data=cost_defaults|{'csrf':token,'rent':'999','import_rent':unescape(hidden)},follow_redirects=True)
        self.assertNotIn('다른 모듈 값 사용',response.get_data(as_text=True))

    def test_standalone_module_hides_import(self):
        html=self.standalone_client().get(self.module_path).get_data(as_text=True)
        self.assertNotIn('다른 모듈에서 불러오기',html)

    def test_sensitivity_moves_one_factor_at_a_time(self):
        model=model_for('cost_optimization');table=model.analyze(model.defaults(),'a').result['extra_tables'][0]
        rows={row[0]:row for row in table['rows']}
        # Revenue 12M, material 2.5M (variable), total cost 8M -> base profit 4M.
        revenue=rows['매출 (재료비 함께 변동)']
        self.assertEqual(revenue[3],Decimal(4000000))
        self.assertEqual(revenue[1],Decimal(2100000))   # 9.6M - (8M - 0.5M)
        self.assertEqual(revenue[5],Decimal(5900000))   # 14.4M - (8M + 0.5M)
        self.assertEqual(rows['임대료'][5],Decimal(3700000))  # rent 1.5M +20%
        self.assertIn("'매출 (재료비 함께 변동)'",table['lead'])


if __name__ == "__main__":
    unittest.main()
