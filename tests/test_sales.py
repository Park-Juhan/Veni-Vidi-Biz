"""Monthly menu sales with menu engineering (03) and monthly financial records (05)."""
from decimal import Decimal
from html import unescape
import re
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.modules.cost_optimization.repositories.financials import FinancialStore
from app.modules.material_cost.repositories.catalog import MaterialCatalog
from app.modules.menu_pricing.repositories.recipes import RecipeStore
from app.modules.menu_pricing.repositories.sales import SalesStore
from tests.module_support import model_for


def menu_setup():
    """Three menus: 아메리카노 (원두 18g = 360원), 라떼 (원두 18g + 우유 200mL = 860원), 쿠키 (밀가루 50g = 100원)."""
    database = Database.in_memory()
    database.migrate()
    material = model_for('material_cost')
    material.catalog = MaterialCatalog(database)
    menu = model_for('menu_pricing')
    menu.material_catalog, menu.recipes, menu.sales = material, RecipeStore(database), SalesStore(database)
    material.save_material('w', material.defaults())
    material.save_material('w', material.defaults() | {'name': '우유', 'purchase_price': '2500', 'quantity': '1', 'unit': 'L'})
    material.save_material('w', material.defaults() | {'name': '밀가루', 'purchase_price': '2000', 'quantity': '1', 'unit': 'kg'})
    ids = {item.name: str(item.material_id) for item in menu.materials('w')}
    for name, rows, other in (('아메리카노', [(ids['원두'], '18')], '200'), ('라떼', [(ids['원두'], '18'), (ids['우유'], '200')], '300'),
                              ('쿠키', [(ids['밀가루'], '50')], '0')):
        menu.save_recipe('w', name, menu.recipe_cost('w', rows)[1], Decimal(other))
    menus = {m['name']: m['id'] for m in menu.list_menus('w')}
    return menu, menus


class MenuEngineeringTests(unittest.TestCase):
    def test_classifies_by_popularity_and_unit_margin(self):
        menu, ids = menu_setup()
        menu.save_sales('w', '2026-10', [(ids['아메리카노'], '600', '4000'), (ids['라떼'], '300', '5500'), (ids['쿠키'], '100', '1500')])
        result = menu.menu_engineering('w', '2026-10')
        rows = {row['name']: row for row in result['rows']}
        # Unit margins: 아메리카노 4000-(360+200)=3440, 라떼 5500-(860+300)=4340, 쿠키 1500-100=1400.
        self.assertEqual([rows[n]['margin'] for n in ('아메리카노', '라떼', '쿠키')], [Decimal(3440), Decimal(4340), Decimal(1400)])
        self.assertEqual(result['revenue'], Decimal(600 * 4000 + 300 * 5500 + 100 * 1500))
        self.assertEqual(result['material'], Decimal(600 * 360 + 300 * 860 + 100 * 100))
        # Popularity line = 100/3 * 0.7 = 23.3%; weighted average margin = (2,064,000+1,302,000+140,000)/1000 = 3506.
        self.assertEqual(result['average_margin'], Decimal(3506))
        self.assertEqual(rows['아메리카노']['label'], '인기·저수익')   # 60% share, 3440 < 3506
        self.assertEqual(rows['라떼']['label'], '스타')               # 30% share, 4340
        self.assertEqual(rows['쿠키']['label'], '저인기·저수익')       # 10% share, 1400
        self.assertEqual(result['rows'][0]['name'], '아메리카노')       # sorted by total margin

    def test_sales_validation_and_replacement(self):
        menu, ids = menu_setup()
        for period, rows in (('2026-13', [(ids['쿠키'], '1', '1000')]), ('2026-10', [(ids['쿠키'], '-1', '1000')]),
                             ('2026-10', [(ids['쿠키'], '1.5', '1000')]), ('2026-10', [(ids['쿠키'], '1', 'abc')]),
                             ('2026-10', [(ids['쿠키'], '', '1000')])):
            with self.subTest(period=period, rows=rows), self.assertRaises(ValidationError):
                menu.save_sales('w', period, rows)
        menu.save_sales('w', '2026-10', [(ids['쿠키'], '10', '1500'), (ids['라떼'], '5', '5500')])
        menu.save_sales('w', '2026-10', [(ids['쿠키'], '20', '1500')])  # same month replaces
        self.assertEqual(set(menu.sales_for('w', '2026-10')), {ids['쿠키']})
        self.assertEqual(menu.sales_periods('w'), ['2026-10'])
        self.assertEqual(menu.latest_prices('w'), {ids['쿠키']: Decimal(1500)})
        self.assertEqual(menu.sales_periods('other'), [])
        self.assertTrue(menu.delete_sales('w', '2026-10'))
        self.assertEqual(menu.sales_periods('w'), [])

    def test_operating_cost_export_prefers_latest_sales_month(self):
        menu, ids = menu_setup()
        menu.save_sales('w', '2026-09', [(ids['쿠키'], '10', '1500')])
        menu.save_sales('w', '2026-10', [(ids['아메리카노'], '100', '4000'), (ids['쿠키'], '50', '1500')])
        snapshot = menu.export_operating_costs('w')
        self.assertEqual(snapshot.monthly_revenue, Decimal(100 * 4000 + 50 * 1500))
        self.assertEqual(snapshot.monthly_material, Decimal(100 * 360 + 50 * 100))
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
        self.post('/material-cost/', model_for('material_cost').defaults() | {'save_material': 'yes'})
        page = self.client.get('/menu-pricing/').get_data(as_text=True)
        self.assertNotIn('월별 판매 기록', page)  # needs a saved menu first
        bean = re.search(r'<option value="(\d+)"[^>]*>원두', page).group(1)
        self.post('/menu-pricing/', model_for('menu_pricing').defaults() | {'use_recipe': 'yes', 'recipe_material_0': bean, 'recipe_qty_0': '18'})
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
        self.assertIn('id="material" name="material" type="number" value="360000"', imported)  # 1000 x 360
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
