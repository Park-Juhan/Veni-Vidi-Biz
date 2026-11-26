"""KAMIS monthly retail prices: import, name matching and comparison in the material list (02)."""
import csv
from decimal import Decimal
from html import unescape
from pathlib import Path
import tempfile
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.modules.material_cost.repositories.catalog import MaterialCatalog
from app.reference.kamis import KamisPrices, base_of, import_file, is_kamis
from tests.module_support import model_for

HEADER = ['월', '지역', '부류', '품목', '품종', '단위', '등급', '월평균가격']
ROWS = [
    ['2025-10', '전국', '', '양파', '양파', '1kg', '상품', '2,000'],
    ['2026-10', '전국', '', '양파', '양파', '1kg', '상품', '2,500'],
    ['2026-10', '서울', '', '양파', '양파', '1kg', '상품', '2,600'],
    ['2026-10', '전국', '', '양파', '양파', '1kg', '중품', '2,100'],
    ['2026-10', '전국', '', '깐마늘(국산)', '깐마늘(국산)', '1kg', '상품', '12000'],
    ['2026-10', '전국', '', '레몬', '수입', '10개', '상품', '8000'],
    ['2026-10', '전국', '', '배추', '배추', '1포기', '상품', '4000'],
    ['2026-10', '전국', '가공식품', '간장', '샘표 양조간장 1.7L', '1개', '상품', '15000'],
    ['2026-10', '전국', '', '오이', '가시계통', '10개', '상품', '-'],  # no price: skipped
]


def write_prices(folder):
    path = Path(folder) / 'KAMIS_소매가격_월별_2025-10_2026-10.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(ROWS)
    return path


def loaded_prices():
    database = Database.in_memory()
    database.migrate()
    with tempfile.TemporaryDirectory() as folder:
        import_file(database, write_prices(folder))
    return database, KamisPrices(database)


class KamisTests(unittest.TestCase):
    def test_units_and_file_names(self):
        self.assertEqual(base_of('1kg'), ('g', Decimal(1000)))
        self.assertEqual(base_of('500g'), ('g', Decimal(500)))
        self.assertEqual(base_of('10개'), ('개', Decimal(10)))
        self.assertEqual(base_of('1.5L'), ('mL', Decimal(1500)))
        self.assertIsNone(base_of('1포기'))
        self.assertTrue(is_kamis('KAMIS_소매가격_월별_2023-11_2026-10.csv'))
        self.assertFalse(is_kamis('서울시 상권분석서비스(점포-상권).csv'))

    def test_import_suggest_and_quote(self):
        database, prices = loaded_prices()
        with database.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM price_series').fetchone()[0], 8)
        self.assertEqual(prices.suggest('양파', 'g'), '양파|양파|1kg|상품')        # 상품 grade preferred
        self.assertEqual(prices.suggest('마늘', 'g'), '깐마늘(국산)|깐마늘(국산)|1kg|상품')
        self.assertEqual(prices.suggest('레몬', '개'), '레몬|수입|10개|상품')
        self.assertIsNone(prices.suggest('원두', 'g'))
        quote = prices.quote('양파|양파|1kg|상품')
        self.assertEqual((quote.month, quote.price, quote.seoul_price, quote.year_ago_price), ('2026-10', 2500, 2600, 2000))
        self.assertEqual((quote.base_unit, quote.price_per_base), ('g', Decimal('2.5')))
        self.assertEqual(prices.quote('배추|배추|1포기|상품').price_per_base, None)
        self.assertIn('간장 · 샘표 양조간장 1.7L · 1개 · 상품', [o.label for o in prices.options()])


class MaterialMarketTests(unittest.TestCase):
    def setUp(self):
        database, self.prices = loaded_prices()
        self.model = model_for('material_cost')
        self.model.catalog = MaterialCatalog(database)
        self.model.price_provider = self.prices

    def save(self, **values):
        return self.model.save_material('w', self.model.defaults() | values)

    def item(self, name):
        return next(i for i in self.model.list_materials('w') if i['name'] == name)

    def test_auto_match_gap_and_trend(self):
        self.save(name='양파', purchase_price='30000', quantity='1', unit='kg', usage='100', usage_unit='g', yield_rate='90')  # far too dear
        self.save(name='양파', purchase_price='2000', quantity='10', unit='kg', usage='100', usage_unit='g', yield_rate='90')
        market = self.item('양파')['market']
        self.assertTrue(market['auto'])
        # 2,000원/kg = 2원/g against 2.5원/g: 20% cheaper (yield is not applied to either side).
        self.assertEqual((market['mine_per_base'], market['per_base'], market['gap']), (Decimal(2), Decimal('2.5'), Decimal(-20)))
        self.assertEqual(market['change'], Decimal(25))  # 2,000 -> 2,500 over a year
        self.assertEqual(market['seoul_price'], 2600)

    def test_manual_link_off_and_incomparable_units(self):
        material_id = self.save(name='레몬즙용 레몬', purchase_price='1000', quantity='5', unit='개', usage='1', usage_unit='개')
        self.assertEqual(self.item('레몬즙용 레몬')['market']['label'], '레몬 · 수입 · 10개 · 상품')  # name contains 레몬
        self.assertEqual(self.item('레몬즙용 레몬')['market']['gap'], Decimal(25))                  # 1,000 vs 800 per 개
        self.assertTrue(self.model.set_market_item('w', material_id, '배추 · 1포기 · 상품'))
        market = self.item('레몬즙용 레몬')['market']
        self.assertFalse(market['auto'])
        self.assertIsNone(market['gap'])  # 개 vs 포기: not comparable
        self.model.set_market_item('w', material_id, 'none')
        self.assertIsNone(self.item('레몬즙용 레몬')['market'])
        self.model.set_market_item('w', material_id, 'auto')
        self.assertTrue(self.item('레몬즙용 레몬')['market']['auto'])
        with self.assertRaises(ValidationError):
            self.model.set_market_item('w', material_id, '없는 품목')
        self.assertFalse(self.model.set_market_item('other', material_id, 'auto'))  # another workspace

    def test_menu_contract_skips_market_lookups(self):
        self.save(name='양파', purchase_price='2000', quantity='1', unit='kg', usage='100', usage_unit='g')
        [item] = self.model.list_material_costs('w')
        self.assertEqual((item.name, item.base_unit), ('양파', 'g'))


class MarketHttpTests(unittest.TestCase):
    def setUp(self):
        _, prices = loaded_prices()
        self.client = create_app({'TESTING': True, 'MARKET_PRICES': prices}).test_client()
        self.client.get('/material-cost/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def post(self, data, **kwargs):
        return unescape(self.client.post('/material-cost/', data=data | {'csrf': self.token}, **kwargs).get_data(as_text=True))

    def test_list_shows_market_and_link_form(self):
        self.post(model_for('material_cost').defaults() | {'name': '양파', 'purchase_price': '3000', 'quantity': '1', 'unit': 'kg',
                                                           'usage': '100', 'usage_unit': 'g', 'save_material': 'yes'}, follow_redirects=True)
        page = unescape(self.client.get('/material-cost/').get_data(as_text=True))
        self.assertIn('양파 · 1kg · 상품 <small>(자동)</small>', page)
        self.assertIn('+20%', page)  # 3원/g vs 2.5원/g
        self.assertIn('<option value="깐마늘(국산) · 1kg · 상품">', page)
        material_id = page.split('name="material_id" value="')[1].split('"')[0]
        bad = self.post({'action': 'set_market', 'material_id': material_id, 'market_choice': 'pick', 'market_item': '없는 품목'})
        self.assertIn("시세 품목 '없는 품목'을(를) 찾지 못했습니다", bad)
        done = self.post({'action': 'set_market', 'material_id': material_id, 'market_choice': 'pick', 'market_item': '양파 · 1kg · 중품'})
        self.assertIn('시세 품목을 연결했습니다', done)
        self.assertIn('2,100원 / 1kg', done)
        off = self.post({'action': 'set_market', 'material_id': material_id, 'market_choice': 'none'})
        self.assertIn('비교 안 함', off)

    def test_without_prices_no_market_columns(self):
        client = create_app({'TESTING': True}).test_client()
        self.assertNotIn('소매 시세 (전국)', client.get('/material-cost/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
