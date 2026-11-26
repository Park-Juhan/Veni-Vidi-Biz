# Veni-Vidi-Biz

Start · Predict · Succeed — 소규모 사업자를 위한 창업·운영 의사결정 웹 프로토타입.

Python + Flask + Jinja + HTML/CSS로 만든 로컬 실행 프로토타입입니다.
Flask는 독립 URL과 MVC 분리가 명확하며 별도 프런트엔드 빌드 없이 실행할 수 있어 선택했습니다.
정밀 계산에는 Python `Decimal`, 저장에는 표준 `sqlite3`, 차트에는 CSS, 테스트에는 표준 `unittest`를 사용합니다.
런타임 의존성은 Flask 하나입니다.

## 실행

Python 3.12 권장 (실제 검증: Python 3.12.9, Windows, Chrome).

```powershell
# 내려받은 프로젝트의 루트 폴더에서 실행
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

브라우저에서 **http://127.0.0.1:5000** 을 엽니다. 활성화 스크립트를 실행하지 않아도 됩니다.
이미 가상환경이 준비되어 있으면 마지막 명령만 실행하세요. 종료는 실행 터미널에서 `Ctrl+C`입니다.
기본 포트가 사용 중이면 `run.py --port 5001`로 실행합니다.

Linux/macOS에서는 가상환경 Python 경로를 `.venv/bin/python`으로 바꿉니다.
기본 실행은 로컬 PC 전용 개발 서버입니다. 외부 서비스 배포·인증은 이번 구현 범위가 아닙니다.

## 구현 범위

| 모듈 / 독립 URL | 실행되는 기능 | 사용한 모델·처리 방식 |
|---|---|---|
| 01 부동산 및 업장 `/property/` | 입지 후보를 **원하는 만큼 저장**하고 2곳 이상 골라 비교, 기준별 가중치 직접 설정, 초기 자금과 부족 자금 계산, 후보를 **서울 상권에 연결**해 매출·점포 수·유동인구 등 공개 통계 비교, **업종 평균 보증금·월세·창업비용 분포**와 비교 | 예산·면적 조건 그룹 우선 + **TOPSIS** (고객층·동선·시설·임대료·초기 자금·면적 + 상권 연결 시 점포당 매출·경쟁 점포 수·유동인구), Blackboard |
| 02 재료비 `/material-cost/` | 구매 비용, kg↔g·L↔mL 단위 환산, **수율(손질 손실) 보정**, 1회 사용 원가, **내 재료 목록** 저장과 구매 이력, 저장한 재료의 **소매 시세 비교**(KAMIS·참가격·서울 시장 조사, g·mL·개당 단가 차이, 1년 변화) | 일반 계산 Model |
| 03 메뉴 가격 `/menu-pricing/` | 목표 공헌이익률 기반 가격, **여러 재료 레시피 원가 합산**, 메뉴 저장, **월별 판매 기록**과 메뉴 분석, **지역 외식비 평균**(냉면·김치찌개 백반 등 9개 메뉴)과 가격 비교 | 원가 가산 가격, **메뉴 엔지니어링** (Kasavana-Smith: 스타·인기 저수익·저인기 고수익·저인기 저수익) |
| 04 마케팅 `/marketing/` | 홍보 방법 비교, **캠페인 기록** (기간·비용·신규 고객·전후 매출), 채널별 성과 요약을 추천에 함께 표시 | 규칙 점수 Blackboard + 신규 고객 1명당 비용(CAC)·수익률(ROI) |
| 05 비용 절감 및 운영 개선 `/cost-optimization/` | 비용 비중, 이전 월 대비 증감, 항목별 감축 시나리오, 손익분기 매출, **다른 모듈 값 불러오기**, **월별 매출·비용 기록** | CVP + Blackboard + **민감도 분석** (매출·재료비·인건비·임대료 ±10·20%) + **업종 평균 비교** (소상공인실태조사, 매출 대비 비율) |

모듈 간 연동 (모두 선택 사항이며, 원본 모듈이 꺼져 있거나 기록이 없으면 직접 입력으로 계산합니다):

- 02 → 03: 최근 재료 1건의 1회 사용 원가, 또는 내 재료 목록 단가로 레시피 원가를 계산합니다.
- 01·03·04 → 05: 임대료(01), 월 매출·재료비(03, 가장 최근 판매 기록 달 기준), 광고비(04)를 불러옵니다.
  불러온 값에는 출처 모듈, 기준, 저장 시각, 가상 예시 여부를 표시합니다.
- 05 월별 기록 → 05: 저장한 전월 총비용을 "이전 월 비용"으로 불러옵니다.

모든 모듈은 기본 가상 예시를 제공하며, 입력을 바꿔 계산할 수 있습니다. 기본값을 실제 시장 자료처럼 표시하지 않습니다.
결과에 출처, 계산 시점(KST), 계산 가정과 주의점을 표시합니다. 긴 입력은 단계별 창으로, 결과는 탭으로 나누어 보여줍니다.

각 모듈만 등록해 별도 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe run.py --module menu_pricing --port 5001
.\.venv\Scripts\python.exe run.py --module material_cost --module menu_pricing --port 5002
```

모듈 식별자: `property`, `material_cost`, `menu_pricing`, `marketing`, `cost_optimization`.

## 공공데이터 불러오기 (서울 상권 · 재료 시세 · 업종 평균 · 외식비 · 창업비용)

서울 열린데이터광장에서 "서울시 상권분석서비스"의 **상권 단위(`-상권`)** CSV 파일을 내려받아 `data/raw/`에 넣고 실행합니다.
인증키는 필요 없습니다. 원본 파일은 크기와 이용 조건 때문에 Git에서 제외됩니다(`data/raw/`).

```powershell
.\.venv\Scripts\python.exe import_data.py
```

| 파일 (`서울시 상권분석서비스(…-상권).csv`) | 쓰는 값 |
|---|---|
| 영역 (필수) | 상권 1,650곳의 이름·구분·자치구·행정동 (후보 연결용) |
| 추정매출 | 업종별 분기 추정매출·건수, 매출이 가장 큰 연령대·시간대 |
| 점포 | 업종별 점포 수·프랜차이즈 수·개업률·폐업률 |
| 길단위인구, 직장인구, 상주인구 | 유동인구, 직장인구, 상주인구 |
| 집객시설 | 집객시설·지하철역·버스정거장 수 |
| 상권변화지표 | 상권 변화 단계 (정체·다이나믹·상권확장·상권축소) |

- 실행 결과는 앱 DB(`instance/veni.db` 또는 `VENI_DATABASE`)에 저장됩니다. 다른 폴더는 `import_data.py <폴더>`로 지정합니다.
- 같은 파일을 다시 불러오면 이전 값을 지우고 새로 넣습니다. 새 분기 파일을 받으면 다시 실행하세요. 실행 후 서버를 다시 켜면 화면에 반영됩니다.
- **재료 시세:** `KAMIS_소매가격_월별_*.csv`(열: 월, 지역, 부류, 품목, 품종, 단위, 등급, 월평균가격)를 같은 폴더에 두면 함께 불러옵니다.
  현재 파일은 KAMIS "세부가격정보 > 소매가격 > 부류별·월간" 화면 값(2023-11~2026-10, 전국·서울, 102개 품목·236개 규격)을 내 PC 계산용으로 모은 것입니다.
  이 화면에는 공공누리 표시가 없으므로 원본·DB를 공유하거나 공개 서비스에 쓰려면 KAMIS Open API 등 공식 경로나 기관 협의가 필요합니다.
- 02 "내 재료 목록"은 재료 이름으로 시세 품목을 자동으로 찾고(예: 마늘 → 깐마늘(국산) 1kg 상품), "시세 품목 연결"에서 바꾸거나 끌 수 있습니다.
- **추가 시세 (이용허락 제한 없음):** `한국소비자원_생필품*.csv`(공공데이터포털 15083256, 참가격 상품별 판매가격)와
  `서울시_생필품_농수축산물*.csv`(서울 열린데이터광장 OA-1170, 서울 전통시장·마트 약 120개 품목 월별)도 같은 시세 표에 들어갑니다.
  상품명의 용량(예: 백설 하얀설탕(1kg), 돼지고기 100g)을 읽어 월별 중앙값으로 줄입니다. 서울 파일은 연도별로 나뉘어 있어 함께 불러옵니다.
  이로써 돼지·소·닭고기, 계란, 우유, 설탕, 밀가루, 버터, 식용유 등도 비교됩니다. 원두는 어느 출처에도 없습니다.
  자동 연결 우선순위: 단위 비교 가능 → 이름 일치 → KAMIS → 서울 시장 조사 → 참가격.
- **업종 평균:** `KOSIS_소상공인실태조사_업종별_경영지표_*.csv`(기준연도, 시도, 대분류, 업종, 기업체수, 매출액, 영업비용, 매출원가, 급여총액, 임차료, 기타비용, 영업이익; 기업체당 백만원/년).
  현재 파일은 KOSIS 「소상공인실태조사」 2023년 표(시도/산업중분류별 주요지표 `DT_3ME0100`, 영업비용 `DT_3ME0144`)의 전국·서울 값을 옮긴 것입니다.
  KOSIS 이용약관상 사전 승낙 없는 복제·제공이 제한되므로 KAMIS와 마찬가지로 내 PC 계산용으로만 씁니다.
  05 입력의 "업종 평균 비교" 단계에서 업종(기본: 음식점 및 주점업)과 지역(기본: 서울)을 고르면 결과에 비교 탭이 생깁니다.
- **외식비:** `외식비_시도별_*.csv`(월, 지역, 메뉴, 가격). 행정안전부 지방물가 외식비(참가격 「서비스가격정보 > 외식비」, 출처 국가데이터처)
  2025-10·2026-10 시도별 9개 메뉴 값을 옮긴 것으로 내 PC 계산용입니다. 03에서 "비교할 외식 메뉴"를 고르면 결과에 비교 탭이 생깁니다.
- **창업비용·임차:** `KOSIS_소상공인실태조사_창업비용_임차_*.csv`. 소상공인실태조사 2024 창업비용 구간 비율(`DT_3ME0126`)과
  기업체당 보증금·월세(`DT_3ME0132`)의 전국·서울 값으로 내 PC 계산용입니다. 01 "비교할 후보" 단계에서 업종을 고르면 비교 탭이 생깁니다.
- **원두:** 소매 시세 대신 `aTFIS_국제원료_*.csv`(aT 식품산업통계정보 FIS 「국제 원료가격」, ICE 아라비카 선물 주간 평균, 2024-10~2026-11)를
  불러와 이름에 원두·커피·생두가 들어간 재료에 국제 시세와 4주·1년 변화를 보여 줍니다. 생두 국제가라 단가를 직접 비교하지 않으며 내 PC 계산용입니다.
  쿠팡(봇 차단)·G마켓(약관상 스크래핑 금지)의 쇼핑몰 가격은 수집하지 않았습니다.
- `-상권배후지`, `-서울시`처럼 다른 단위 파일은 건너뜁니다. 실제 8개 파일 약 76만 행을 불러오는 데 약 10초, DB는 약 90MB입니다.
- 01 "내 후보 목록"에서 후보마다 상권을 검색해 고르면, 비교 결과에 "상권 지표" 탭이 생기고 업종(기본 커피-음료) 기준 지표가 TOPSIS에 더해집니다.
  비교하는 후보 중 한 곳이라도 상권이 없으면 상권 기준은 그 비교에서 빠지고 결과에 그 사실을 적습니다.

## 디렉터리와 책임

```text
app/
  common/
    model.py                 # Repository 계약을 사용하는 Model 기본 동작
    repository.py            # 분석 기록 저장 계약, 메모리·SQLite 구현
    db.py                    # SQLite 연결·마이그레이션·작업 공간·보관 기간 정리
    migrations/              # 번호순 스키마 SQL (001~011)
    validation.py            # 필드 계약과 숫자·선택값·필수값 검증
    decision.py              # Blackboard / KnowledgeSource / Control / Result
    web.py                   # 공통 요청 흐름·CSRF·오류/재표시·모듈별 확장 훅
    time.py                  # UTC 저장, KST 표시
    templates/               # 공통 레이아웃·단계 입력·결과 탭·작업 공간·홈·오류 화면
    static/                  # 반응형 CSS, 단계·탭·제출 상태 JS
  modules/
    property/                # repositories/candidates.py    입지 후보
    material_cost/           # repositories/catalog.py       재료·구매 이력
    menu_pricing/            # repositories/recipes.py, sales.py  메뉴·레시피·판매 기록
    marketing/               # repositories/campaigns.py     캠페인 기록
    cost_optimization/       # repositories/financials.py    월별 매출·비용, models/sensitivity.py
      # 각 모듈: controllers/routes.py, models/service.py,
      # repositories/memory.py, views/<모듈>/index.html
      # property/marketing/cost_optimization의 models/decision_engine/
  reference/seoul_areas.py   # 서울 상권 CSV 불러오기와 조회 (AreaDataProvider 구현)
  reference/kamis.py         # KAMIS 소매가격 CSV 불러오기와 조회 (MarketPriceProvider 구현)
  reference/kosis.py         # 소상공인실태조사 업종 평균 불러오기와 조회 (BenchmarkProvider 구현)
  reference/consumer_prices.py # 참가격·서울 시장 조사 가격 불러오기 (용량 해석, 월별 중앙값)
  reference/dineout.py       # 시도별 외식비 불러오기와 조회 (DineOutProvider 구현)
  reference/commodities.py   # aT FIS 국제 원료가격(커피) 불러오기와 추세 (CommodityTrendProvider 구현)
  integrations/contracts.py  # 공개 DTO와 Provider 인터페이스 (재료 원가, 재료 목록, 운영 비용, 상권 통계, 재료 시세, 업종 평균)
  main/application.py        # 조립 지점, 모듈 등록, 라우팅, 설정, 작업 공간 화면
tests/
  <모듈>/test_module.py      # 모듈 단독 MVC 흐름과 계산 정답
  module_support.py          # 모듈별 테스트 공통 흐름 (선택한 모듈만 조립)
  test_prototype.py          # 공통 검증·HTTP·내부 의존성·연동 계약
  test_database.py           # 마이그레이션·작업 공간·보관 기간·SQLite 저장
  test_recipes.py            # 재료 목록·레시피 원가 (02·03)
  test_sales.py              # 판매 기록·메뉴 엔지니어링·월별 재무 (03·05)
  test_candidates.py         # 입지 후보 N곳·TOPSIS (01)
  test_campaigns.py          # 캠페인 기록·성과 요약 (04)
  test_area_data.py          # 서울 상권 CSV 불러오기·조회·01 비교 연동
  test_market_prices.py      # KAMIS 시세 불러오기·자동 연결·02 단가 비교
  test_benchmarks.py         # 업종 평균 불러오기·지역 대체·05 비교
  test_consumer_prices.py    # 참가격·서울 시장 조사 용량 해석·중앙값·출처별 교체
  test_dineout_startup.py    # 외식비(03)·창업비용·임차 조건(01) 비교
  test_commodities.py        # 국제 커피 시세 추세(02)
  test_architecture.py       # 순환 참조·상대 import·MVC 데이터 접근 경계
  test_release_readiness.py  # 극단 입력·CLI·실제 Git 제외 규칙
  browser_smoke.py           # 선택적 실제 Chrome 화면 검증
docs/
  analysis-and-plan.md       # 세 문서 분석, 충돌 해결, 계산 가정, 개발 계획
  implementation-log.md      # 1차 구현 단계별 결과와 검증 기록
  release-review.md          # 1차 GitHub 업로드 전 점검 결과
  decision-model-survey.md   # 모듈별 의사결정 모델 조사
  dataset-survey.md          # 공공데이터 조사 (API·라이선스·지역 범위)
  db-design.md               # DB 설계와 단계별 진행 상황
run.py
import_data.py               # 공공데이터 CSV → DB 불러오기
requirements.txt
requirements-dev.txt
```

각 모듈의 Model이 자신의 Repository를 소유합니다. View/Controller가 Repository를 직접 조회하지 않습니다.
모듈끼리 내부 구현을 import하지 않습니다(`test_architecture.py`가 검사). `main/application.py`에서 의존성을 주입하며,
모듈 간 데이터는 `integrations/contracts.py`의 읽기 전용 스냅샷과 Provider 계약으로만 주고받습니다.
공통 View는 레이아웃·필드·단계·결과 표시를 재사용하고, 모듈별 View가 확장 지점을 갖습니다.

Blackboard는 요청마다 독립 작업 공간을 만듭니다. Knowledge Sources가 중간 결과와 대안을 기록하고,
Control Component가 규칙 적용 순서와 적용 여부를 제어하며 Result Generator가 결과를 반환합니다.
세 모듈의 규칙·작업 공간은 별개입니다. 재료 원가·가격 산식에는 적용하지 않습니다.

## 계산 기준과 한계

- 금액: 원. 운영 비용·매출·판매량: 월 단위. 마케팅 가용 시간: 주당 시간.
- 초기 자금 = 보증금 + 첫 달 임대료 + 시설·인테리어 + 장비 + 초기 재료 + 기타 비용.
  보증금은 묶이는 자금이며 영업비용과 구분합니다. 권리금 등은 기타 비용에 포함해 입력하세요.
- 입지 비교: 예산·면적 조건을 모두 충족하는 후보를 먼저 두고, 같은 그룹 안에서 TOPSIS 근접도로 순위를 매깁니다.
  가중치는 사용자가 정하며 합계 100%로 정규화합니다. 고객층·동선·시설은 사용자의 1~5 자가평가입니다.
- 업종 평균 비교: 각 비용 ÷ 월 매출(%)을 업종 평균(기업체당 연간 비용 ÷ 연간 매출)과 비교합니다. 재료비↔매출원가, 인건비↔급여총액, 임대료↔임차료,
  공과금·광고·기타↔기타비용으로 짝지었습니다. 영업이익은 대표자 본인 인건비를 빼기 전 금액입니다.
- 재료 시세 비교: (구매 단가 ÷ 단위 환산 − 시세 ÷ 조사 단위 환산) ÷ 시세. 수율은 양쪽 모두 반영하지 않습니다. 조사 단위가 포기·마리처럼
  g·mL·개로 바꿀 수 없거나 재료 단위와 차원이 다르면 비교하지 않습니다.
- 상권 지표: 점포당 월평균 추정매출 = 분기 추정매출 ÷ 점포 수 ÷ 3. 서울시가 카드 결제 등을 바탕으로 추정한 **상권 전체** 값이며
  후보 매물 한 곳의 실적이 아닙니다. 원자료 열 이름은 "당월_매출_금액"이지만 서울 합계 규모로 볼 때 분기 합계로 해석했습니다.
- 구매 비용 = 구매 단가 × 수량. 사용 원가 = 총 구매 비용 / (환산 구매량 × 수율) × 환산 사용량.
  구매 단가는 구매 단위 1개당 가격입니다. 밀도·배송비 자동 보정은 없습니다.
- 레시피 원가 = Σ(재료 기준 단위 원가 × 사용량). 저장한 메뉴는 재료의 **현재** 최근 단가로 다시 계산합니다.
- 메뉴 변동 원가 = 재료비 + 기타 변동비. 가격 = 변동 원가 / (1 - 목표 공헌이익률).
  계산 가격은 100원 단위로 올립니다. 공헌이익은 고정비·세금 차감 전 금액입니다.
  가격별 판매량은 입력 수량을 동일하게 유지하므로 가격 수요 변화 예측이 아닙니다.
- 메뉴 엔지니어링: 인기 기준 = 메뉴 수 균등 비중의 70%, 수익 기준 = 판매량 가중 평균 단위 공헌이익.
- 월 운영 손익 = 월 매출 - 입력한 월 비용. 손익분기 매출 = 고정비 / (1 - 재료비/매출).
  재료비만 매출에 비례한다고 가정하고 나머지는 고정비로 처리합니다.
  매출 0 또는 재료비 비율 100% 이상이면 손익분기 매출은 산출 불가로 표시합니다.
- 민감도 분석은 한 번에 한 항목만 바꿉니다. 매출이 바뀌면 재료비도 같은 비율로 바뀝니다.
- 절감액 = 항목 비용 × 사용자 지정 감축률. 절감 후 손익은 매출 유지 가정입니다.
  계약·인건비 법규·품질·위생 위험을 별도로 확인해야 합니다.
- 마케팅 추천의 비용·시간은 가상 예시입니다. 캠페인 기록의 CAC = 비용 / 신규 고객, ROI = (전후 매출 증가 - 비용) / 비용이며,
  다른 요인(계절·날씨 등)을 분리하지 않은 단순 비교입니다.
- 내부 계산은 `Decimal`로 수행하고 표시에서 소수 둘째 자리까지 반올림합니다.
- 숫자 입력은 최대 64자이며 0이 아닌 값은 1e-28 이상이어야 합니다. 극단적인 지수 표기로
  계산이 실패하면 입력 오류로 안내하고 이전 정상 결과는 보존합니다.

## 저장 (SQLite)

`run.py`로 실행하면 계산 결과와 운영 기록을 SQLite 파일 `instance/veni.db`에 저장합니다. 서버를 다시 켜도 남습니다.
DB 파일과 세션 서명 키(`instance/secret_key`)는 첫 실행 때 자동으로 만들어지며 `instance/`는 Git에서 제외됩니다.
스키마는 `app/common/migrations/NNN_*.sql`을 번호순으로 한 번씩 적용합니다. 설계는 [DB 설계안](docs/db-design.md)을 참고하세요.

| 마이그레이션 | 테이블 | 용도 |
|---|---|---|
| 001 | `workspaces`, `analysis_records` | 작업 공간, 모듈별 계산 이력 |
| 002 | `materials`, `material_purchases`, `menus`, `recipe_items` | 재료·구매 이력, 메뉴 레시피 |
| 003 | `menu_sales`, `monthly_financials` (+ `menus.other_cost`) | 월별 판매, 월별 매출·비용 |
| 004 | `location_candidates` | 입지 후보 |
| 005 | `campaigns` | 캠페인 기록 |
| 006 | `datasets`, `areas`, `area_sales`, `area_stores`, `area_counts`, `area_change` | 서울 상권 공개 통계 (작업 공간과 무관, 삭제 대상 아님) |
| 007 | `price_series` (+ `materials.market_item`) | KAMIS 월평균 소매가격, 재료별 시세 품목 연결 |
| 008 | `industry_benchmarks` | 소상공인실태조사 시도·업종별 기업체당 매출·비용 |
| 009 | `price_series.source` | 시세 출처 구분 (KAMIS / 참가격 / 서울시장), 출처별로 다시 불러오기 |
| 010 | `dineout_prices`, `startup_benchmarks` | 시도별 외식비, 업종별 창업비용 구간·보증금·월세 |
| 011 | `commodity_prices` | 국제 원료 선물 주간 시세 (커피 아라비카) |

- 로그인 대신 익명 **작업 공간**을 씁니다. 화면 오른쪽 위 "코드 보기"에서 작업 공간 코드를 확인하고,
  다른 브라우저에서 그 코드를 입력하면 같은 데이터를 엽니다. 코드를 아는 사람은 누구나 데이터를 열 수 있습니다.
- 같은 화면에서 작업 공간의 모든 데이터를 삭제할 수 있습니다. 365일 동안 사용하지 않은 작업 공간은 시작 시 자동 삭제됩니다.
- 모듈별 계산 이력을 모두 남기고, 화면에는 가장 최근 결과를 표시합니다. 금액은 문자열로 저장해 오차 없이 `Decimal`로 복원합니다.
- 환경변수: `VENI_DATABASE`(DB 파일 경로), `VENI_SECRET_KEY`(세션 서명 키). `.env.example`을 참고하세요.
  `.env` 파일을 자동으로 읽지는 않으므로 실행 전에 환경변수로 지정합니다.
- 테스트(`TESTING`)는 파일 없이 메모리 저장소와 메모리 SQLite를 씁니다. 이 모드에서는 재시작 시 기록이 사라집니다.

로컬 프로토타입이며 인증·권한이 없습니다. 민감한 실제 사업 자료의 보관 용도로 쓰지 마세요.

## 검증

기본 테스트 (별도 테스트 라이브러리 불필요):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

103개 테스트: 수치 정답(TOPSIS·수율·레시피·메뉴 엔지니어링·민감도·CAC/ROI·상권 지표·시세 차이 포함), 상권·시세·업종 평균 CSV 불러오기·재실행, 단위 차원/과다 사용량,
0·음수·NaN·무한대·누락값, 가격/판매량 경계, 손익분기 산출 불가, 모듈별 단독 등록·실행,
모듈 내부 상호 import 금지, 작업 공간 분리·코드 열기·삭제·보관 기간, 마이그레이션, CSRF와 HTML 이스케이프,
오류 입력 보존, 모듈 간 불러오기와 데이터 없음 처리, 극단적인 지수 입력, 잘못된 CLI 옵션,
순환 참조·계층 경계, 실제 Git 제외 규칙. Git 제외 규칙 테스트는 Git이 없으면 건너뜁니다.

GitHub Actions(`.github/workflows/tests.yml`)가 push/PR마다 Windows·Ubuntu의 Python 3.12에서 같은 테스트를 실행합니다.

모듈별 테스트를 독립적으로 실행할 수 있습니다. 각 명령은 해당 모듈만 등록한 앱으로
화면·계산·입력 오류·브라우저 데이터 분리를 검증합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.property.test_module -v
.\.venv\Scripts\python.exe -m unittest tests.material_cost.test_module -v
.\.venv\Scripts\python.exe -m unittest tests.menu_pricing.test_module -v
.\.venv\Scripts\python.exe -m unittest tests.marketing.test_module -v
.\.venv\Scripts\python.exe -m unittest tests.cost_optimization.test_module -v
```

실제 브라우저 검사 (서버를 기본 포트로 켠 상태, Chrome 설치 필요):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tests\browser_smoke.py
```

다른 포트의 서버를 검사할 때는 `--base-url http://127.0.0.1:5051`처럼 지정합니다.
1440×1100, 768×1024, 390×844, 320×740에서 홈·다섯 모듈, 계산 제출, 표 생성,
원가 가져오기, 오류 표시, 페이지 가로 넘침, JS 오류를 확인합니다. 결과·스크린샷은 `tmp/ui/`에 생성합니다.
이 스크립트는 1차 구현 화면 기준이며, 이후 추가한 저장 목록 화면은 브라우저에서 수동으로 확인했습니다.

## 저장소 관리

`.gitignore`는 가상환경·캐시·QA 이미지·로그·DB 파일(`instance/`)·IDE 설정·환경 파일·키·인증 파일을 제외합니다.
개인 사업 자료는 `local-data/`, `data/private/`, `uploads/`처럼 제외된 경로에 보관하세요.
`.env.example`만 예외로 허용하며, 실제 값 대신 설명용 자리표시자만 둡니다.
`.gitignore`는 이미 추적 중인 파일이나 과거 커밋을 삭제하지 않습니다. 민감한 파일을 잘못 커밋했다면
기록 정리와 노출된 키 교체가 별도로 필요합니다. 1차 업로드 전 점검 내용은 [release-review.md](docs/release-review.md)에 있습니다.
재사용 라이선스는 아직 지정하지 않았습니다.

## 남은 과제

| 과제 | 상태 |
|---|---|
| 서울 상권 지표 → 01 | ✅ 완료 (CSV 불러오기). 서울 밖 지역은 지원하지 않음 |
| 재료 시세 → 02 | ✅ KAMIS 농수산물 + 참가격 상품 + 서울 시장·마트 조사(축산물 포함). 원두는 aT FIS 국제 생두 시세 추세로 대신 |
| 외식비 → 03, 창업비용·보증금·월세 → 01 | ✅ 완료 (외식비 2026-10, 실태조사 2024) |
| 업종 평균 비용(소상공인실태조사) → 05 | ✅ 완료 (2023, 전국·서울). 서울 중분류의 비용 구성은 미공개라 전국 비율로 대체 |
| 상권 자동 갱신(API), 주소·지도로 상권 찾기 | 필요해지면 (현재는 분기마다 파일을 다시 받아 실행) |
| 가격 탄력성·월별 매출 예측 | 판매·월별 기록이 여러 달 쌓인 뒤 |
| 마케팅 예산 배분 최적화 | 캠페인 기록이 쌓인 뒤 |
| 실제 매물·광고 업체 견적 데이터 | 공개 데이터 없음 |
| 계정·인증·권한, 운영 배포, 다중 사용자 서버(PostgreSQL 등) | 범위 밖 |

이번 결과의 추천은 사용자가 입력한 값과 기록에 기반한 설명 가능한 계산·규칙 비교입니다. 학습 모델·LLM은 쓰지 않습니다.
