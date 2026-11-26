"""Seoul commercial-area statistics (서울시 상권분석서비스, 상권 단위 CSV files).

import_folder() loads the downloaded CSV files into SQLite; SeoulAreaData answers the
AreaDataProvider contract for the property module. Only the standard library is used.
"""
import csv
from pathlib import Path

from app.common.db import utc_now
from app.integrations.contracts import AreaOption, AreaSnapshot

PROVIDER = '서울 열린데이터광장 · 서울시 상권분석서비스'
BATCH = 5000
TIME_BANDS = (('00_06', '00~06시'), ('06_11', '06~11시'), ('11_14', '11~14시'), ('14_17', '14~17시'), ('17_21', '17~21시'), ('21_24', '21~24시'))
AGE_BANDS = (('10', '10대'), ('20', '20대'), ('30', '30대'), ('40', '40대'), ('50', '50대'), ('60', '60대 이상'))


class DataImportError(ValueError):
    """A file is missing columns or cannot be read."""


def number(text):
    text = (text or '').strip()
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return int(float(text))


def read_rows(path):
    """Yield dict rows; Seoul files are CP949, re-saved files may be UTF-8."""
    head = Path(path).read_bytes()[:200000]
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            head.decode(encoding)
        except UnicodeDecodeError as exc:
            # A multi-byte character cut at the sample end is fine; anything earlier is the wrong encoding.
            if exc.start < len(head) - 4:
                continue
        break
    with open(path, encoding=encoding, newline='') as handle:
        yield from csv.DictReader(handle)


def need(row, columns, name):
    missing = [c for c in columns if c not in row]
    if missing:
        raise DataImportError(f'{name}: 열이 없습니다 ({", ".join(missing[:5])}). 상권 단위 파일인지 확인하세요.')


# ---- one loader per file kind: (row) -> tuple for its table ----

def _area(row):
    return (row['상권_코드'], row['상권_코드_명'].strip(), row['상권_구분_코드_명'], row['자치구_코드_명'], row['행정동_코드_명'],
            number(row['엑스좌표_값']), number(row['와이좌표_값']), number(row['영역_면적']))


def _sales(row):
    times = [number(row[f'시간대_{a}~{b}_매출_금액']) for a, b in (band[0].split('_') for band in TIME_BANDS)]
    ages = [number(row[f'연령대_{age}_매출_금액' if age != '60' else '연령대_60_이상_매출_금액']) for age, _ in AGE_BANDS]
    return (row['상권_코드'], row['기준_년분기_코드'], row['서비스_업종_코드'], row['서비스_업종_코드_명'],
            number(row['당월_매출_금액']), number(row['당월_매출_건수']), number(row['주말_매출_금액']),
            *times, number(row['남성_매출_금액']), number(row['여성_매출_금액']), *ages)


def _stores(row):
    return (row['상권_코드'], row['기준_년분기_코드'], row['서비스_업종_코드'], row['서비스_업종_코드_명'],
            number(row['전체_점포_수']), number(row['프랜차이즈_점포_수']), number(row['개업_율']), number(row['개업_점포_수']),
            number(row['폐업_률']), number(row['폐업_점포_수']))


def _change(row):
    return (row['상권_코드'], row['기준_년분기_코드'], row['상권_변화_지표'], row['상권_변화_지표_명'],
            number(row['운영_영업_개월_평균']), number(row['폐업_영업_개월_평균']),
            number(row['서울_운영_영업_개월_평균']), number(row['서울_폐업_영업_개월_평균']))


# metric name -> source column, for the one-number-per-area files
COUNTS = {
    '길단위인구': {'footfall': '총_유동인구_수'},
    '상주인구': {'residents': '총_상주인구_수', 'households': '총_가구_수'},
    '직장인구': {'workers': '총_직장_인구_수'},
    '집객시설': {'facilities': '집객시설_수', 'subway': '지하철_역_수', 'bus_stops': '버스_정거장_수'},
}

SALES_SQL = ('INSERT OR REPLACE INTO area_sales VALUES (' + ', '.join('?' * 21) + ')')
TABLES = {
    # file kind: (table, insert sql, row loader, has quarter column)
    '영역': ('areas', 'INSERT OR REPLACE INTO areas VALUES (?, ?, ?, ?, ?, ?, ?, ?)', _area, False),
    '추정매출': ('area_sales', SALES_SQL, _sales, True),
    '점포': ('area_stores', 'INSERT OR REPLACE INTO area_stores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', _stores, True),
    '상권변화지표': ('area_change', 'INSERT OR REPLACE INTO area_change VALUES (?, ?, ?, ?, ?, ?, ?, ?)', _change, True),
}


def kind_of(path):
    """'서울시 상권분석서비스(추정매출-상권).csv' -> '추정매출'; other units (-상권배후지, -서울시) are skipped."""
    stem = Path(path).stem
    if '(' not in stem or not stem.endswith('-상권)'):
        return None
    kind = stem[stem.rindex('(') + 1:-len('-상권)')]
    return kind if kind in TABLES or kind in COUNTS else None


def import_file(database, path):
    """Replace one dataset with the contents of its CSV file. Returns (dataset name, rows)."""
    kind = kind_of(path)
    if kind is None:
        raise DataImportError(f'{Path(path).name}: 서울시 상권분석서비스의 "-상권" 단위 파일이 아닙니다.')
    name = f'{kind}-상권'
    periods, rows = set(), 0
    with database.connect() as connection:
        connection.execute('INSERT INTO datasets VALUES (?, ?, ?, NULL, NULL, 0, ?) ON CONFLICT(name) DO UPDATE SET file_name = excluded.file_name, imported_at = excluded.imported_at', (name, PROVIDER, Path(path).name, utc_now()))
        if kind in COUNTS:
            metrics = COUNTS[kind]
            connection.execute('DELETE FROM area_counts WHERE dataset = ?', (name,))
            sql, loader = 'INSERT OR REPLACE INTO area_counts VALUES (?, ?, ?, ?, ?)', None
        else:
            table, sql, loader, _ = TABLES[kind]
            connection.execute(f'DELETE FROM {table}')
        batch = []
        for row in read_rows(path):
            if rows == 0:
                need(row, ['상권_코드', *(metrics.values() if loader is None else [])], name)
            if loader is None:
                period = row['기준_년분기_코드']
                batch.extend((row['상권_코드'], period, metric, number(row[column]), name) for metric, column in metrics.items())
            else:
                try:
                    batch.append(loader(row))
                except KeyError as exc:
                    raise DataImportError(f'{name}: 열이 없습니다 ({exc.args[0]}).') from exc
                period = row.get('기준_년분기_코드')
            if period:
                periods.add(period)
            rows += 1
            if len(batch) >= BATCH:
                connection.executemany(sql, batch); batch.clear()
        if batch:
            connection.executemany(sql, batch)
        connection.execute('UPDATE datasets SET period_from = ?, period_to = ?, row_count = ? WHERE name = ?',
                           (min(periods) if periods else None, max(periods) if periods else None, rows, name))
    return name, rows


def import_folder(database, folder):
    """Import every recognised file in folder (영역 first). Returns [(file name, dataset, rows)]; unknown files are skipped."""
    files = sorted((p for p in Path(folder).glob('*.csv') if kind_of(p)), key=lambda p: kind_of(p) != '영역')
    results = []
    for path in files:
        dataset, rows = import_file(database, path)
        results.append((path.name, dataset, rows))
    return results


def quarter_label(period):
    return f'{period[:4]}년 {period[4:]}분기' if period and len(period) == 5 else (period or '')


class SeoulAreaData:
    """Read side of the imported Seoul data; implements AreaDataProvider."""

    def __init__(self, database):
        self.database = database
        self._options = None

    def available(self):
        try:
            with self.database.connect() as connection:
                return connection.execute('SELECT 1 FROM areas LIMIT 1').fetchone() is not None
        except Exception:  # missing tables (database not migrated)
            return False

    def area_options(self):
        if self._options is None:
            with self.database.connect() as connection:
                rows = connection.execute('SELECT code, name, kind, district, dong FROM areas ORDER BY district, name').fetchall()
            labels = [f"{r['name']} · {r['district']} {r['dong']} · {r['kind']}" for r in rows]
            duplicated = {label for label in labels if labels.count(label) > 1}
            self._options = [AreaOption(r['code'], label + (f" · {r['code']}" if label in duplicated else ''))
                             for r, label in zip(rows, labels)]
        return self._options

    def resolve(self, text):
        """Area code for a datalist label, an exact unique name, or a code; None if not found."""
        text = (text or '').strip()
        options = self.area_options()
        for option in options:
            if text in (option.label, option.code):
                return option.code
        by_name = [o for o in options if o.label.split(' · ')[0] == text]
        return by_name[0].code if len(by_name) == 1 else None

    def label(self, code):
        return next((o.label for o in self.area_options() if o.code == code), '')

    def industries(self):
        with self.database.connect() as connection:
            return [r['industry'] for r in connection.execute('SELECT DISTINCT industry FROM area_sales ORDER BY industry')]

    def snapshot(self, code, industry):
        with self.database.connect() as connection:
            area = connection.execute('SELECT * FROM areas WHERE code = ?', (code,)).fetchone()
            if area is None:
                return None
            latest = connection.execute('SELECT MAX(period) AS p FROM area_sales').fetchone()['p'] \
                or connection.execute('SELECT MAX(period) AS p FROM area_stores').fetchone()['p']
            sales = connection.execute('SELECT * FROM area_sales WHERE area_code = ? AND period = ? AND industry = ?', (code, latest, industry)).fetchone()
            stores = connection.execute('SELECT * FROM area_stores WHERE area_code = ? AND period = ? AND industry = ?', (code, latest, industry)).fetchone()
            counts = {}
            for metric in ('footfall', 'residents', 'workers', 'facilities', 'subway', 'bus_stops'):
                # Latest published quarter up to the sales quarter.
                found = connection.execute('SELECT value FROM area_counts WHERE area_code = ? AND metric = ? AND period <= ? ORDER BY period DESC LIMIT 1',
                                           (code, metric, latest or '99999')).fetchone()
                counts[metric] = found['value'] if found else None
            change = connection.execute('SELECT indicator_name FROM area_change WHERE area_code = ? AND period <= ? ORDER BY period DESC LIMIT 1',
                                        (code, latest or '99999')).fetchone()
            datasets = [r['name'] for r in connection.execute('SELECT name FROM datasets ORDER BY name')]
        top_age = top_time = None
        if sales and sales['amount']:
            top_age = max(AGE_BANDS, key=lambda band: sales[f'age_{band[0]}'])[1]
            top_time = max(TIME_BANDS, key=lambda band: sales[f'time_{band[0]}'])[1]
        if counts['facilities'] is not None and counts['subway'] is None:
            counts['subway'] = 0
        if counts['facilities'] is not None and counts['bus_stops'] is None:
            counts['bus_stops'] = 0
        return AreaSnapshot(
            code=code, name=area['name'], kind=area['kind'], district=area['district'], dong=area['dong'],
            industry=industry, period=quarter_label(latest),
            sales=sales['amount'] if sales else None, sales_count=sales['count'] if sales else None,
            stores=stores['stores'] if stores else None, franchise=stores['franchise'] if stores else None,
            open_rate=stores['open_rate'] if stores else None, close_rate=stores['close_rate'] if stores else None,
            change=change['indicator_name'] if change else None, top_age=top_age, top_time=top_time,
            source=f"{PROVIDER} ({', '.join(datasets)})", **counts)
