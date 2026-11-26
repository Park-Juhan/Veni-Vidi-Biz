"""Small business averages by industry (중소벤처기업부 소상공인실태조사, KOSIS tables DT_3ME0100 and DT_3ME0144).

The CSV (data/raw/KOSIS_소상공인실태조사_업종별_경영지표_*.csv) holds per-business annual figures in 백만원.
KosisBenchmarks answers the BenchmarkProvider contract for the cost optimization module.
"""
from decimal import Decimal
from pathlib import Path

from app.common.db import utc_now
from app.integrations.contracts import IndustryBenchmark
from app.reference.seoul_areas import DataImportError, read_rows

DATASET = '소상공인실태조사 업종별 경영지표'
PROVIDER = '중소벤처기업부 「소상공인실태조사」 (KOSIS 국가통계포털: 시도/산업중분류별 주요지표·영업비용)'
COLUMNS = ('기준연도', '시도', '대분류', '업종', '기업체수', '매출액', '영업비용', '매출원가', '급여총액', '임차료', '기타비용', '영업이익')
NUMBERS = COLUMNS[4:]


def is_kosis(path):
    name = Path(path).name
    return name.startswith('KOSIS_소상공인실태조사_업종별_경영지표') and name.endswith('.csv')


def _int(text):
    text = (text or '').replace(',', '').strip()
    return int(text) if text not in ('', '-') else None


def import_file(database, path):
    rows, years = [], set()
    for index, row in enumerate(read_rows(path)):
        if index == 0:
            missing = [c for c in COLUMNS if c not in row]
            if missing:
                raise DataImportError(f'{Path(path).name}: 열이 없습니다 ({", ".join(missing)}).')
        rows.append((row['기준연도'], row['시도'], row['대분류'], row['업종'], *(_int(row[c]) for c in NUMBERS)))
        years.add(row['기준연도'])
    with database.connect() as connection:
        connection.execute('DELETE FROM industry_benchmarks')
        connection.executemany('INSERT OR REPLACE INTO industry_benchmarks VALUES (' + ', '.join('?' * 12) + ')', rows)
        connection.execute('INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET file_name = excluded.file_name, '
                           'period_from = excluded.period_from, period_to = excluded.period_to, row_count = excluded.row_count, imported_at = excluded.imported_at',
                           (DATASET, PROVIDER, Path(path).name, min(years, default=None), max(years, default=None), len(rows), utc_now()))
    return DATASET, len(rows)


def label_of(sector, industry):
    return f'{sector} 전체' if industry == '소계' else industry


class KosisBenchmarks:
    """Read side of the imported survey averages; implements BenchmarkProvider."""

    def __init__(self, database):
        self.database = database

    def _rows(self):
        with self.database.connect() as connection:
            return [dict(r) for r in connection.execute('SELECT * FROM industry_benchmarks ORDER BY year DESC, rowid')]

    def available(self):
        try:
            with self.database.connect() as connection:
                return connection.execute('SELECT 1 FROM industry_benchmarks LIMIT 1').fetchone() is not None
        except Exception:  # tables missing (not migrated)
            return False

    def industries(self):
        seen = []
        for row in self._rows():
            if row['region'] == '전국':
                label = label_of(row['sector'], row['industry'])
                if label not in seen: seen.append(label)
        return seen

    def regions(self):
        regions = []
        for row in self._rows():
            if row['region'] not in regions: regions.append(row['region'])
        return regions

    def _find(self, rows, label, region):
        return next((r for r in rows if r['region'] == region and label_of(r['sector'], r['industry']) == label), None)

    def benchmark(self, industry, region):
        rows = self._rows()
        row = self._find(rows, industry, region)
        if row is None or not row['revenue']:
            return None
        # Cost breakdown: this region's row, else the same industry nationwide (shares only, applied to this region's revenue).
        split, split_region = row, region
        if row['cost_of_sales'] is None:
            split, split_region = self._find(rows, industry, '전국'), '전국'
        def share(value, base):
            return Decimal(value) / base * 100 if value is not None and base else None
        base = Decimal(split['revenue']) if split and split['revenue'] else None
        return IndustryBenchmark(
            industry=industry, region=region, year=row['year'], firms=row['firms'],
            monthly_revenue=Decimal(row['revenue']) * 1_000_000 / 12,
            cost_of_sales_ratio=share(split['cost_of_sales'], base) if split else None,
            payroll_ratio=share(split['payroll'], base) if split else None,
            rent_ratio=share(split['rent'], base) if split else None,
            other_ratio=share(split['other_cost'], base) if split else None,
            profit_ratio=share(row['profit'], Decimal(row['revenue'])),
            split_region=split_region, source=PROVIDER)
