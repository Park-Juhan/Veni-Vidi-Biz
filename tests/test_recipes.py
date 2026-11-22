"""Saved materials (02) and recipe costing with saved menus (03)."""
from decimal import Decimal
from html import unescape
import re
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.modules.material_cost.repositories.catalog import MaterialCatalog
from app.modules.menu_pricing.repositories.recipes import RecipeStore
from tests.module_support import model_for


def models():
    database = Database.in_memory()
    database.migrate()
    material = model_for('material_cost')
    material.catalog = MaterialCatalog(database)
    menu = model_for('menu_pricing')
    menu.material_catalog = material
    menu.recipes = RecipeStore(database)
    return material, menu


class CatalogAndRecipeModelTests(unittest.TestCase):
    def test_saving_same_material_records_purchase_history(self):
        material, _ = models()
        defaults = material.defaults()  # 원두 20,000원/kg, 2kg, yield 100
        material.save_material('w', defaults)
        material.save_material('w', defaults | {'purchase_price': '24000', 'yield_rate': '80'})
        [item] = material.list_materials('w')
        self.assertEqual((item['name'], item['purchases'], item['unit_price']), ('원두', 2, Decimal(24000)))
        self.assertEqual(item['base_unit'], 'g')
        self.assertEqual(item['cost_per_base_unit'], Decimal(30))  # 24,000 / 1000g / 0.8
        self.assertEqual(material.list_materials('other'), [])

    def test_recipe_cost_sums_materials_and_reports_row_errors(self):
        material, menu = models()
        material.save_material('w', material.defaults())  # 원두 20원/g
        material.save_material('w', material.defaults() | {'name': '우유', 'purchase_price': '2500', 'quantity': '1', 'unit': 'L', 'usage': '200', 'usage_unit': 'mL'})
        ids = {item.name: str(item.material_id) for item in menu.materials('w')}
        total, items, description = menu.recipe_cost('w', [(ids['원두'], '18'), ('', ''), (ids['우유'], '200')])
        self.assertEqual(total, Decimal(860))  # 18g x 20 + 200mL x 2.5
        self.assertEqual(len(items), 2)
        self.assertEqual(description, '원두 18g + 우유 200mL')
        for rows in ([('', '18')], [(ids['원두'], 'abc')], [(ids['원두'], '0')], [(ids['원두'], '1'), (ids['원두'], '2')], [('', '')], [('999', '1')]):
            with self.subTest(rows=rows), self.assertRaises(ValidationError):
                menu.recipe_cost('w', rows)
        # Other workspaces cannot use this workspace's materials.
        with self.assertRaises(ValidationError):
            menu.recipe_cost('other', [(ids['원두'], '18')])

    def test_saved_menu_follows_current_prices_and_material_deletion(self):
        material, menu = models()
        material.save_material('w', material.defaults())
        [bean] = menu.materials('w')
        _, items, _ = menu.recipe_cost('w', [(str(bean.material_id), '18')])
        menu.save_recipe('w', '아메리카노', items)
        menu.save_recipe('w', '아메리카노', items)  # same name replaces, not duplicates
        [saved] = menu.list_menus('w')
        self.assertEqual(saved['cost'], Decimal(360))
        material.save_material('w', material.defaults() | {'purchase_price': '30000'})
        self.assertEqual(menu.list_menus('w')[0]['cost'], Decimal(540))
        material.delete_material('w', bean.material_id)
        self.assertEqual(menu.list_menus('w')[0]['items'], [])


class RecipeHttpTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({'TESTING': True}).test_client()
        self.client.get('/material-cost/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def post(self, path, data, **kwargs):
        return self.client.post(path, data=data | {'csrf': self.token}, **kwargs)

    def test_save_material_then_cost_menu_by_recipe(self):
        page = self.post('/material-cost/', model_for('material_cost').defaults() | {'save_material': 'yes'}, follow_redirects=True).get_data(as_text=True)
        self.assertIn('내 재료 목록에 저장했습니다', page)
        self.assertIn('20원 / g', unescape(page))
        menu_page = self.client.get('/menu-pricing/').get_data(as_text=True)
        bean_id = re.search(r'<option value="(\d+)"[^>]*>원두', menu_page).group(1)

        menu_defaults = model_for('menu_pricing').defaults()
        page = self.post('/menu-pricing/', menu_defaults | {'name': '진한 아메리카노', 'use_recipe': 'yes', 'recipe_material_0': bean_id, 'recipe_qty_0': '20'},
                         follow_redirects=True).get_data(as_text=True)
        self.assertIn('레시피를 저장했습니다', page)
        self.assertIn('레시피 합산 (내 재료 목록 단가): 원두 20g', page)
        self.assertIn('id="material" name="material" type="number" value="400"', page)  # 20g x 20원
        menu_id = re.search(r'name="menu_id" value="(\d+)"', page).group(1)

        # Loading the saved menu restores its recipe rows without calculating.
        page = unescape(self.post('/menu-pricing/', {'action': 'load_menu', 'menu_id': menu_id}).get_data(as_text=True))
        self.assertIn("메뉴 '진한 아메리카노'의 레시피를 불러왔습니다", page)
        self.assertIn('name="recipe_qty_0" type="number" min="0" step="any" inputmode="decimal" value="20"', page)

        # Choosing both the single-material import and the recipe is rejected.
        response = self.post('/menu-pricing/', menu_defaults | {'use_material': 'yes', 'use_recipe': 'yes', 'recipe_material_0': bean_id, 'recipe_qty_0': '1'})
        self.assertEqual(response.status_code, 422)

        page = self.post('/menu-pricing/', {'action': 'delete_menu', 'menu_id': menu_id}).get_data(as_text=True)
        self.assertIn('메뉴 레시피를 삭제했습니다', page)
        self.assertIn('저장한 메뉴가 없습니다', page)

    def test_workspace_delete_clears_saved_lists(self):
        self.post('/material-cost/', model_for('material_cost').defaults() | {'save_material': 'yes'})
        self.assertNotIn('아직 저장한 재료가 없습니다', self.client.get('/material-cost/').get_data(as_text=True))
        self.post('/workspace/', {'action': 'delete', 'confirm': 'yes'})
        self.assertIn('아직 저장한 재료가 없습니다', self.client.get('/material-cost/').get_data(as_text=True))

    def test_menu_module_alone_hides_recipe(self):
        client = create_app({'TESTING': True}, enabled_modules=['menu_pricing']).test_client()
        self.assertNotIn('레시피 원가 계산', client.get('/menu-pricing/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
