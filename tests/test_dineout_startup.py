"""Restaurant menu averages (03) and start-up cost / lease benchmarks (01)."""
import csv
from decimal import Decimal
from html import unescape
from pathlib import Path
import tempfile
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.reference import dineout, kosis
from app.reference.dineout import DineOutPrices
from app.reference.kosis import StartupBenchmarks
from tests.module_support import model_for


def loaded():
    database = Database.in_memory(); database.migrate()
    with tempfile.TemporaryDirectory() as folder:
        menu_file = Path(folder) / '외식비_시도별_2025-10_2026-10.csv'
        with menu_file.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle); writer.writerow(['월', '지역', '메뉴', '가격'])
            writer.writerows([['2026-10', '서울', '김치찌개 백반', '9000'], ['2025-10', '서울', '김치찌개 백반', '8000'],
                              ['2026-10', '부산', '김치찌개 백반', '8500'], ['2026-10', '서울', '냉면', '12000']])
        startup_file = Path(folder) / 'KOSIS_소상공인실태조사_창업비용_임차_2024.csv'
        with startup_file.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle); writer.writerow(kosis.STARTUP_COLUMNS)
            writer.writerows([['2024', '전국', '숙박 및 음식점업', '음식점 및 주점업', '20.0', '42.2', '37.8', '24.8', '51.4', '23.8', '2748', '101', '86'],
                              ['2024', '서울특별시', '숙박 및 음식점업', '소계', '0.4', '52.5', '47.1', '3.1', '58.1', '38.8', '2522', '115', '95']])
        assert dineout.is_dineout(menu_file) and kosis.is_startup(startup_file)
        dineout.import_file(database, menu_file)
        kosis.import_startup_file(database, startup_file)
    return DineOutPrices(database), StartupBenchmarks(database)


class DineOutTests(unittest.TestCase):
    def setUp(self):
        self.prices, _ = loaded()
        self.model = model_for('menu_pricing')
        self.model.dineout_provider = self.prices

    def test_quote_and_choices(self):
        self.assertEqual(self.prices.menus(), ['김치찌개 백반', '냉면'])
        self.assertEqual(self.prices.regions(), ['서울', '부산'])
        quote = self.prices.quote('김치찌개 백반', '서울')
        self.assertEqual((quote.month, quote.price, quote.year_ago_price), ('2026-10', 9000, 8000))
        self.assertIsNone(self.prices.quote('냉면', '부산'))

    def test_menu_comparison_tab(self):
        result = self.model.analyze(self.model.defaults() | {'price': '9900', 'dine_menu': '김치찌개 백반', 'dine_region': '서울'}, 'w').result
        tab = result['extra_tables'][0]
        self.assertEqual(tab['tab'], '외식 가격 비교')
        current = tab['rows'][1]
        self.assertEqual((current[1], current[2], current[3]), (Decimal(9900), Decimal(900), Decimal(10)))
        self.assertIn('+12.5%', tab['note'])  # 8,000 -> 9,000
        self.assertNotIn('extra_tables', [k for k, v in self.model.analyze(self.model.defaults(), 'w').result.items() if v])
        with self.assertRaises(ValidationError):
            self.model.analyze(self.model.defaults() | {'dine_menu': '피자'}, 'w')


class StartupTests(unittest.TestCase):
    def setUp(self):
        _, self.data = loaded()
        self.model = model_for('property')
        self.model.startup_provider = self.data

    def test_benchmark_and_fallback(self):
        self.assertEqual(self.data.industries(), ['음식점 및 주점업'])
        self.assertEqual(self.data.regions(), ['전국', '서울특별시'])
        national = self.data.benchmark('음식점 및 주점업', '서울특별시')   # no Seoul row for the 중분류: 전국
        self.assertEqual((national.region, national.monthly_rent, national.deposit), ('전국', Decimal(1010000), Decimal(27480000)))
        self.assertEqual(national.cost_brackets, (Decimal('20.0'), Decimal('42.2'), Decimal('37.8')))

    def test_property_tab(self):
        result = self.model.analyze(self.model.defaults() | {'startup_industry': '음식점 및 주점업', 'startup_region': '전국'}, 'w').result
        tab = result['extra_tables'][-1]
        self.assertEqual(tab['tab'], '업종 평균 임대·창업비용')
        rows = {row[0]: row for row in tab['rows']}
        b = rows['가상 주거지 B']   # rent 1,200,000; startup 49,700,000
        self.assertEqual(round(b[2], 2), Decimal('18.81'))       # vs 1,010,000
        self.assertEqual(b[6], '5천만 원 미만 (업체 20.0%)')
        self.assertEqual(rows['가상 역세권 A'][6], '5천만~1억 원 (업체 42.2%)')
        self.assertEqual(len(self.model.analyze(self.model.defaults(), 'w').result['extra_tables']), 1)
        with self.assertRaises(ValidationError):
            self.model.analyze(self.model.defaults() | {'startup_industry': '없는 업종'}, 'w')


class HttpTests(unittest.TestCase):
    def test_inputs_appear_only_with_data(self):
        prices, startup = loaded()
        client = create_app({'TESTING': True, 'DINEOUT': prices, 'STARTUP_BENCHMARKS': startup}).test_client()
        self.assertIn('비교할 외식 메뉴', client.get('/menu-pricing/').get_data(as_text=True))
        self.assertIn('업종 평균 임대·창업비용 비교', client.get('/property/').get_data(as_text=True))
        with client.session_transaction() as session:
            token = session['csrf']
        page = unescape(client.post('/menu-pricing/', data=model_for('menu_pricing').defaults() |
                                    {'csrf': token, 'dine_menu': '냉면', 'dine_region': '서울'}, follow_redirects=True).get_data(as_text=True))
        self.assertIn('서울 냉면 평균 가격과 비교 (2026-10)', page)
        plain = create_app({'TESTING': True}).test_client()
        self.assertNotIn('비교할 외식 메뉴', plain.get('/menu-pricing/').get_data(as_text=True))
        self.assertNotIn('업종 평균 임대·창업비용 비교', plain.get('/property/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
