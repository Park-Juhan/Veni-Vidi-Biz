"""KAMIS monthly retail prices: import, name matching and comparison in the material list (02)."""
import csv
from decimal import Decimal
from html import unescape
from pathlib import Path
import tempfile
import unittest

from app.common.db import Database
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

    def test_retail_reference_trend_and_advice(self):
        record = self.model.analyze(self.model.defaults() | {'dish': '김치찌개'}, 'w')
        rows = {row[0]: row for row in record.result['rows']}
        # Applied price stays the assumed 업소용 1.5원/g; retail 2,500원/kg is shown with its one-year change.
        self.assertEqual(rows['양파'][3], '1.5원/g')
        self.assertEqual(rows['양파'][4], '2.5원/g (2026-10) · 1년 +25%')
        self.assertEqual(rows['김치'][4], '-')                       # no retail series in this file
        self.assertTrue(any('양파 소매 시세가 1년 새 25% 올랐습니다' in line for line in record.result['advice']))
        self.assertEqual(record.result['metrics'][3][1], '1 / 7')

    def test_material_list_compares_with_retail(self):
        self.model.remember('w', self.model.analyze(self.model.defaults() | {'dish': '김치찌개'}, 'w'))
        onion = next(i for i in self.model.list_materials('w') if i['name'] == '양파')
        self.assertEqual((onion['unit'], onion['unit_price']), ('kg', Decimal(1500)))
        self.assertEqual((onion['market']['gap'], onion['market']['change']), (Decimal(-40), Decimal(25)))
        [item] = [i for i in self.model.list_material_costs('w') if i.name == '양파']
        self.assertEqual((item.base_unit, item.cost_per_base_unit), ('g', Decimal('1.5') * 100 / 90))


class MarketHttpTests(unittest.TestCase):
    def setUp(self):
        _, prices = loaded_prices()
        self.client = create_app({'TESTING': True, 'MARKET_PRICES': prices}).test_client()
        self.client.get('/material-cost/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def test_result_and_list_show_retail_prices(self):
        self.client.post('/material-cost/', data=model_for('material_cost').defaults() | {'dish': '김치찌개', 'csrf': self.token})
        page = unescape(self.client.get('/material-cost/').get_data(as_text=True))
        self.assertIn('음식을 고르면 재료와 원가를 공공 시세로 계산합니다', page)
        self.assertIn('2.5원/g (2026-10) · 1년 +25%', page)
        self.assertIn('+25% <small class="market-sub">양파</small>', page)

    def test_without_prices_no_retail_reference(self):
        client = create_app({'TESTING': True}).test_client()
        self.assertIn('표준 레시피로 재료와 원가를 계산합니다', client.get('/material-cost/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
