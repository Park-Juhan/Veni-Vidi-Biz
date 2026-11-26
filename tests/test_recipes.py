"""Dishes analysed in 02 (standard recipes, saved dish list and material list) and their use in 03."""
from decimal import Decimal
from html import unescape
import re
import unittest

from app.common.db import Database
from app.main.application import create_app
from app.modules.material_cost.repositories.catalog import MaterialCatalog
from app.modules.material_cost.repositories.dishes import DishStore
from tests.module_support import model_for


def material_model():
    database = Database.in_memory()
    database.migrate()
    material = model_for('material_cost')
    material.catalog, material.dishes = MaterialCatalog(database), DishStore(database)
    return material


class DishModelTests(unittest.TestCase):
    def test_remember_saves_dish_and_monthly_purchases(self):
        material = material_model()
        material.remember('w', material.analyze(material.defaults() | {'dish': '카페라떼', 'monthly_volume': '900'}, 'w'))
        [dish] = material.list_dishes('w')
        self.assertEqual((dish.name, dish.cost_per_serving, dish.monthly_volume), ('카페라떼', Decimal(978), Decimal(900)))
        self.assertEqual([i.name for i in dish.ingredients], ['원두', '우유'])
        items = {m['name']: m for m in material.list_materials('w')}
        # 원두: 17 bags of 1kg at 25,000원/kg; 우유: 198 packs of 1L at 2,400원/L.
        self.assertEqual((items['원두']['unit'], items['원두']['unit_price'], items['원두']['quantity']), ('kg', Decimal(25000), Decimal(17)))
        self.assertEqual((items['우유']['unit'], items['우유']['unit_price'], items['우유']['quantity']), ('L', Decimal(2400), Decimal(198)))
        self.assertEqual(items['원두']['cost_per_base_unit'], Decimal(25))
        # Same dish again replaces it; purchases accumulate per material.
        material.remember('w', material.analyze(material.defaults() | {'dish': '카페라떼', 'monthly_volume': '300'}, 'w'))
        self.assertEqual([d.monthly_volume for d in material.list_dishes('w')], [Decimal(300)])
        self.assertEqual({m['name']: m['purchases'] for m in material.list_materials('w')}, {'원두': 2, '우유': 2})
        self.assertEqual(material.list_dishes('other'), [])
        self.assertTrue(material.delete_dish('w', material.list_dishes('w')[0].dish_id))
        self.assertEqual(material.list_dishes('w'), [])


class DishHttpTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({'TESTING': True}).test_client()
        self.client.get('/material-cost/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def post(self, path, data, **kwargs):
        return self.client.post(path, data=data | {'csrf': self.token}, **kwargs)

    def test_dish_list_material_list_and_delete(self):
        page = unescape(self.post('/material-cost/', model_for('material_cost').defaults() | {'dish': '김치찌개'}, follow_redirects=True).get_data(as_text=True))
        self.assertIn("'김치찌개'의 재료비를 저장했습니다", page)
        self.assertIn('계산한 메뉴', page)
        self.assertIn('내 재료 목록', page)
        self.assertIn('10kg 박스 × ', page)
        self.assertNotIn('시세 품목 연결', page)
        dish_id = re.search(r'name="action" value="delete_dish"><input type="hidden" name="item_id" value="(\d+)"', page).group(1)
        page = unescape(self.post('/material-cost/', {'action': 'delete_dish', 'item_id': dish_id}).get_data(as_text=True))
        self.assertIn('메뉴를 목록에서 삭제했습니다', page)
        self.assertNotIn('계산한 메뉴', page)

    def test_workspace_delete_clears_saved_lists(self):
        self.post('/material-cost/', model_for('material_cost').defaults())
        self.assertIn('내 재료 목록', self.client.get('/material-cost/').get_data(as_text=True))
        self.post('/workspace/', {'action': 'delete', 'confirm': 'yes'})
        page = self.client.get('/material-cost/').get_data(as_text=True)
        self.assertNotIn('내 재료 목록', page)
        self.assertNotIn('계산한 메뉴', page)

    def test_menu_module_alone_takes_typed_cost(self):
        client = create_app({'TESTING': True}, enabled_modules=['menu_pricing']).test_client()
        page = client.get('/menu-pricing/').get_data(as_text=True)
        self.assertIn('재료비를 직접 입력합니다', page)
        self.assertNotIn('02에서 음식을 계산</a>', page)   # no link to a disabled module


if __name__ == '__main__':
    unittest.main()
