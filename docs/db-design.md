# DB 설계안

> **진행 상황 (2026-11-26):** 1~5단계 구현 완료 (마이그레이션 001~005). 6단계는 서울 상권(006)과 KAMIS 소매 시세(007)를 CSV 파일로 연결했다 (`import_data.py`). 업종 평균 비용은 남아 있다.
> 구현에서 정한 사항은 5장에 정리했다.

작성일: 2026-11-22 (한국 시간). 기준: [decision-model-survey.md](decision-model-survey.md), [dataset-survey.md](dataset-survey.md), 현재 코드(`app/common/repository.py`, 모듈별 `repositories/memory.py`).

## 1. 기본 결정 (권장안)

| 항목 | 권장 | 이유 | 대안 |
|---|---|---|---|
| DBMS | **SQLite** (파일 1개, `instance/veni.db`) | 로컬 실행 프로토타입, 서버 설치 불필요, Python 표준 `sqlite3`로 의존성 추가 없음. `instance/`는 이미 Git 제외 대상 | 여러 사람이 동시에 쓰는 서버 배포 시 PostgreSQL로 이전 |
| 접근 방식 | 기존 **Repository 계약 유지**, SQLite 구현을 추가 | 모델·화면 코드를 거의 바꾸지 않고 저장소만 교체. 테스트는 메모리 구현으로 계속 실행 가능 | ORM(SQLAlchemy) 도입: 테이블이 많아지면 검토 |
| 스키마 관리 | `app/common/migrations/001_*.sql` 번호순 SQL 파일 + `schema_version` 테이블 | 단순하고 변경 이력이 남음 | Alembic (ORM 도입 시) |
| 금액·수량 저장 | 문자열(TEXT)로 저장해 `Decimal`로 복원 | SQLite REAL은 부동소수점이라 원 단위 계산 오차 발생 | 정수(원 단위) 저장 |

## 2. 먼저 풀어야 할 문제: 작업 공간 유지

지금은 브라우저 세션에 임의 ID를 두고, 서버를 켤 때마다 `SECRET_KEY`를 새로 만든다.
DB에 저장해도 **서버를 재시작하면 세션이 무효가 되어 저장한 데이터에 다시 접근할 수 없다.**

- `SECRET_KEY`를 `.env`(Git 제외)에 고정하고, 없으면 첫 실행 때 `instance/`에 생성해 재사용한다.
- 로그인은 이번 범위 밖이다. 대신 화면에 **작업 공간 코드**를 보여주고, 다른 브라우저에서 코드를 입력하면 같은 데이터를 열 수 있게 한다.
- 메모리 저장소의 24시간 자동 삭제가 사라지므로 **"내 데이터 삭제" 기능**과 보관 기간 정책(예: 마지막 접속 후 1년)을 함께 둔다.

## 3. 테이블

### A. 작업 공간과 분석 기록 (현재 메모리 저장소 대체)

| 테이블 | 주요 컬럼 | 용도 |
|---|---|---|
| `workspaces` | `id` (PK), `created_at`, `last_seen_at` | 익명 작업 공간 |
| `analysis_records` | `id`, `workspace_id`, `module`, `inputs_json`, `result_json`, `source`, `created_at` | 모듈별 계산 기록. 최근 1건만이 아니라 **이력**을 남김 (최신 = 가장 늦은 `created_at`) |

### B. 운영 기록 (사용자가 쌓는 데이터)

| 테이블 | 주요 컬럼 | 쓰는 모델 |
|---|---|---|
| `materials` | `id`, `workspace_id`, `name`, `base_unit` (g/mL/개), `yield_rate` | 수율 보정, 레시피 합산 |
| `material_purchases` | `material_id`, `purchased_on`, `unit`, `quantity`, `unit_price` | 최근 단가, 단가 추세 |
| `menus` | `id`, `workspace_id`, `name`, `price`, `other_variable_cost`, `active` | 메뉴 가격, 메뉴 엔지니어링 |
| `recipe_items` | `menu_id`, `material_id`, `quantity`, `unit` | **레시피 합산** (메뉴 원가 = 재료 N개 합) |
| `menu_sales` | `menu_id`, `period` (YYYY-MM), `quantity`, `price` | **메뉴 엔지니어링**, 가격 탄력성, 05 매출 합산 |
| `monthly_financials` | `workspace_id`, `period`, `revenue`, `rent`, `labor`, `material`, `utilities`, `advertising`, `other` | 05 전월 비교, 민감도 기준값, 매출 예측 |
| `location_candidates` | `id`, `workspace_id`, `name`, `region_code`, `lat`, `lng`, `rent`, `deposit`, `area`, `interior`, `fit`, `traffic`, `facility` | **후보 N곳** TOPSIS, 상권 지표 연결 |
| `campaigns` | `id`, `workspace_id`, `channel`, `owner` (직접/업체), `started_on`, `ended_on`, `cost`, `hours_per_week`, `new_customers`, `revenue_before`, `revenue_after` | 캠페인 성과 비교, 예산 배분 |

### C. 외부 참고 데이터 (공공데이터 수집 결과)

| 테이블 | 주요 컬럼 | 채울 데이터 |
|---|---|---|
| `datasets` | `id`, `provider`, `name`, `url`, `license`, `as_of`, `fetched_at`, `row_count` | 모든 외부 데이터의 출처·기준 시점·이용 조건 (화면 출처 표시용) |
| `regions` | `code`, `level` (시도/시군구/행정동/서울 상권), `name`, `parent_code` | 지역 코드 매핑 |
| `industries`, `industry_code_map` | 앱 업종 코드 ↔ 출처별 업종 코드 | 서울 상권·상가정보·인허가·실태조사 분류 연결 |
| `area_metrics` | `dataset_id`, `region_code`, `industry_code`, `period`, `metric`, `value` | 추정매출, 유동인구, 점포 수, 개폐업률, 임대료, 공실률 |
| `price_series` | `dataset_id`, `item_code`, `item_name`, `observed_on`, `price`, `unit` | KAMIS 시세 |
| `industry_benchmarks` | `dataset_id`, `industry_code`, `year`, `metric`, `value` | 업종 평균 비용 구조, 가맹 평균매출 |

외부 데이터는 원본 전체가 아니라 모델이 쓰는 단위(지역 × 업종 × 기간)로 집계해 저장한다. API 키는 `.env`에만 둔다.

## 4. 구현 순서

| 단계 | 내용 | 결과 | 외부 키 필요 | 상태 |
|---|---|---|---|---|
| 1 | SQLite 기반·마이그레이션, `analysis_records`로 메모리 저장소 교체, `SECRET_KEY` 고정, 작업 공간 코드·데이터 삭제 | 화면 동작은 그대로, 서버를 재시작해도 결과 유지 | 아니오 | ✅ `001` |
| 2 | 재료·메뉴·레시피 (B의 앞 4개) + 관리 화면 | 레시피 합산, 메뉴 여러 개 | 아니오 | ✅ `002` |
| 3 | 메뉴 판매·월별 재무 기록 | 메뉴 엔지니어링, 05 불러오기를 메뉴 전체 합산으로 개선 | 아니오 | ✅ `003` |
| 4 | 입지 후보 N곳 | 01 후보 3곳 이상 TOPSIS | 아니오 | ✅ `004` |
| 5 | 캠페인 기록 | 04 캠페인 성과 비교 | 아니오 | ✅ `005` |
| 6 | 외부 데이터 테이블(C) + 수집 스크립트 | 상권 지표, 시세, 업종 평균 | 아니오 (CSV 파일) | 🔶 서울 상권 `006`·KAMIS 시세 `007` 완료, 업종 평균 남음 |

1~5단계는 인증키 없이 진행할 수 있다. 6단계 전까지 인증키를 준비하면 된다.

## 5. 결정 사항

| 항목 | 결정 | 구현 |
|---|---|---|
| DBMS | SQLite로 시작 | `app/common/db.py`, 파일 없으면 메모리 SQLite(테스트) |
| 작업 공간 | 로그인 없이 작업 공간 코드 | 화면 오른쪽 위 "코드 보기" (`/workspace/`), 코드로 열기·전체 삭제 |
| 보관 기간 | 마지막 접속 후 365일 | 앱 시작 시 `purge_inactive(365)` |
| 서명 키 | `instance/secret_key`에 생성·재사용 | `VENI_SECRET_KEY` 환경변수가 있으면 우선 |
| 상권 지표 범위 | 서울 우선, 상권 단위 | 서울시 상권분석서비스 CSV (인증키 없이 파일로) |

설계와 달라진 점:

- 계획한 `menus.price`, `active` 컬럼 대신 가격은 판매 기록(`menu_sales.price`)에 달마다 저장한다. `menus`에는 기타 변동비(`other_cost`)를 둔다.
- `location_candidates.region_code`는 컬럼만 만들어 두었다(6단계에서 상권 지표 연결용). 위도·경도는 아직 두지 않았다.
- `campaigns`에 캠페인 이름·메모 컬럼을 추가했다.
- `materials`에 구매 단위(`unit`)를 두고 기준 단위(g/mL/개)는 계산으로 구한다. `material_purchases`는 구매일 대신 저장 시각(`purchased_at`)을 기록한다.

## 6. 6단계 진행

### 6-1. 서울 상권 (완료)

- 방식: API 대신 서울 열린데이터광장 CSV 파일을 `data/raw/`에 두고 `import_data.py`로 불러온다. 인증키가 필요 없고 같은 파일이면 결과가 같다.
- 단위: **상권**(골목·발달·전통시장·관광특구 1,650곳). `-상권배후지`는 골목상권만 있고 `-서울시`는 서울 합계 1줄이라 쓰지 않는다.
- 테이블 (`006_seoul_areas.sql`): 3장 C의 `area_metrics` 하나 대신 모델이 쓰는 모양대로 나눴다.

| 테이블 | 내용 | 행 수 (2026-11-26 파일) |
|---|---|---|
| `datasets` | 파일별 출처·기간·행 수·불러온 시각 | 8 |
| `areas` | 상권 코드·이름·구분·자치구·행정동·좌표·면적 | 1,650 |
| `area_sales` | 상권 × 분기 × 업종 추정매출 (요일·시간대·성별·연령대) | 128,053 |
| `area_stores` | 상권 × 분기 × 업종 점포·개폐업 | 456,659 |
| `area_counts` | 상권 × 분기 × 지표 한 값 (유동·직장·상주인구, 가구, 집객시설, 지하철역, 버스정거장) | 약 25만 |
| `area_change` | 상권 변화 지표 | 36,300 |

- 앱 연결: `app/reference/seoul_areas.py`의 `SeoulAreaData`가 `AreaDataProvider` 계약을 구현하고 `main/application.py`에서 01에 주입한다.
  01은 후보의 `location_candidates.region_code`에 상권 코드를 저장하고, 비교 때 최신 분기 지표를 결과에 함께 저장한다.
- 해석: "당월_매출_금액"은 서울 커피-음료 합계가 분기당 약 7천억 원(연 약 2.9조 원)이라 분기 합계로 보았다.

### 6-2. KAMIS 소매 시세 (완료, 내 PC 계산용)

- 수집: KAMIS "세부가격정보 > 소매가격 > 부류별·월간" 화면은 한 달 치 전 품목을 한 표로 보여 준다. 월 36개 × 지역 2개(전국·서울) × (전체·가공식품) = 144회를
  앱 내장 브라우저에서 3초 간격으로 조회해 `data/raw/KAMIS_소매가격_월별_2023-11_2026-10.csv` (11,182행, 102개 품목·236개 규격)로 저장했다.
- 이용 조건: robots.txt는 해당 화면을 막지 않는다. 다만 가격 화면에 공공누리 표시가 없고, aT 저작권 정책상 공공누리 미부착 자료의 복제·배포는 사전 협의가 필요하다.
  그래서 원본·DB는 Git에서 제외하고 내 PC 계산에만 쓴다. 공유·공개 서비스에는 KAMIS Open API 등 공식 경로가 필요하다.
- 테이블 `price_series` (지역·월·품목·품종·단위·등급·가격), `materials.market_item` (NULL 자동, '' 비교 안 함, 그 외 `품목|품종|단위|등급`).
- 없는 품목: 축산물(소·돼지·닭·계란)과 우유·원두·설탕·밀가루 등 가공 원재료.

### 6-3. 남은 데이터

1. 소상공인실태조사 업종 평균 비용 → 05 비용 구조 비교 (`industry_benchmarks`)
2. 축산물 가격(축산물품질평가원), 가공 원재료 가격(참가격) → 02 시세 비교 확대
3. 필요해지면: 상권 자동 갱신(API), 주소·좌표로 상권 찾기 (`areas.x`, `areas.y`는 TM 좌표로 저장해 둠)
