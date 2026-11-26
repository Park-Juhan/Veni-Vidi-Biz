"""Restaurant menu prices by region (행정안전부 지방물가 외식비, shown on 한국소비자원 참가격).

CSV: data/raw/외식비_시도별_*.csv with columns 월, 지역, 메뉴, 가격 (원). Kept for local calculation only.
"""
from pathlib import Path

from app.common.db import utc_now
from app.integrations.contracts import DineOutQuote
from app.reference.seoul_areas import DataImportError, read_rows

DATASET = '외식비 (시도별 대표 메뉴)'
PROVIDER = '행정안전부 지방물가 외식비 (한국소비자원 참가격 「서비스가격정보 > 외식비」, 출처 국가데이터처)'


def is_dineout(path):
    name = Path(path).name
    return name.startswith('외식비_시도별') and name.endswith('.csv')


def import_file(database, path):
    rows = []
    for index, row in enumerate(read_rows(path)):
        if index == 0 and not {'월', '지역', '메뉴', '가격'} <= set(row):
            raise DataImportError(f'{Path(path).name}: 월·지역·메뉴·가격 열이 없습니다.')
        price = (row['가격'] or '').replace(',', '').strip()
        if price.isdigit() and int(price) > 0:
            rows.append((row['월'].strip(), row['지역'].strip(), row['메뉴'].strip(), int(price)))
    months = {r[0] for r in rows}
    with database.connect() as connection:
        connection.execute('DELETE FROM dineout_prices')
        connection.executemany('INSERT OR REPLACE INTO dineout_prices VALUES (?, ?, ?, ?)', rows)
        connection.execute('INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET file_name = excluded.file_name, '
                           'period_from = excluded.period_from, period_to = excluded.period_to, row_count = excluded.row_count, imported_at = excluded.imported_at',
                           (DATASET, PROVIDER, Path(path).name, min(months, default=None), max(months, default=None), len(rows), utc_now()))
    return DATASET, len(rows)


class DineOutPrices:
    """Implements DineOutProvider."""

    def __init__(self, database):
        self.database = database

    def available(self):
        try:
            with self.database.connect() as connection:
                return connection.execute('SELECT 1 FROM dineout_prices LIMIT 1').fetchone() is not None
        except Exception:  # tables missing (not migrated)
            return False

    def _distinct(self, column):
        with self.database.connect() as connection:
            return [r[0] for r in connection.execute(f'SELECT {column} FROM dineout_prices GROUP BY {column} ORDER BY MIN(rowid)')]

    def menus(self):
        return self._distinct('menu')

    def regions(self):
        return self._distinct('region')

    def quote(self, menu, region):
        with self.database.connect() as connection:
            row = connection.execute('SELECT month, price FROM dineout_prices WHERE menu = ? AND region = ? ORDER BY month DESC LIMIT 1',
                                     (menu, region)).fetchone()
            if row is None:
                return None
            year, month = int(row['month'][:4]), row['month'][5:]
            ago = connection.execute('SELECT price FROM dineout_prices WHERE menu = ? AND region = ? AND month = ?',
                                     (menu, region, f'{year - 1}-{month}')).fetchone()
        return DineOutQuote(menu=menu, region=region, month=row['month'], price=row['price'],
                            year_ago_price=ago['price'] if ago else None, source=PROVIDER)
