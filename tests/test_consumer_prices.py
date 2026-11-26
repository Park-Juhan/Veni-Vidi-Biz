"""Consumer price files (참가격, 서울 시장·마트 조사): parsing, monthly medians and use next to KAMIS."""
import csv
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from app.common.db import Database
from app.reference import consumer_prices, kamis
from app.reference.consumer_prices import month_of, source_of, split_size
from app.reference.kamis import KamisPrices

SEOUL_HEADER = ['일련번호', '시장/마트 번호', '시장/마트 이름', '품목 번호', '품목 이름', '실판매규격', '가격(원)', '년도-월', '비고',
                '시장유형 구분(시장/마트) 코드', '시장유형 구분(시장/마트) 이름', '자치구 코드', '자치구 이름', '점검일자']


def seoul_row(item, price, month, kind='전통시장'):
    return ['1', '1', '시장', '1', item, '', price, month, '', '001', kind, '1', '구', '']


def write(folder, name, header, rows, encoding='cp949'):
    path = Path(folder) / name
    with path.open('w', encoding=encoding, newline='') as handle:
        writer = csv.writer(handle); writer.writerow(header); writer.writerows(rows)
    return path


class ParsingTests(unittest.TestCase):
    def test_split_size_and_month(self):
        self.assertEqual(split_size('백설 하얀설탕(1kg)'), ('백설 하얀설탕', '1kg'))
        self.assertEqual(split_size(' 돼지고기 100g'), ('돼지고기', '100g'))
        self.assertEqual(split_size('남양 맛있는우유GT(900ml)'), ('남양 맛있는우유GT', '900mL'))
        self.assertEqual(split_size('라면 5개입 1봉'), ('라면', '5개'))
        self.assertEqual(split_size('소주 360ml, 1병'), ('소주', '360mL'))
        self.assertEqual(split_size('배추(봄) 1포기'), ('배추(봄)', '1포기'))
        self.assertEqual(split_size('CJ 동치미물냉면(4인)'), ('CJ 동치미물냉면(4인)', '-'))
        self.assertEqual((month_of('Jan-24'), month_of('2025-03'), month_of('2026-10-09'), month_of('x')), ('2024-01', '2025-03', '2026-10', None))
        self.assertEqual(source_of('한국소비자원_생필품_가격정보_20261023.csv'), '참가격')
        self.assertEqual(source_of('서울시_생필품_농수축산물_가격정보_2025.csv'), '서울시장')
        self.assertIsNone(source_of('KAMIS_소매가격_월별_2023-11_2026-10.csv'))


class ImportTests(unittest.TestCase):
    def test_medians_sources_and_matching(self):
        database = Database.in_memory(); database.migrate()
        with tempfile.TemporaryDirectory() as folder:
            seoul = [write(folder, '서울시_생필품_농수축산물_가격정보_2024.csv', SEOUL_HEADER, [
                         seoul_row('돼지고기 100g', '2,500', 'Dec-24'), seoul_row('돼지고기 100g', '0', 'Dec-24')]),
                     write(folder, '서울시_생필품_농수축산물_가격정보_2025.csv', SEOUL_HEADER, [
                         seoul_row('돼지고기 100g', '2800', '2025-12'), seoul_row('돼지고기 100g', '3000', '2025-12'),
                         seoul_row('돼지고기 100g', '3400', '2025-12'), seoul_row('계란 10개', '4300', '2025-12', '대형마트')])]
            brand = write(folder, '한국소비자원_생필품_가격정보_20261023.csv', ['상품명', '조사일', '판매가격', '판매업소', '제조사', '세일여부', '원플러스원'], [
                ['백설 하얀설탕(1kg)', '2026-10-09', '3000', 'A', '대형마트', '', ''], ['백설 하얀설탕(1kg)', '2026-10-23', '3400', 'B', '슈퍼마켓', '', '']])
            kamis_file = write(folder, 'KAMIS_소매가격_월별_2026-10.csv', ['월', '지역', '부류', '품목', '품종', '단위', '등급', '월평균가격'],
                               [['2026-10', '전국', '', '양파', '양파', '1kg', '상품', '2160']], encoding='utf-8-sig')
            kamis.import_file(database, kamis_file)
            self.assertEqual(consumer_prices.import_files(database, seoul)[1], 3)   # pork Dec-24, pork Dec-25, eggs
            consumer_prices.import_files(database, [brand])
            kamis.import_file(database, kamis_file)  # re-importing KAMIS keeps the other sources
        with database.connect() as connection:
            counts = dict(connection.execute('SELECT source, COUNT(*) FROM price_series GROUP BY source').fetchall())
        self.assertEqual(counts, {'KAMIS': 1, '서울시장': 3, '참가격': 1})
        prices = KamisPrices(database)
        pork = prices.quote(prices.suggest('돼지고기', 'g'))
        self.assertEqual((pork.month, pork.price, pork.year_ago_price), ('2025-12', 3000, 2500))  # median; zero price ignored
        self.assertEqual(pork.price_per_base, Decimal(30))
        self.assertEqual(pork.label, '돼지고기 · 서울 시장·마트 조사 · 100g · 전통시장')
        self.assertIn('서울특별시', pork.source)
        sugar = prices.quote(prices.suggest('설탕', 'g'))
        self.assertEqual((sugar.price, sugar.unit), (3200, '1kg'))  # median of 3,000 and 3,400
        self.assertEqual(prices.suggest('양파', 'g'), '양파|양파|1kg|상품')  # KAMIS stays first
        self.assertEqual(prices.quote(prices.suggest('계란', '개')).label, '계란 · 서울 시장·마트 조사 · 10개 · 대형마트')


if __name__ == '__main__':
    unittest.main()
