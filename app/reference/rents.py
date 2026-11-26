"""Monthly rent per ㎡ of small shops by Seoul commercial area (한국부동산원 「상업용부동산 임대동향조사」).

CSV: data/raw/KOSIS_부동산원_소규모상가_임대료_*.csv with columns 권역, 상권, <quarter>... (천원/㎡). Taken from KOSIS
for local calculation only. The survey covers 64 Seoul areas; each 서울시 상권 is matched to one of them by name or
행정동 keyword, else to the average of the surveyed areas in the same 자치구, else to the Seoul average.
"""
from decimal import Decimal
from pathlib import Path

from app.common.db import utc_now
from app.integrations.contracts import RentEstimate
from app.reference.seoul_areas import DataImportError, read_rows

DATASET = '부동산원 소규모 상가 임대료'
PROVIDER = '한국부동산원 「상업용부동산 임대동향조사」 상권별 소규모 상가 임대료 (KOSIS)'
# Surveyed area -> (자치구, keywords found in a 서울시 상권 name or 행정동). Longer keywords are tried first.
AREAS = {
    '광화문': ('종로구', ('광화문',)), '남대문': ('중구', ('남대문', '숭례문')), '동대문': ('중구', ('동대문',)),
    '명동': ('중구', ('명동',)), '방산시장': ('중구', ('방산',)), '북촌': ('종로구', ('북촌', '삼청', '가회')),
    '서촌': ('종로구', ('서촌', '통인', '경복궁')), '시청': ('중구', ('시청',)), '을지로': ('중구', ('을지로',)),
    '종로': ('종로구', ('종로', '종각')), '충무로': ('중구', ('충무로',)),
    '강남대로': ('강남구', ('강남역', '강남대로')), '교대역': ('서초구', ('교대',)), '남부터미널': ('서초구', ('남부터미널',)),
    '논현역': ('강남구', ('논현',)), '도산대로': ('강남구', ('도산',)), '신사역': ('강남구', ('신사', '가로수길')),
    '압구정': ('강남구', ('압구정',)), '청담': ('강남구', ('청담',)), '테헤란로': ('강남구', ('테헤란', '역삼', '선릉', '삼성역')),
    '공덕역': ('마포구', ('공덕',)), '당산역': ('영등포구', ('당산',)), '동교/연남': ('마포구', ('연남', '동교')),
    '망원역': ('마포구', ('망원', '망리단')), '신촌/이대': ('서대문구', ('신촌', '이대', '이화')),
    '영등포역': ('영등포구', ('영등포역', '영등포시장')), '홍대/합정': ('마포구', ('홍대', '홍익', '합정', '서교')),
    '가락시장': ('송파구', ('가락',)), '건대입구': ('광진구', ('건대', '건국대')), '경희대': ('동대문구', ('경희대', '회기')),
    '군자': ('광진구', ('군자',)), '까치산역': ('강서구', ('까치산',)), '노량진': ('동작구', ('노량진',)),
    '독산/시흥': ('금천구', ('독산', '시흥')), '뚝섬': ('성동구', ('뚝섬', '성수')), '목동': ('양천구', ('목동',)),
    '미아사거리': ('강북구', ('미아',)), '불광역': ('은평구', ('불광',)), '사당': ('동작구', ('사당',)),
    '상계역': ('노원구', ('상계',)), '상봉역': ('중랑구', ('상봉',)), '서울대입구역': ('관악구', ('서울대입구', '샤로수')),
    '성신여대': ('성북구', ('성신여대',)), '수유': ('강북구', ('수유',)), '숙명여대': ('용산구', ('숙명여대', '숙대')),
    '신림역': ('관악구', ('신림',)), '약수역': ('중구', ('약수',)), '연신내': ('은평구', ('연신내',)),
    '오류동역': ('구로구', ('오류',)), '왕십리': ('성동구', ('왕십리',)), '용산역': ('용산구', ('용산역',)),
    '이태원': ('용산구', ('이태원', '한남')), '잠실/송파': ('송파구', ('잠실', '송리단')), '잠실새내역': ('송파구', ('잠실새내', '신천')),
    '장안동': ('동대문구', ('장안',)), '천호': ('강동구', ('천호',)), '청량리': ('동대문구', ('청량리',)),
    '혜화동': ('종로구', ('혜화', '대학로')), '화곡': ('강서구', ('화곡',)),
}
KEYWORDS = sorted(((word, area) for area, (_, words) in AREAS.items() for word in words), key=lambda x: -len(x[0]))


def is_rent(path):
    name = Path(path).name
    return name.startswith('KOSIS_부동산원_소규모상가_임대료') and name.endswith('.csv')


def import_file(database, path):
    rows = list(read_rows(path))
    if not rows or not {'권역', '상권'} <= set(rows[0]):
        raise DataImportError(f'{Path(path).name}: 권역, 상권 열과 분기 열(예: 2026.2/4)이 필요합니다.')
    quarters = sorted(c for c in rows[0] if c not in ('권역', '상권'))
    if not quarters:
        raise DataImportError(f'{Path(path).name}: 분기 열이 없습니다.')
    latest = quarters[-1]
    data = [(r['권역'].strip(), r['상권'].strip(), latest, float(r[latest])) for r in rows if (r.get(latest) or '').strip()]
    with database.connect() as connection:
        connection.execute('DELETE FROM area_rents')
        connection.executemany('INSERT INTO area_rents VALUES (?, ?, ?, ?)', data)
        connection.execute('INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET file_name = excluded.file_name, '
                           'period_from = excluded.period_from, period_to = excluded.period_to, row_count = excluded.row_count, imported_at = excluded.imported_at',
                           (DATASET, PROVIDER, Path(path).name, latest, latest, len(data), utc_now()))
    return DATASET, len(data)


class AreaRents:
    """Implements RentProvider: estimated monthly rent per ㎡ for a 서울시 상권."""

    def __init__(self, database):
        self.database = database
        self._table = None

    def available(self):
        try:
            return bool(self.table())
        except Exception:  # not migrated
            return False

    def table(self):
        if self._table is None:
            with self.database.connect() as connection:
                self._table = {(r['zone'], r['area']): (Decimal(str(r['rent_per_m2'])), r['quarter'])
                               for r in connection.execute('SELECT * FROM area_rents')}
        return self._table

    def estimate(self, name, district, dong):
        table = self.table()
        areas = {area: value for (zone, area), value in table.items() if area != '소계'}
        quarter = next(iter(table.values()))[1] if table else ''
        for text in (name or '', dong or ''):
            compact = text.replace(' ', '')
            for word, area in KEYWORDS:
                if word in compact and area in areas:
                    return RentEstimate(areas[area][0] * 1000, f'{area} 상권', quarter, PROVIDER)
        same = [areas[a][0] for a, (gu, _) in AREAS.items() if gu == district and a in areas]
        if same:
            return RentEstimate(sum(same) / len(same) * 1000, f'{district} 조사 상권 평균', quarter, PROVIDER)
        seoul = table.get(('기타지역', '소계')) or table.get(('소계', '소계'))
        return RentEstimate(seoul[0] * 1000, '서울 기타지역 평균', quarter, PROVIDER) if seoul else None
