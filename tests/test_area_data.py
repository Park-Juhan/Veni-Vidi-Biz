"""Seoul commercial-area data: CSV import, lookups and use in location comparison (01)."""
from contextlib import redirect_stderr, redirect_stdout
import csv
from decimal import Decimal
from html import unescape
from pathlib import Path
import io
import tempfile
import unittest

from app.common.db import Database
from app.common.validation import ValidationError
from app.main.application import create_app
from app.modules.property.repositories.candidates import CandidateStore
from app.reference.seoul_areas import SeoulAreaData, import_folder, kind_of
import import_data
from tests.module_support import model_for

AGES = ('10', '20', '30', '40', '50', '60_이상')
TIMES = ('00~06', '06~11', '11~14', '14~17', '17~21', '21~24')
AREAS = (  # code, name, kind, district, dong
    ('3120103', '홍대입구역(홍대)', '발달상권', '마포구', '서교동'),
    ('3120023', '서울시청', '발달상권', '중구', '명동'),
    ('3110001', '조용한골목', '골목상권', '종로구', '청운효자동'),
)


def write(folder, kind, header, rows, unit='상권'):
    path = Path(folder) / f'서울시 상권분석서비스({kind}-{unit}).csv'
    with path.open('w', encoding='cp949', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def area_cols(code):
    name, kind = next((a[1], a[2]) for a in AREAS if a[0] == code)
    return ['A' if kind == '골목상권' else 'D', kind, code, name]


def sample_files(folder):
    """Three areas; 커피-음료 sales/stores for 홍대 and 시청 only, 2026 Q1 and Q2."""
    write(folder, '영역', ['상권_구분_코드', '상권_구분_코드_명', '상권_코드', '상권_코드_명', '엑스좌표_값', '와이좌표_값', '자치구_코드', '자치구_코드_명', '행정동_코드', '행정동_코드_명', '영역_면적'],
          [['A' if kind == '골목상권' else 'D', kind, code, name, '1', '2', '1', district, '1', dong, '1000'] for code, name, kind, district, dong in AREAS])
    base = ['기준_년분기_코드', '상권_구분_코드', '상권_구분_코드_명', '상권_코드', '상권_코드_명']
    sales_header = base + ['서비스_업종_코드', '서비스_업종_코드_명', '당월_매출_금액', '당월_매출_건수', '주중_매출_금액', '주말_매출_금액'] \
        + [f'시간대_{t}_매출_금액' for t in TIMES] + ['남성_매출_금액', '여성_매출_금액'] + [f'연령대_{a}_매출_금액' for a in AGES]
    def sales(period, code, amount, count, peak_time, peak_age):
        times = ['0'] * 6; times[peak_time] = str(amount)
        ages = ['0'] * 6; ages[peak_age] = str(amount)
        return [period, *area_cols(code), 'CS100010', '커피-음료', str(amount), str(count), str(amount), '0', *times, str(amount), '0', *ages]
    write(folder, '추정매출', sales_header, [
        sales('20261', '3120103', 100, 1, 0, 0),
        sales('20262', '3120103', 900_000_000, 60_000, 4, 1),   # 홍대: 20대, 17~21시
        sales('20262', '3120023', 300_000_000, 30_000, 2, 3),   # 시청: 40대, 11~14시
    ])
    write(folder, '점포', base + ['서비스_업종_코드', '서비스_업종_코드_명', '전체_점포_수', '일반_점포_수', '프랜차이즈_점포_수', '개업_율', '개업_점포_수', '폐업_률', '폐업_점포_수'], [
        ['20262', *area_cols('3120103'), 'CS100010', '커피-음료', '100', '80', '20', '5', '5', '4', '4'],
        ['20262', *area_cols('3120023'), 'CS100010', '커피-음료', '20', '10', '10', '3', '1', '6', '1'],
    ])
    write(folder, '길단위인구', base + ['총_유동인구_수'], [['20262', *area_cols(c), v] for c, v in (('3120103', '500000'), ('3120023', '200000'), ('3110001', '1000'))])
    write(folder, '직장인구', base + ['총_직장_인구_수'], [['20262', *area_cols('3120023'), '90000']])
    write(folder, '상주인구', base + ['총_상주인구_수', '총_가구_수'], [['20262', *area_cols('3120103'), '3000', '1500']])
    write(folder, '집객시설', base + ['집객시설_수', '지하철_역_수', '버스_정거장_수'], [['20262', *area_cols('3120103'), '40', '2', '']])
    write(folder, '상권변화지표', base + ['상권_변화_지표', '상권_변화_지표_명', '운영_영업_개월_평균', '폐업_영업_개월_평균', '서울_운영_영업_개월_평균', '서울_폐업_영업_개월_평균'],
          [['20262', *area_cols('3120103'), 'LH', '상권확장', '50', '30', '100', '50']])
    write(folder, '점포', ['기준_년분기_코드'], [['20262']], unit='서울시')  # other unit: skipped


def loaded_data():
    folder = tempfile.TemporaryDirectory()
    sample_files(folder.name)
    database = Database.in_memory()
    database.migrate()
    import_folder(database, folder.name)
    folder.cleanup()
    return database, SeoulAreaData(database)


class ImportAndLookupTests(unittest.TestCase):
    def test_import_counts_and_reimport_replaces(self):
        with tempfile.TemporaryDirectory() as folder:
            sample_files(folder)
            self.assertIsNone(kind_of(Path(folder) / '서울시 상권분석서비스(점포-서울시).csv'))
            database = Database.in_memory(); database.migrate()
            first = import_folder(database, folder)
            self.assertEqual(first[0][1], '영역-상권')  # areas first
            self.assertEqual(len(first), 8)
            import_folder(database, folder)  # same files again: no duplicates
            with database.connect() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM area_sales').fetchone()[0], 3)
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM area_counts WHERE metric = ?', ('footfall',)).fetchone()[0], 3)
                sales = connection.execute("SELECT period_from, period_to, row_count FROM datasets WHERE name = '추정매출-상권'").fetchone()
            self.assertEqual(tuple(sales), ('20261', '20262', 3))

    def test_cli_imports_into_database_file(self):
        with tempfile.TemporaryDirectory() as folder:
            sample_files(folder)
            target = Path(folder) / 'db' / 'veni.db'
            with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
                self.assertEqual(import_data.main([folder, '--database', str(target)]), 0)
                self.assertEqual(import_data.main([str(Path(folder) / 'missing'), '--database', str(target)]), 2)
            self.assertIn('건너뜀  서울시 상권분석서비스(점포-서울시).csv', out.getvalue())
            self.assertTrue(SeoulAreaData(Database(target)).available())

    def test_options_resolve_and_snapshot(self):
        _, data = loaded_data()
        self.assertTrue(data.available())
        labels = [o.label for o in data.area_options()]
        self.assertIn('홍대입구역(홍대) · 마포구 서교동 · 발달상권', labels)
        self.assertEqual(data.resolve('서울시청'), '3120023')
        self.assertEqual(data.resolve('홍대입구역(홍대) · 마포구 서교동 · 발달상권'), '3120103')
        self.assertIsNone(data.resolve('없는 상권'))
        self.assertEqual(data.industries(), ['커피-음료'])
        hongdae = data.snapshot('3120103', '커피-음료')
        self.assertEqual((hongdae.period, hongdae.sales, hongdae.stores, hongdae.footfall), ('2026년 2분기', 900_000_000, 100, 500000))
        self.assertEqual((hongdae.top_age, hongdae.top_time, hongdae.change), ('20대', '17~21시', '상권확장'))
        self.assertEqual((hongdae.facilities, hongdae.subway, hongdae.bus_stops, hongdae.residents), (40, 2, 0, 3000))
        quiet = data.snapshot('3110001', '커피-음료')
        self.assertEqual((quiet.sales, quiet.stores, quiet.footfall, quiet.workers), (None, None, 1000, None))
        self.assertIsNone(data.snapshot('0000000', '커피-음료'))
        self.assertFalse(SeoulAreaData(Database.in_memory()).available())  # not migrated


class PropertyWithAreaTests(unittest.TestCase):
    def setUp(self):
        database, self.data = loaded_data()
        self.model = model_for('property')
        self.model.candidate_store = CandidateStore(database)
        self.model.area_provider = self.data

    def save(self, name, region, rent='1400000'):
        return self.model.save_candidate('w', dict(name=name, rent=rent, deposit='10000000', area='32', interior='12000000',
                                                   fit='3', traffic='3', facility='3', region=region))

    def test_region_is_validated_and_stored(self):
        self.save('A', '서울시청')
        self.save('B', '')
        with self.assertRaises(ValidationError):
            self.save('C', '없는 상권')
        regions = {c['name']: c['region_code'] for c in self.model.list_candidates('w')}
        self.assertEqual(regions, {'A': '3120023', 'B': None})
        self.assertEqual(self.model.area_label('3120023'), '서울시청 · 중구 명동 · 발달상권')

    def test_area_criteria_join_topsis_when_all_candidates_are_linked(self):
        self.save('홍대 후보', '홍대입구역(홍대)')
        self.save('시청 후보', '서울시청')
        candidates, _ = self.model.candidates_for('w')
        result = self.model.analyze(self.model.defaults() | {'candidates': candidates}, 'w').result
        criteria = [row[0] for row in result['extra_tables'][0]['rows']]
        self.assertEqual(criteria[-3:], ['점포당 월평균 추정매출', '같은 업종 점포 수', '유동인구'])
        tab = result['extra_tables'][1]
        self.assertEqual(tab['tab'], '상권 지표')
        names = tab['columns'][1:]
        rows = {row[0]: dict(zip(names, row[1:])) for row in tab['rows']}
        # 900,000,000 / 100 stores / 3 months = 3,000,000; 300,000,000 / 20 / 3 = 5,000,000.
        self.assertEqual(rows['점포당 월평균 추정매출 (원)'], {'홍대 후보': Decimal(3000000), '시청 후보': Decimal(5000000)})
        self.assertEqual(rows['결제 1건당 금액 (원)'], {'홍대 후보': Decimal(15000), '시청 후보': Decimal(10000)})
        self.assertEqual(rows['커피-음료 점포 수'], {'홍대 후보': 100, '시청 후보': 20})
        self.assertIn('서울시 상권분석서비스', tab['note'])
        # Same rents and ratings: higher sales per store and fewer competitors decide for 시청.
        self.assertEqual(result['best_name'], '시청 후보')
        # Without data weights the self-rated tie is broken only by input order; data changes the outcome.
        plain = self.model.analyze(self.model.defaults() | {'candidates': candidates, 'w_sales_per_store': '0', 'w_competition': '0', 'w_footfall': '0'}, 'w').result
        self.assertEqual(len(plain['extra_tables'][0]['rows']), 6)

    def test_unlinked_candidate_skips_area_criteria(self):
        self.save('홍대 후보', '홍대입구역(홍대)')
        self.save('미연결', '')
        candidates, _ = self.model.candidates_for('w')
        result = self.model.analyze(self.model.defaults() | {'candidates': candidates}, 'w').result
        self.assertEqual(len(result['extra_tables'][0]['rows']), 6)
        self.assertIn('상권 미연결', result['extra_tables'][1]['rows'][0])
        self.assertTrue(any('이번 비교에서 뺐습니다' in note for note in result['notes']))
        with self.assertRaises(ValidationError):
            self.model.analyze(self.model.defaults() | {'candidates': candidates, 'area_industry': '없는 업종'}, 'w')


class AreaHttpTests(unittest.TestCase):
    def setUp(self):
        _, data = loaded_data()
        self.client = create_app({'TESTING': True, 'AREA_DATA': data}).test_client()
        self.client.get('/property/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def post(self, data, **kwargs):
        return unescape(self.client.post('/property/', data=data | {'csrf': self.token}, **kwargs).get_data(as_text=True))

    def add(self, name, region):
        fields = dict(name=name, rent='1400000', deposit='10000000', area='32', interior='12000000', fit='3', traffic='3', facility='3', region=region)
        return self.post({'action': 'save_candidate', **{'cand_' + k: v for k, v in fields.items()}})

    def test_link_area_and_compare(self):
        page = unescape(self.client.get('/property/').get_data(as_text=True))
        self.assertIn('<option value="서울시청 · 중구 명동 · 발달상권">', page)
        bad = self.add('잘못', '없는 상권')
        self.assertIn("상권 '없는 상권'을(를) 찾지 못했습니다", bad)
        self.assertIn('value="없는 상권"', bad)
        self.add('홍대 후보', '홍대입구역(홍대) · 마포구 서교동 · 발달상권')
        page = self.add('시청 후보', '서울시청')
        self.assertIn('<td>서울시청</td>', page)
        self.assertIn('상권 데이터 업종', page)
        result = self.post(model_for('property').defaults() | {'area_industry': '커피-음료'}, follow_redirects=True)
        self.assertIn('후보별 상권 지표 (커피-음료, 2026년 2분기)', result)
        self.assertIn('점포당 월평균 추정매출', result)

    def test_without_data_the_area_input_is_hidden(self):
        client = create_app({'TESTING': True}).test_client()
        self.assertNotIn('서울 상권 (선택)', client.get('/property/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
