"""More retail prices for the material comparison, stored next to KAMIS in price_series.

- 한국소비자원 「생필품 가격 정보」 (공공데이터포털 15083256, 이용허락 제한 없음): brand products per store;
  the size is read from the product name, e.g. "백설 하얀설탕(1kg)".
- 서울특별시 「생필품 농수축산물 가격 정보」 (서울 열린데이터광장 OA-1170, 이용허락 제한 없음): monthly prices
  of about 120 items in Seoul traditional markets and marts, e.g. "돼지고기 100g", "계란 10개".

Each file is reduced to the monthly median price per item and size.
"""
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import re
from statistics import median

from app.common.db import utc_now
from app.reference.seoul_areas import DataImportError, read_rows

SOURCES = {
    '참가격': ('한국소비자원_생필품', '한국소비자원 참가격 「생필품 가격 정보」 (공공데이터포털, 이용허락 제한 없음)', '참가격 브랜드 상품'),
    '서울시장': ('서울시_생필품_농수축산물', '서울특별시 「생필품 농수축산물 가격 정보」 (서울 열린데이터광장, 이용허락 제한 없음)', '서울 시장·마트 조사'),
}
SIZE = re.compile(r'(\d+(?:\.\d+)?)\s*(kg|g|ml|mL|ML|l|L|개입|개|구)(?![a-zA-Z가-힣])')


def source_of(path):
    name = Path(path).name
    if not name.endswith('.csv'):
        return None
    return next((key for key, (prefix, *_) in SOURCES.items() if name.startswith(prefix)), None)


def split_size(text):
    """'백설 하얀설탕(1kg)' -> ('백설 하얀설탕', '1kg'); '돼지고기 100g' -> ('돼지고기', '100g');
    '배추(봄) 1포기' -> ('배추(봄)', '1포기'); '라면 5개입 1봉' -> ('라면', '5개')."""
    text = ' '.join((text or '').split())
    match = SIZE.search(text)
    if match:
        unit = match.group(2).lower().replace('개입', '개').replace('구', '개')
        unit = {'ml': 'mL', 'l': 'L'}.get(unit, unit)
        item = text[:match.start()].rstrip(' ,(')
        return (item or text), f'{match.group(1)}{unit}'
    if ' ' in text and text.rsplit(' ', 1)[1][:1].isdigit():  # '1포기', '1마리(대)'
        item, unit = text.rsplit(' ', 1)
        return item, unit
    return text, '-'


def month_of(text):
    text = (text or '').strip()
    for fmt in ('%Y-%m', '%b-%y', '%Y-%m-%d'):
        try:
            return datetime.strptime(text[:10] if fmt == '%Y-%m-%d' else text, fmt).strftime('%Y-%m')
        except ValueError:
            continue
    return None


def _price(text):
    text = (text or '').replace(',', '').strip()
    try:
        value = int(float(text))
    except ValueError:
        return None
    return value if value > 0 else None


def collect(source, path):
    """{(region, month, item, kind, unit, rank): [prices]} for one file."""
    groups = defaultdict(list)
    for index, row in enumerate(read_rows(path)):
        if source == '참가격':
            if index == 0 and not {'상품명', '조사일', '판매가격'} <= set(row):
                raise DataImportError(f'{Path(path).name}: 상품명·조사일·판매가격 열이 없습니다.')
            item, unit = split_size(row['상품명'])
            key = ('전국', month_of(row['조사일']), item, SOURCES[source][2], unit, '-')
            price = _price(row['판매가격'])
        else:
            if index == 0 and not {'품목 이름', '가격(원)', '년도-월'} <= set(row):
                raise DataImportError(f'{Path(path).name}: 품목 이름·가격(원)·년도-월 열이 없습니다.')
            item, unit = split_size(row['품목 이름'])
            key = ('서울', month_of(row['년도-월']) or month_of(row.get('점검일자')), item, SOURCES[source][2], unit,
                   (row.get('시장유형 구분(시장/마트) 이름') or '-').strip())
            price = _price(row['가격(원)'])
        if price is not None and key[1] and item:
            groups[key].append(price)
    return groups


def import_files(database, paths):
    """Import every file of one source together (e.g. 2024 + 2025) and replace that source's rows."""
    source = source_of(paths[0])
    groups = defaultdict(list)
    for path in paths:
        for key, prices in collect(source, path).items():
            groups[key].extend(prices)
    rows = [(*key[:2], '', *key[2:], int(median(prices)), source) for key, prices in groups.items()]
    months = {row[1] for row in rows}
    with database.connect() as connection:
        connection.execute('DELETE FROM price_series WHERE source = ?', (source,))
        connection.executemany('INSERT OR REPLACE INTO price_series (region, month, category, item, kind, unit, rank, price, source) '
                               'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)
        connection.execute('INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET file_name = excluded.file_name, '
                           'period_from = excluded.period_from, period_to = excluded.period_to, row_count = excluded.row_count, imported_at = excluded.imported_at',
                           (f'{source} 가격', SOURCES[source][1], ', '.join(Path(p).name for p in paths),
                            min(months, default=None), max(months, default=None), len(rows), utc_now()))
    return f'{source} 가격', len(rows)
