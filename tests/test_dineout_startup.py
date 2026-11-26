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
from tests.fakes import property_config


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
        # The dish name is matched to the survey menu (김치찌개 -> 김치찌개 백반, 서울).
        result = self.model.analyze(self.model.defaults() | {'dish': '김치찌개', 'price': '9900'}, 'w').result
        tab = result['extra_tables'][0]
        self.assertEqual(tab['tab'], '외식 가격 비교')
        current = tab['rows'][1]
        self.assertEqual((current[1], current[2], current[3]), (Decimal(9900), Decimal(900), Decimal(10)))
        self.assertIn('+12.5%', tab['note'])  # 8,000 -> 9,000
        self.assertEqual(self.model.analyze(self.model.defaults() | {'dish': '아메리카노'}, 'w').result['extra_tables'], [])


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
        result = self.model.analyze(self.model.defaults() | {'rent_band': '상관없음'}, 'w').result
        tab = result['extra_tables'][-1]
        self.assertEqual(tab['tab'], '업종 평균과 비교')
        rows = {row[0]: row for row in tab['rows']}
        self.assertEqual(rows['망원역'][2], '+74.3')            # 1,760,000 vs 1,010,000 (커피-음료 -> 음식점 및 주점업)
        self.assertEqual(rows['망원역'][4], '5천만~1억 원 (업체 42.2%)')
        self.model.startup_provider = None
        self.assertEqual(len(self.model.analyze(self.model.defaults() | {'rent_band': '상관없음'}, 'w').result['extra_tables']), 1)


class HttpTests(unittest.TestCase):
    def test_tabs_appear_only_with_data(self):
        prices, startup = loaded()
        client = create_app({'TESTING': True, 'DINEOUT': prices, 'STARTUP_BENCHMARKS': startup} | property_config()).test_client()
        client.get('/menu-pricing/')
        with client.session_transaction() as session:
            token = session['csrf']
        page = unescape(client.post('/menu-pricing/', data=model_for('menu_pricing').defaults() |
                                    {'csrf': token, 'dish': '김치찌개'}, follow_redirects=True).get_data(as_text=True))
        self.assertIn('서울 김치찌개 백반 평균 가격과 비교 (2026-10)', page)
        page = unescape(client.post('/property/', data=model_for('property').defaults() | {'csrf': token, 'rent_band': '상관없음'},
                                    follow_redirects=True).get_data(as_text=True))
        self.assertIn('업종 평균 임대·창업비용과 비교', page)
        plain = create_app({'TESTING': True} | property_config()).test_client()
        plain.get('/property/')
        with plain.session_transaction() as session:
            token = session['csrf']
        page = plain.post('/property/', data=model_for('property').defaults() | {'csrf': token, 'rent_band': '상관없음'}, follow_redirects=True)
        self.assertNotIn('업종 평균 임대·창업비용과 비교', page.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
