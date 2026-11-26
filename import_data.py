"""Load downloaded public data files into the app database.

    .venv\\Scripts\\python.exe import_data.py                 # data/raw -> instance/veni.db
    .venv\\Scripts\\python.exe import_data.py D:\\files --database other.db

Recognised now: 서울시 상권분석서비스 "-상권" CSV files (영역, 추정매출, 점포, 길단위인구,
상주인구, 직장인구, 집객시설, 상권변화지표). Other files are listed and skipped.
"""
import argparse
import os
from pathlib import Path
import sys
import time

from app.common.db import Database
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
    known = sorted((p for p in files if kind_of(p)), key=lambda p: kind_of(p) != '영역')
    for path in files:
        if not kind_of(path):
            print(f'건너뜀  {path.name} (상권 단위 파일이 아님)')
    if not known:
        print('불러올 파일이 없습니다. 서울시 상권분석서비스 "-상권" CSV 파일을 넣어 주세요.', file=sys.stderr)
        return 1
    for path in known:
        started = time.perf_counter()
        try:
            dataset, rows = import_file(database, path)
        except (DataImportError, UnicodeDecodeError) as exc:
            print(f'실패    {path.name}: {exc}', file=sys.stderr)
            return 1
        print(f'완료    {dataset:<16} {rows:>9,}행  {time.perf_counter() - started:5.1f}초')
    print(f'저장 위치: {database.path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
