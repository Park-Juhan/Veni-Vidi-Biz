"""Small business survey averages (KOSIS): import, regional fallback and comparison in 05."""
import csv
from decimal import Decimal
from html import unescape
from pathlib import Path
import tempfile
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.reference.kosis import KosisBenchmarks, import_file, is_kosis
from tests.module_support import model_for

HEADER = ['기준연도', '시도', '대분류', '업종', '기업체수', '매출액', '영업비용', '매출원가', '급여총액', '임차료', '기타비용', '영업이익']
ROWS = [
    ['2023', '전국', '숙박 및 음식점업', '소계', '790003', '151', '119', '70', '24', '14', '11', '32'],
    ['2023', '전국', '숙박 및 음식점업', '음식점 및 주점업', '745196', '156', '124', '73', '25', '15', '11', '33'],
    ['2023', '서울특별시', '숙박 및 음식점업', '음식점 및 주점업', '', '212', '173', '', '', '', '', '39'],  # no cost split
    ['2023', '전국', '교육 서비스업', '소계', '231896', '75', '51', '15', '19', '11', '6', '24'],
]


def loaded():
    database = Database.in_memory()
    database.migrate()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'KOSIS_소상공인실태조사_업종별_경영지표_2023.csv'
        with path.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle); writer.writerow(HEADER); writer.writerows(ROWS)
        self_check = is_kosis(path)
        import_file(database, path)
    assert self_check
    return KosisBenchmarks(database)


class KosisTests(unittest.TestCase):
    def test_choices_and_ratios(self):
        data = loaded()
        self.assertEqual(data.industries(), ['숙박 및 음식점업 전체', '음식점 및 주점업', '교육 서비스업 전체'])
        self.assertEqual(data.regions(), ['전국', '서울특별시'])
        national = data.benchmark('음식점 및 주점업', '전국')
        self.assertEqual(national.monthly_revenue, Decimal(13000000))           # 156백만원 / 12
        self.assertEqual(round(national.cost_of_sales_ratio, 2), Decimal('46.79'))  # 73 / 156
        self.assertEqual(national.split_region, '전국')
        seoul = data.benchmark('음식점 및 주점업', '서울특별시')
        self.assertEqual(seoul.split_region, '전국')                             # cost split borrowed
        self.assertEqual(round(seoul.profit_ratio, 2), Decimal('18.40'))         # 39 / 212, Seoul's own
        self.assertIsNone(data.benchmark('교육 서비스업 전체', '서울특별시'))
        self.assertFalse(KosisBenchmarks(Database.in_memory()).available())


class CostComparisonTests(unittest.TestCase):
    def setUp(self):
        self.model = model_for('cost_optimization')
        self.model.benchmark_provider = loaded()

    def test_comparison_tab(self):
        # Revenue 12M; material 2.5M = 20.83% against 46.79% (73/156).
        result = self.model.analyze(self.model.defaults() | {'bench_industry': '음식점 및 주점업', 'bench_region': '전국'}, 'w').result
        tab = result['extra_tables'][-1]
        self.assertEqual(tab['tab'], '업종 평균 비교')
        rows = {row[0]: row for row in tab['rows']}
        material = rows['재료비 ↔ 매출원가']
        self.assertEqual(material[1], Decimal(2500000))
        self.assertEqual(round(material[4], 2), Decimal('-25.96'))
        self.assertEqual(material[5], Decimal(5615385))   # 12M x 73/156, whole won
        self.assertEqual(rows['공과금·광고·기타 ↔ 기타비용'][1], Decimal(1000000))  # 400k + 300k + 300k
        self.assertIn('대표자 본인 인건비', tab['note'])

    def test_fallback_none_and_validation(self):
        seoul = self.model.analyze(self.model.defaults() | {'bench_industry': '교육 서비스업 전체', 'bench_region': '서울특별시'}, 'w').result
        self.assertIn('교육 서비스업 전체 · 전국', seoul['extra_tables'][-1]['title'])  # no Seoul row: nationwide
        off = self.model.analyze(self.model.defaults() | {'bench_industry': 'none'}, 'w').result
        self.assertEqual(len(off['extra_tables']), 1)
        with self.assertRaises(ValidationError):
            self.model.analyze(self.model.defaults() | {'bench_industry': '없는 업종'}, 'w')
        plain = model_for('cost_optimization')
        self.assertEqual(len(plain.analyze(plain.defaults(), 'w').result['extra_tables']), 1)


class BenchmarkHttpTests(unittest.TestCase):
    def test_step_and_result_tab(self):
        client = create_app({'TESTING': True, 'BENCHMARKS': loaded()}).test_client()
        page = unescape(client.get('/cost-optimization/').get_data(as_text=True))
        self.assertIn('비교할 업종', page)
        self.assertIn('<option selected>음식점 및 주점업</option>', page)
        with client.session_transaction() as session:
            token = session['csrf']
        result = unescape(client.post('/cost-optimization/', data=model_for('cost_optimization').defaults() |
                                      {'csrf': token, 'bench_industry': '음식점 및 주점업', 'bench_region': '서울특별시'},
                                      follow_redirects=True).get_data(as_text=True))
        self.assertIn('업종 평균과 비교 (음식점 및 주점업 · 서울특별시, 2023)', result)
        self.assertIn('비용 구성은 전국 값', result)
        self.assertIn('<option selected>서울특별시</option>', result)
        self.assertNotIn('비교할 업종', create_app({'TESTING': True}).test_client().get('/cost-optimization/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
