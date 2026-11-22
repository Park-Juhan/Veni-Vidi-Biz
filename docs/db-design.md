# DB 설계안 (초안)

작성일: 2026-11-22 (한국 시간). 기준: [decision-model-survey.md](decision-model-survey.md), [dataset-survey.md](dataset-survey.md), 현재 코드(`app/common/repository.py`, 모듈별 `repositories/memory.py`).

## 1. 기본 결정 (권장안)

| 항목 | 권장 | 이유 | 대안 |
|---|---|---|---|
| DBMS | **SQLite** (파일 1개, `instance/veni.db`) | 로컬 실행 프로토타입, 서버 설치 불필요, Python 표준 `sqlite3`로 의존성 추가 없음. `instance/`는 이미 Git 제외 대상 | 여러 사람이 동시에 쓰는 서버 배포 시 PostgreSQL로 이전 |
| 접근 방식 | 기존 **Repository 계약 유지**, SQLite 구현을 추가 | 모델·화면 코드를 거의 바꾸지 않고 저장소만 교체. 테스트는 메모리 구현으로 계속 실행 가능 | ORM(SQLAlchemy) 도입: 테이블이 많아지면 검토 |
| 스키마 관리 | `app/db/migrations/001_*.sql` 번호순 SQL 파일 + `schema_version` 테이블 | 단순하고 변경 이력이 남음 | Alembic (ORM 도입 시) |
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

| 단계 | 내용 | 결과 | 외부 키 필요 |
|---|---|---|---|
| 1 | SQLite 기반·마이그레이션, `analysis_records`로 메모리 저장소 교체, `SECRET_KEY` 고정, 작업 공간 코드·데이터 삭제 | 화면 동작은 그대로, 서버를 재시작해도 결과 유지 | 아니오 |
| 2 | 재료·메뉴·레시피 (B의 앞 4개) + 관리 화면 | 레시피 합산, 메뉴 여러 개 | 아니오 |
| 3 | 메뉴 판매·월별 재무 기록 | 메뉴 엔지니어링, 05 불러오기를 메뉴 전체 합산으로 개선 | 아니오 |
| 4 | 입지 후보 N곳 | 01 후보 3곳 이상 TOPSIS | 아니오 |
| 5 | 캠페인 기록 | 04 캠페인 성과 비교 | 아니오 |
| 6 | 외부 데이터 테이블(C) + 수집 스크립트 | 상권 지표, 시세, 업종 평균 | **예** |

1~5단계는 인증키 없이 진행할 수 있다. 6단계 전까지 인증키를 준비하면 된다.

## 5. 결정이 필요한 것

1. DBMS: SQLite로 시작해도 되는지 (권장: 예)
2. 작업 공간: 로그인 없이 "작업 공간 코드" 방식으로 충분한지
3. 데이터 보관 기간: 마지막 접속 후 1년 등 기준
4. 상권 지표 범위: 서울 우선 여부 (6단계 전까지)
