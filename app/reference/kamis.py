"""KAMIS monthly retail prices (CSV saved to data/raw/KAMIS_소매가격_월별_*.csv).

Columns: 월, 지역, 부류, 품목, 품종, 단위, 등급, 월평균가격. import_file() replaces the table;
KamisPrices answers the MarketPriceProvider contract for the material cost module.
"""
from decimal import Decimal
from pathlib import Path
import re

from app.common.db import utc_now
from app.integrations.contracts import MarketItemOption, MarketQuote
from app.reference.seoul_areas import DataImportError, read_rows

DATASET = 'KAMIS 소매가격 (월평균)'
PROVIDER = '한국농수산식품유통공사 KAMIS 농산물유통정보 · 소매가격 (부류별·월간)'
SOURCE_NAMES = {'KAMIS': PROVIDER, '참가격': '한국소비자원 참가격 「생필품 가격 정보」', '서울시장': '서울특별시 「생필품 농수축산물 가격 정보」'}
COLUMNS = ('월', '지역', '부류', '품목', '품종', '단위', '등급', '월평균가격')
UNIT = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*(kg|g|L|l|mL|ml|개)\s*$')
FACTOR = {'kg': ('g', 1000), 'g': ('g', 1), 'L': ('mL', 1000), 'l': ('mL', 1000), 'mL': ('mL', 1), 'ml': ('mL', 1), '개': ('개', 1)}


def is_kamis(path):
    name = Path(path).name
    return name.startswith('KAMIS_소매가격_월별') and name.endswith('.csv')


def base_of(unit):
    """('g', 1000) for '1kg', ('개', 10) for '10개'; None for units like 1포기 or 1마리."""
    match = UNIT.match(unit or '')
    if not match:
        return None
    base, factor = FACTOR[match.group(2)]
    return base, Decimal(match.group(1)) * factor


def make_key(item, kind, unit, rank):
    return '|'.join((item, kind, unit, rank))


def import_file(database, path):
    rows, months = [], set()
    for index, row in enumerate(read_rows(path)):
        if index == 0:
            missing = [c for c in COLUMNS if c not in row]
            if missing:
                raise DataImportError(f'{Path(path).name}: 열이 없습니다 ({", ".join(missing)}).')
        price = (row['월평균가격'] or '').replace(',', '').strip()
        if not price or price == '-':
            continue
        rows.append((row['지역'], row['월'], row['부류'], row['품목'], row['품종'], row['단위'], row['등급'], int(Decimal(price))))
        months.add(row['월'])
    with database.connect() as connection:
        connection.execute("DELETE FROM price_series WHERE source = 'KAMIS'")
        connection.executemany('INSERT OR REPLACE INTO price_series (region, month, category, item, kind, unit, rank, price) '
                               'VALUES (?, ?, ?, ?, ?, ?, ?, ?)', rows)
        connection.execute('INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET file_name = excluded.file_name, '
                           'period_from = excluded.period_from, period_to = excluded.period_to, row_count = excluded.row_count, imported_at = excluded.imported_at',
                           (DATASET, PROVIDER, Path(path).name, min(months, default=None), max(months, default=None), len(rows), utc_now()))
    return DATASET, len(rows)


class KamisPrices:
    """Read side of the imported KAMIS prices; implements MarketPriceProvider."""

    def __init__(self, database):
        self.database = database
        self._series = None

    def available(self):
        try:
            with self.database.connect() as connection:
                return connection.execute('SELECT 1 FROM price_series LIMIT 1').fetchone() is not None
        except Exception:  # tables missing (not migrated)
            return False

    def series(self):
        """key -> (item, kind, unit, rank, category, source), loaded once. KAMIS first, then the other sources."""
        if self._series is None:
            with self.database.connect() as connection:
                rows = connection.execute("SELECT DISTINCT item, kind, unit, rank, category, source FROM price_series "
                                          "ORDER BY source != 'KAMIS', source, category, item, kind, unit, rank").fetchall()
            self._series = {make_key(r['item'], r['kind'], r['unit'], r['rank']): tuple(r) for r in rows}
        return self._series

    @staticmethod
    def label(item, kind, unit, rank):
        parts = [item] + ([kind] if kind and kind != item else []) + [unit] + ([rank] if rank and rank != '-' else [])
        return ' · '.join(parts)

    def options(self):
        return [MarketItemOption(key, self.label(*value[:4])) for key, value in self.series().items()]

    def suggest(self, name, base_unit):
        """Best series for a material name: same 품목 (or 품종) name, a unit convertible to base_unit, 상품 grade first."""
        name = (name or '').strip()
        candidates = [(key, v) for key, v in self.series().items() if name and (v[0] == name or v[1] == name)]
        if not candidates:
            # Partial names either way: 마늘 -> 깐마늘(국산), 국산 양파 -> 양파 (two characters at least).
            candidates = [(key, v) for key, v in self.series().items()
                          if len(name) >= 2 and ((len(v[0]) >= 2 and v[0] in name) or name in v[0])]
        def score(entry):
            _, (item, kind, unit, rank, category, source) = entry
            base = base_of(unit)
            # Comparable unit, exact name, then KAMIS > Seoul market survey > brand products, 상품 grade, plain names.
            order = {'KAMIS': 2, '서울시장': 1}.get(source, 0)
            return (base is not None and base[0] == base_unit, item == name, order, rank in ('상품', '전통시장'), category == '', -len(item))
        return max(candidates, key=score)[0] if candidates else None

    def quote(self, key):
        found = self.series().get(key)
        if not found:
            return None
        item, kind, unit, rank, _, source = found
        with self.database.connect() as connection:
            def latest(region):
                return connection.execute('SELECT month, price FROM price_series WHERE region = ? AND item = ? AND kind = ? AND unit = ? AND rank = ? '
                                          'ORDER BY month DESC LIMIT 1', (region, item, kind, unit, rank)).fetchone()
            national = latest('전국') or latest('서울')
            if national is None:
                return None
            seoul = latest('서울')
            year, month = int(national['month'][:4]), national['month'][5:]
            region = '전국' if latest('전국') else '서울'
            ago = connection.execute('SELECT price FROM price_series WHERE region = ? AND month = ? AND item = ? AND kind = ? AND unit = ? AND rank = ?',
                                     (region, f'{year - 1}-{month}', item, kind, unit, rank)).fetchone()
        base = base_of(unit)
        per = (lambda price: Decimal(price) / base[1]) if base else (lambda price: None)
        return MarketQuote(key=key, label=self.label(item, kind, unit, rank), unit=unit, month=national['month'], price=national['price'],
                           seoul_price=seoul['price'] if seoul else None, base_unit=base[0] if base else None,
                           price_per_base=per(national['price']), seoul_per_base=per(seoul['price']) if seoul else None,
                           year_ago_price=ago['price'] if ago else None, source=SOURCE_NAMES.get(source, PROVIDER))
