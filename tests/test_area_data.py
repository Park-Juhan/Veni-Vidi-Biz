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
from app.main.application import create_app
from app.reference import rents
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


def loaded_rents(database):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'KOSIS_부동산원_소규모상가_임대료_서울_2026Q2.csv'
        with path.open('w', encoding='utf-8-sig', newline='') as handle:
            csv.writer(handle).writerows([['권역', '상권', '2026.1/4', '2026.2/4'], ['소계', '소계', '50.0', '52.8'],
                                          ['기타지역', '소계', '44.0', '45.0'], ['영등포신촌지역', '홍대/합정', '61.0', '60.0'],
                                          ['도심지역', '시청', '89.0', '90.0']])
        assert rents.is_rent(path)
        self_check = rents.import_file(database, path)
    return self_check, rents.AreaRents(database)


class BulkSnapshotAndRentTests(unittest.TestCase):
    def setUp(self):
        self.database, self.data = loaded_data()

    def test_snapshots_match_single_lookups(self):
        self.assertEqual(self.data.districts(), ['마포구', '종로구', '중구'])
        everything = {s.name: s for s in self.data.snapshots('커피-음료')}
        self.assertEqual(set(everything), {'홍대입구역(홍대)', '서울시청'})   # 조용한골목 has no stores
        self.assertEqual(everything['홍대입구역(홍대)'], self.data.snapshot('3120103', '커피-음료'))
        self.assertEqual([s.name for s in self.data.snapshots('커피-음료', ['중구'])], ['서울시청'])

    def test_rent_import_and_matching(self):
        (dataset, count), rent = loaded_rents(self.database)
        self.assertEqual((dataset, count), ('부동산원 소규모 상가 임대료', 4))
        hongdae = rent.estimate('홍대입구역(홍대)', '마포구', '서교동')
        self.assertEqual((hongdae.per_m2, hongdae.basis, hongdae.quarter), (Decimal(60000), '홍대/합정 상권', '2026.2/4'))
        self.assertEqual(rent.estimate('서울시청', '중구', '명동').per_m2, Decimal(90000))
        # No keyword: same 자치구 average, then the Seoul 기타지역 average.
        self.assertEqual(rent.estimate('망원 어딘가', '마포구', '망원1동').basis, '마포구 조사 상권 평균')
        quiet = rent.estimate('조용한골목', '종로구', '청운효자동')
        self.assertEqual((quiet.per_m2, quiet.basis), (Decimal(45000), '서울 기타지역 평균'))

    def test_recommendation_with_imported_data(self):
        _, rent = loaded_rents(self.database)
        model = model_for('property')
        model.area_provider, model.rent_provider = self.data, rent
        result = model.analyze(model.defaults() | {'rent_band': '상관없음'}, 'w').result
        rows = {row[1].split(' (')[0]: row for row in result['rows']}
        # 900,000,000 / 100 / 3 = 3,000,000; 300,000,000 / 20 / 3 = 5,000,000. 44㎡ x 60,000 / 90,000.
        self.assertEqual((rows['홍대입구역(홍대)'][4], rows['서울시청'][4]), (Decimal(3000000), Decimal(5000000)))
        self.assertEqual((rows['홍대입구역(홍대)'][2], rows['서울시청'][2]), (Decimal(2640000), Decimal(3960000)))
        detail = {row[0]: row[1:] for row in result['extra_tables'][0]['rows']}
        self.assertEqual(detail['결제 1건당 금액 (원)'], [Decimal(15000), Decimal(10000)] if result['rows'][0][1].startswith('홍대') else [Decimal(10000), Decimal(15000)])
        self.assertTrue(any('서울시 상권분석서비스' in note for note in result['notes']))


class AreaHttpTests(unittest.TestCase):
    def test_form_lists_industries_and_districts_and_recommends(self):
        database, data = loaded_data()
        _, rent = loaded_rents(database)
        client = create_app({'TESTING': True, 'AREA_DATA': data, 'AREA_RENTS': rent}).test_client()
        page = unescape(client.get('/property/').get_data(as_text=True))
        self.assertIn('<option selected>커피-음료</option>', page)
        self.assertIn('name="districts" value="중구"', page)
        self.assertIn('name="rent_band" value="200~300만 원" checked', page)
        with client.session_transaction() as session:
            token = session['csrf']
        result = unescape(client.post('/property/', data=model_for('property').defaults() | {'csrf': token, 'rent_band': '상관없음', 'districts': ['중구']},
                                      follow_redirects=True).get_data(as_text=True))
        self.assertIn('추천 상권 상위 1곳', result)
        self.assertIn('서울시청 (중구 명동)', result)
        self.assertIn('중구 상권 추천', result)

    def test_without_data_explains_import(self):
        client = create_app({'TESTING': True}).test_client()
        page = client.get('/property/').get_data(as_text=True)
        self.assertIn('상권 공공데이터를 불러오면 추천을 쓸 수 있습니다', page)


if __name__ == '__main__':
    unittest.main()
