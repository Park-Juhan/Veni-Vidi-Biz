"""Monthly menu sales with menu engineering (03) and monthly financial records (05)."""
from decimal import Decimal
from html import unescape
import re
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.modules.cost_optimization.repositories.financials import FinancialStore
from app.modules.material_cost.repositories.dishes import DishStore
from app.modules.menu_pricing.repositories.recipes import RecipeStore
from app.modules.menu_pricing.repositories.sales import SalesStore
from tests.module_support import model_for


def menu_setup():
    """Three dishes from 02 priced in 03: 아메리카노 (450원), 카페라떼 (978원), 크로플."""
    database = Database.in_memory()
    database.migrate()
    material = model_for('material_cost')
    material.dishes = DishStore(database)
    menu = model_for('menu_pricing')
    menu.dish_provider, menu.recipes, menu.sales = material, RecipeStore(database), SalesStore(database)
    for dish, other in (('아메리카노', '200'), ('카페라떼', '300'), ('크로플', '0')):
        material.remember('w', material.analyze(material.defaults() | {'dish': dish}, 'w'))
        menu.remember('w', menu.analyze(menu.defaults() | {'dish': dish, 'other': other}, 'w'))
    menus = {m['name']: m['id'] for m in menu.list_menus('w')}
    costs = {d.name: d.cost_per_serving for d in material.list_dishes('w')}
    return menu, menus, costs


class MenuEngineeringTests(unittest.TestCase):
    def test_classifies_by_popularity_and_unit_margin(self):
        menu, ids, cost = menu_setup()
        self.assertEqual((cost['아메리카노'], cost['카페라떼']), (Decimal(450), Decimal(978)))
        menu.save_sales('w', '2026-10', [(ids['아메리카노'], '600', '4000'), (ids['카페라떼'], '300', '5500'), (ids['크로플'], '100', '1500')])
        result = menu.menu_engineering('w', '2026-10')
        rows = {row['name']: row for row in result['rows']}
        margins = {'아메리카노': 4000 - cost['아메리카노'] - 200, '카페라떼': 5500 - cost['카페라떼'] - 300, '크로플': 1500 - cost['크로플']}
        self.assertEqual({n: rows[n]['margin'] for n in margins}, margins)
        self.assertEqual(result['revenue'], Decimal(600 * 4000 + 300 * 5500 + 100 * 1500))
        self.assertEqual(result['material'], 600 * cost['아메리카노'] + 300 * cost['카페라떼'] + 100 * cost['크로플'])
        average = (600 * margins['아메리카노'] + 300 * margins['카페라떼'] + 100 * margins['크로플']) / 1000
        self.assertEqual(result['average_margin'], average)
        self.assertEqual(rows['아메리카노']['label'], '스타')          # 60% share, 3,350 >= average
        self.assertEqual(rows['카페라떼']['label'], '스타')
        self.assertEqual(rows['크로플']['label'], '저인기·저수익')     # 10% share, low margin
        self.assertEqual(result['rows'][0]['name'], '아메리카노')      # sorted by total margin

    def test_sales_validation_and_replacement(self):
        menu, ids, _ = menu_setup()
        for period, rows in (('2026-13', [(ids['크로플'], '1', '1000')]), ('2026-10', [(ids['크로플'], '-1', '1000')]),
                             ('2026-10', [(ids['크로플'], '1.5', '1000')]), ('2026-10', [(ids['크로플'], '1', 'abc')]),
                             ('2026-10', [(ids['크로플'], '', '1000')])):
            with self.subTest(period=period, rows=rows), self.assertRaises(ValidationError):
                menu.save_sales('w', period, rows)
        menu.save_sales('w', '2026-10', [(ids['크로플'], '10', '1500'), (ids['카페라떼'], '5', '5500')])
        menu.save_sales('w', '2026-10', [(ids['크로플'], '20', '1500')])  # same month replaces
        self.assertEqual(set(menu.sales_for('w', '2026-10')), {ids['크로플']})
        self.assertEqual(menu.sales_periods('w'), ['2026-10'])
        self.assertEqual(menu.latest_prices('w'), {ids['크로플']: Decimal(1500)})
        self.assertEqual(menu.sales_periods('other'), [])
        self.assertTrue(menu.delete_sales('w', '2026-10'))
        self.assertEqual(menu.sales_periods('w'), [])

    def test_operating_cost_export_prefers_latest_sales_month(self):
        menu, ids, cost = menu_setup()
        menu.save_sales('w', '2026-09', [(ids['크로플'], '10', '1500')])
        menu.save_sales('w', '2026-10', [(ids['아메리카노'], '100', '4000'), (ids['크로플'], '50', '1500')])
        snapshot = menu.export_operating_costs('w')
        self.assertEqual(snapshot.monthly_revenue, Decimal(100 * 4000 + 50 * 1500))
        self.assertEqual(snapshot.monthly_material, 100 * cost['아메리카노'] + 50 * cost['크로플'])
        self.assertIn('2026-10 판매 기록', snapshot.detail)


class MonthlyFinancialTests(unittest.TestCase):
    def setUp(self):
        database = Database.in_memory()
        database.migrate()
        self.model = model_for('cost_optimization')
        self.model.financials = FinancialStore(database)

    def test_months_profit_change_and_previous_total(self):
        defaults = self.model.defaults()  # revenue 12M, total cost 8M
        self.model.save_month('w', '2026-09', defaults)
        self.model.save_month('w', '2026-10', defaults | {'revenue': '13000000', 'rent': '1600000'})
        october, september = self.model.list_months('w')
        self.assertEqual((october['period'], october['total'], october['profit']), ('2026-10', Decimal(8100000), Decimal(4900000)))
        self.assertEqual(october['profit_change'], Decimal(900000))
        self.assertNotIn('profit_change', september)
        self.assertEqual(self.model.previous_total('w', '2026-10'), ('2026-09', Decimal(8000000)))
        self.assertEqual(self.model.previous_total('w', '2026-09'), None)
        self.assertEqual(self.model.month_values('w', '2026-10')['previous'], '8000000')
        imported = self.model.import_operating_costs('w', '2026-11')
        self.assertEqual(imported['values']['previous'], '8100000')
        self.assertIn('2026-10', imported['origins']['previous'])
        with self.assertRaises(ValidationError):
            self.model.save_month('w', 'October', defaults)


class SalesAndMonthsHttpTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({'TESTING': True}).test_client()
        self.client.get('/material-cost/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def post(self, path, data, **kwargs):
        return self.client.post(path, data=data | {'csrf': self.token}, **kwargs)

    def test_sales_flow_feeds_cost_import_and_month_history(self):
        page = self.client.get('/menu-pricing/').get_data(as_text=True)
        self.assertNotIn('월별 판매 기록', page)  # needs a priced menu first
        self.post('/material-cost/', model_for('material_cost').defaults() | {'dish': '아메리카노'})
        self.post('/menu-pricing/', model_for('menu_pricing').defaults() | {'dish': '아메리카노'})
        page = self.client.get('/menu-pricing/').get_data(as_text=True)
        menu_id = re.search(r'name="sales_qty_(\d+)"', page).group(1)

        bad = unescape(self.post('/menu-pricing/', {'action': 'save_sales', 'sales_period': '2026-10', f'sales_qty_{menu_id}': '-3', f'sales_price_{menu_id}': '4500'}).get_data(as_text=True))
        self.assertIn('판매량은 0 이상의 정수', bad)
        self.assertIn(f'name="sales_qty_{menu_id}" type="number" min="0" step="1" inputmode="numeric" value="-3"', bad)  # typed value kept

        page = unescape(self.post('/menu-pricing/', {'action': 'save_sales', 'sales_period': '2026-10', f'sales_qty_{menu_id}': '1000', f'sales_price_{menu_id}': '4500'}).get_data(as_text=True))
        self.assertIn('2026-10 판매 기록 1개 메뉴를 저장했습니다', page)
        self.assertIn('2026-10 메뉴 분석', page)
        self.assertIn('스타', page)  # a single menu is both popular and at the average margin

        cost_defaults = model_for('cost_optimization').defaults()
        imported = unescape(self.post('/cost-optimization/', cost_defaults | {'action': 'import', 'period': '2026-10'}).get_data(as_text=True))
        self.assertIn('id="revenue" name="revenue" type="number" value="4500000"', imported)
        self.assertIn('id="material" name="material" type="number" value="450000"', imported)  # 1000 x 450
        self.assertIn('2026-10 판매 기록', imported)

        page = unescape(self.post('/cost-optimization/', cost_defaults | {'period': '2026-10', 'save_month': 'yes'}, follow_redirects=True).get_data(as_text=True))
        self.assertIn('2026-10 매출·비용을 월별 기록에 저장했습니다', page)
        self.assertIn('<td><b>2026-10</b></td>', page)
        self.assertEqual(self.post('/cost-optimization/', cost_defaults | {'save_month': 'yes', 'period': ''}).status_code, 422)

        loaded = unescape(self.post('/cost-optimization/', {'action': 'load_month', 'month': '2026-10'}).get_data(as_text=True))
        self.assertIn('2026-10 기록을 불러왔습니다', loaded)
        deleted = unescape(self.post('/cost-optimization/', {'action': 'delete_month', 'month': '2026-10'}).get_data(as_text=True))
        self.assertIn('저장한 달이 없습니다', deleted)


if __name__ == '__main__':
    unittest.main()
