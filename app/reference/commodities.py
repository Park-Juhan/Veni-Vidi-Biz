"""International raw material futures from aT 식품산업통계정보 (FIS) 「국제 원료가격」.

CSV: data/raw/aTFIS_국제원료_*.csv with columns 품목, 주시작일, 평균가(US센트/lb), 환산가(USD/ton). Kept for local
calculation only (aT 저작권 정책: 공공누리 표시가 없는 자료). Used to show the green coffee price trend for coffee materials.
"""
from decimal import Decimal
from pathlib import Path

from app.common.db import utc_now
from app.integrations.contracts import CommodityTrend
from app.reference.seoul_areas import DataImportError, read_rows

DATASET = 'aT FIS 국제 원료가격'
PROVIDER = 'aT 식품산업통계정보(FIS) 「국제 원료가격」 · ICE(NYBOT) 아라비카 선물 주간 평균'
COLUMNS = ('품목', '주시작일', '평균가(US센트/lb)', '환산가(USD/ton)')
# Material names that should show the coffee trend.
KEYWORDS = {'커피(아라비카)': ('원두', '커피', '생두', '에스프레소', '아라비카')}


def is_commodity(path):
    name = Path(path).name
    return name.startswith('aTFIS_국제원료') and name.endswith('.csv')


def import_file(database, path):
    rows = []
    for index, row in enumerate(read_rows(path)):
        if index == 0 and not set(COLUMNS) <= set(row):
            raise DataImportError(f'{Path(path).name}: {", ".join(COLUMNS)} 열이 필요합니다.')
        ton = (row['환산가(USD/ton)'] or '').strip()
        rows.append((row['품목'].strip(), row['주시작일'].strip(), float(row['평균가(US센트/lb)']), float(ton) if ton else None))
    weeks = {r[1] for r in rows}
    with database.connect() as connection:
        connection.execute('DELETE FROM commodity_prices WHERE commodity IN (%s)' % ','.join('?' * len({r[0] for r in rows})), tuple({r[0] for r in rows}))
        connection.executemany('INSERT OR REPLACE INTO commodity_prices VALUES (?, ?, ?, ?)', rows)
        connection.execute('INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET file_name = excluded.file_name, '
                           'period_from = excluded.period_from, period_to = excluded.period_to, row_count = excluded.row_count, imported_at = excluded.imported_at',
                           (DATASET, PROVIDER, Path(path).name, min(weeks, default=None), max(weeks, default=None), len(rows), utc_now()))
    return DATASET, len(rows)


class CommodityPrices:
    """Implements CommodityTrendProvider."""

    def __init__(self, database):
        self.database = database

    def available(self):
        try:
            with self.database.connect() as connection:
                return connection.execute('SELECT 1 FROM commodity_prices LIMIT 1').fetchone() is not None
        except Exception:  # tables missing (not migrated)
            return False

    def trend_for(self, material_name):
        """Trend of the commodity whose keywords appear in the material name, or None."""
        name = (material_name or '').replace(' ', '')
        commodity = next((c for c, words in KEYWORDS.items() if any(w in name for w in words)), None)
        if commodity is None:
            return None
        with self.database.connect() as connection:
            rows = connection.execute('SELECT week_start, cents_per_lb, usd_per_ton FROM commodity_prices WHERE commodity = ? '
                                      'ORDER BY week_start DESC', (commodity,)).fetchall()
        if not rows:
            return None
        latest = rows[0]
        def change(weeks):
            if len(rows) <= weeks: return None
            old = rows[weeks]['cents_per_lb']
            return (Decimal(str(latest['cents_per_lb'])) - Decimal(str(old))) / Decimal(str(old)) * 100
        per_kg = Decimal(str(latest['usd_per_ton'])) / 1000 if latest['usd_per_ton'] is not None else None
        return CommodityTrend(commodity=commodity, week_start=latest['week_start'], cents_per_lb=Decimal(str(latest['cents_per_lb'])),
                              usd_per_kg=per_kg, change_4w=change(4), change_52w=change(52), source=PROVIDER)
