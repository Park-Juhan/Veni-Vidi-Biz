"""Small in-memory public-data providers for tests (no CSV files needed)."""
from decimal import Decimal

from app.integrations.contracts import AreaOption, AreaSnapshot, RentEstimate

# name, district, dong, kind, sales (quarter), stores, footfall, close_rate, rent per ㎡
AREAS = (
    ('망원역', '마포구', '망원1동', '발달상권', 900_000_000, 30, 500_000, 2, 40_000),
    ('홍대입구', '마포구', '서교동', '발달상권', 3_000_000_000, 100, 3_000_000, 4, 60_000),
    ('시청', '중구', '소공동', '발달상권', 300_000_000, 20, 800_000, 0, 40_000),
    ('작은골목', '중구', '회현동', '골목상권', 50_000_000, 2, 100_000, 0, 30_000),
    ('망원시장', '마포구', '망원1동', '전통시장', 80_000_000, 10, 250_000, 10, 40_000),
)


class FakeAreas:
    """AreaDataProvider with five areas selling 커피-음료."""

    def available(self):
        return True

    def industries(self):
        return ['커피-음료', '한식음식점']

    def districts(self):
        return ['마포구', '중구']

    def area_options(self):
        return [AreaOption(str(i), f'{a[0]} · {a[1]} {a[2]} · {a[3]}') for i, a in enumerate(AREAS)]

    def snapshot(self, code, industry):
        return next((s for s in self.snapshots(industry) if s.code == code), None)

    def snapshots(self, industry, districts=None):
        if industry != '커피-음료':
            return []
        return [AreaSnapshot(code=str(i), name=a[0], kind=a[3], district=a[1], dong=a[2], industry=industry, period='2026년 2분기',
                             sales=a[4], sales_count=a[4] // 7000, stores=a[5], franchise=1, open_rate=3, close_rate=a[7],
                             footfall=a[6], workers=1000, residents=2000, facilities=10, subway=1, bus_stops=3, change='정체',
                             top_age='30대', top_time='14~17시', source='테스트 상권 자료')
                for i, a in enumerate(AREAS) if not districts or a[1] in districts]


class FakeRents:
    """RentProvider: monthly rent per ㎡ by area name."""

    def available(self):
        return True

    def estimate(self, name, district, dong):
        per_m2 = next(a[8] for a in AREAS if a[0] == name)
        return RentEstimate(Decimal(per_m2), f'{name} 상권', '2026.2/4', '테스트 임대료')


def property_config():
    return {'AREA_DATA': FakeAreas(), 'AREA_RENTS': FakeRents()}
