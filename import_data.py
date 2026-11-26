"""Load downloaded public data files into the app database.

    .venv\\Scripts\\python.exe import_data.py                 # data/raw -> instance/veni.db
    .venv\\Scripts\\python.exe import_data.py D:\\files --database other.db

Recognised now: 서울시 상권분석서비스 "-상권" CSV files (영역, 추정매출, 점포, 길단위인구,
상주인구, 직장인구, 집객시설, 상권변화지표), KAMIS_소매가격_월별_*.csv,
KOSIS_소상공인실태조사_업종별_경영지표_*.csv, KOSIS_소상공인실태조사_창업비용_임차_*.csv,
외식비_시도별_*.csv, aTFIS_국제원료_*.csv, KOSIS_부동산원_소규모상가_임대료_*.csv, 한국소비자원_생필품*.csv and 서울시_생필품_농수축산물*.csv.
Other files are skipped.
"""
import argparse
import os
from pathlib import Path
import sys
import time

from app.common.db import Database
from app.reference import commodities, consumer_prices, dineout, kamis, kosis, rents
from app.reference.seoul_areas import DataImportError, import_file, kind_of

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description='Import public data CSV files into the VENI VIDI BIZ database.')
    parser.add_argument('folder', nargs='?', default=str(ROOT / 'data' / 'raw'))
    parser.add_argument('--database', default=os.environ.get('VENI_DATABASE') or str(ROOT / 'instance' / 'veni.db'))
    args = parser.parse_args(argv)
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f'폴더가 없습니다: {folder}', file=sys.stderr)
        return 2
    database = Database(args.database)
    database.migrate()
    files = sorted(folder.glob('*.csv'))
    single = (kind_of, kamis.is_kamis, kosis.is_kosis, kosis.is_startup, dineout.is_dineout, commodities.is_commodity, rents.is_rent)
    known = sorted((p for p in files if any(test(p) for test in single)), key=lambda p: kind_of(p) != '영역')
    # Consumer price files of one source (e.g. 서울 2024 + 2025) are imported together.
    grouped = {}
    for path in files:
        if consumer_prices.source_of(path): grouped.setdefault(consumer_prices.source_of(path), []).append(path)
    known += [paths for paths in grouped.values()]
    for path in files:
        if path not in known and not consumer_prices.source_of(path):
            print(f'건너뜀  {path.name} (알 수 없는 파일 또는 상권 단위가 아님)')
    if not known:
        print('불러올 파일이 없습니다. 서울시 상권분석서비스 "-상권" CSV 또는 KAMIS_소매가격_월별 CSV 파일을 넣어 주세요.', file=sys.stderr)
        return 1
    for path in known:
        started = time.perf_counter()
        try:
            if isinstance(path, list):
                dataset, rows = consumer_prices.import_files(database, path)
            else:
                loader = (kamis.import_file if kamis.is_kamis(path) else kosis.import_file if kosis.is_kosis(path)
                          else kosis.import_startup_file if kosis.is_startup(path) else dineout.import_file if dineout.is_dineout(path)
                          else commodities.import_file if commodities.is_commodity(path) else rents.import_file if rents.is_rent(path) else import_file)
                dataset, rows = loader(database, path)
        except (DataImportError, UnicodeDecodeError) as exc:
            name = ', '.join(p.name for p in path) if isinstance(path, list) else path.name
            print(f'실패    {name}: {exc}', file=sys.stderr)
            return 1
        print(f'완료    {dataset:<16} {rows:>9,}행  {time.perf_counter() - started:5.1f}초')
    print(f'저장 위치: {database.path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
