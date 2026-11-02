# Veni-Vidi-Biz

Start · Predict · Succeed — 소규모 사업자를 위한 창업·운영 의사결정 웹 프로토타입.

프로젝트 계획·요구사항·설계 방향에 따른 **초기 구현**입니다. Python + Flask + Jinja + HTML/CSS를 사용합니다.
Flask는 독립 URL과 MVC 분리가 명확하며 별도 프런트엔드 빌드 없이 실행할 수 있어 선택했습니다.
정밀 계산에는 Python `Decimal`, 차트에는 CSS, 테스트에는 표준 `unittest`를 사용합니다.

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

| 모듈 / 독립 URL | 실행되는 기능 | 사용한 처리 방식 |
|---|---|---|
| 부동산 및 업장 `/property/` | 후보 2곳의 예산·면적·고객층·동선·시설 비교, 초기 자금과 부족 자금 계산 | 모듈 내부 Blackboard + 단순 비용 합계 |
| 재료비 `/material-cost/` | 구매 비용, kg↔g·L↔mL 단위 환산, 사용량 원가 | 일반 계산 Model |
| 메뉴 가격 `/menu-pricing/` | 목표 공헌이익률 기반 가격, 동일 판매량 조건의 매출·공헌이익 비교 | 일반 계산 Model |
| 마케팅 `/marketing/` | 직접 홍보와 가상 업체 대안의 비용·시간·고객층·목적 비교 | 모듈 내부 Blackboard |
| 운영 개선 `/cost-optimization/` | 비용 비중, 이전 월 대비 증감, 항목별 감축률, 절감 전후 손익, 손익분기 매출 | Blackboard + 재무 계산 |

모든 모듈은 기본 가상 예시를 제공하며, 입력을 바꿔 계산할 수 있습니다. 입력 데이터 구분을 직접 선택합니다.
기본값을 실제 시장 자료처럼 표시하지 않습니다. 결과에 출처, 계산 시점(KST), 계산 가정과 주의점을 표시합니다.
메뉴 화면에서 선택하면 재료비의 **최근 재료 1건의 1회 사용 원가**를 가져옵니다.
재료비 결과가 없을 때는 오류 안내 후 직접 입력으로 계산할 수 있습니다. 여러 재료 레시피 합산은 미구현입니다.
업장→운영비, 메뉴→운영비, 마케팅→운영비의 추가 연동은 후속 기능이며 현재 운영비는 직접 입력합니다.

각 모듈만 등록해 별도 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe run.py --module menu_pricing --port 5001
.\.venv\Scripts\python.exe run.py --module material_cost --module menu_pricing --port 5002
```

모듈 식별자: `property`, `material_cost`, `menu_pricing`, `marketing`, `cost_optimization`.

## 디렉터리와 책임

```text
app/
  common/
    model.py                 # Repository 계약을 사용하는 Model 기본 동작
    repository.py            # 저장 계약과 메모리 구현, 데이터 복사·잠금·만료
    validation.py            # 필드 계약과 숫자·선택값·필수값 검증
    decision.py              # Blackboard / KnowledgeSource / Control / Result
    web.py                   # 공통 요청 흐름·CSRF·오류/재표시
    time.py                  # UTC 저장, KST 표시
    templates/               # 공통 레이아웃·입력/결과·홈·오류 화면
    static/                  # 반응형 CSS, 제출 상태 JS
  modules/
    property/
    material_cost/
    menu_pricing/
    marketing/
    cost_optimization/
      # 각 모듈: controllers/routes.py, models/service.py,
      # repositories/memory.py, views/<모듈>/index.html
      # property/marketing/cost_optimization의 models/decision_engine/
  integrations/contracts.py  # 공개 DTO와 MaterialCostProvider 인터페이스
  main/application.py       # 조립 지점, 모듈 등록, 라우팅, 설정
tests/
  property/test_module.py
  material_cost/test_module.py
  menu_pricing/test_module.py
  marketing/test_module.py
  cost_optimization/test_module.py
  module_support.py          # 모듈별 테스트 공통 흐름 (선택한 모듈만 조립)
  test_prototype.py          # 공통 검증·HTTP·내부 의존성·연동 계약 테스트
  test_architecture.py       # 순환 참조·상대 import·MVC 데이터 접근 경계
  test_release_readiness.py  # 극단 입력·CLI·실제 Git 제외 규칙
  browser_smoke.py           # 선택적 실제 Chrome 화면 검증
docs/
  analysis-and-plan.md       # 세 문서 분석, 충돌 해결, 계산 가정, 개발 계획
  implementation-log.md      # 단계별 결과와 검증 기록
  release-review.md          # GitHub 업로드 전 10개 점검 항목과 최종 결과
run.py
requirements.txt
requirements-dev.txt
```

각 모듈의 Model이 자신의 Repository를 소유합니다. View/Controller가 Repository를 직접 조회하지 않습니다.
모듈끼리 내부 구현을 import하지 않습니다. `main/application.py`에서 의존성을 주입하며,
재료 연동은 읽기 전용 `MaterialCostSnapshot`과 `MaterialCostProvider` 계약으로 수행합니다.
공통 View는 레이아웃·필드·결과 표시를 재사용하고, 모듈별 View가 확장 지점을 갖습니다.

Blackboard는 요청마다 독립 작업 공간을 만듭니다. Knowledge Sources가 중간 결과와 대안을 기록하고,
Control Component가 규칙 적용 순서와 적용 여부를 제어하며 Result Generator가 결과를 반환합니다.
세 모듈의 규칙·작업 공간은 별개입니다. 재료 원가·가격 산식에는 적용하지 않습니다.

## 계산 기준과 한계

- 금액: 원. 운영 비용·매출·판매량: 월 단위. 마케팅 가용 시간: 주당 시간.
- 초기 자금 = 보증금 + 첫 달 임대료 + 시설·인테리어 + 장비 + 초기 재료 + 기타 비용.
  보증금은 묶이는 자금이며 영업비용과 구분합니다. 권리금 등은 기타 비용에 포함해 입력하세요.
- 구매 비용 = 구매 단가 × 수량. 사용 원가 = 총 구매 비용 / 환산 구매량 × 환산 사용량.
  구매 단가는 구매 단위 1개당 가격입니다. 밀도·폐기율·배송비 자동 보정은 없습니다.
- 메뉴 변동 원가 = 재료비 + 기타 변동비. 가격 = 변동 원가 / (1 - 목표 공헌이익률).
  계산 가격은 100원 단위로 올립니다. 공헌이익은 고정비·세금 차감 전 금액입니다.
  가격별 판매량은 입력 수량을 동일하게 유지하므로 가격 수요 변화 예측이 아닙니다.
- 월 운영 손익 = 월 매출 - 입력한 월 비용. 손익분기 매출 = 고정비 / (1 - 재료비/매출).
  재료비만 매출에 비례한다고 가정하고 나머지는 고정비로 처리합니다.
  매출 0 또는 재료비 비율 100% 이상이면 손익분기 매출은 산출 불가로 표시합니다.
- 절감액 = 항목 비용 × 사용자 지정 감축률. 절감 후 손익은 매출 유지 가정입니다.
  계약·인건비 법규·품질·위생 위험을 별도로 확인해야 합니다.
- 입지 점수: 고객층 30 + 동선 20 + 시설 10 + 예산 충족 25 + 면적 충족 15.
  사용자가 입력한 평가와 비용을 비교하는 시연 규칙이며 실제 상권 추천이 아닙니다.
- 마케팅 비용·시간은 가상 예시입니다. 실제 업체 견적·수익률·매출 증가량을 산출하지 않습니다.
- 내부 계산은 `Decimal`로 수행하고 표시에서 소수 둘째 자리까지 반올림합니다.
- 숫자 입력은 최대 64자이며 0이 아닌 값은 1e-28 이상이어야 합니다. 극단적인 지수 표기로
  계산이 실패하면 입력 오류로 안내하고 이전 정상 결과는 보존합니다.

## 임시 저장 및 DB 확장

실제 DB 서버 연결, 파일 DB, 테이블 생성, 외부 데이터 API 호출을 하지 않습니다.
각 프로세스·모듈별 메모리에 익명 브라우저 작업 공간의 최근 계산 1건을 저장합니다.
서버 재시작, 브라우저 세션 변경, 24시간 만료, 모듈당 1,000개 작업 공간 초과 시 기록이 사라질 수 있습니다.
쿠키에는 익명 식별자와 요청 검증 토큰만 저장하며 입력·결과는 서버 메모리에 있습니다.
여러 탭은 같은 브라우저 쿠키를 공유하므로 같은 모듈의 최근 결과를 공유합니다.
인증과 사용자 계정이 없는 로컬 데모이며 민감한 실제 사업 자료의 보관 용도가 아닙니다.

DB 단계에서는 모듈별 `repositories/`에 `AnalysisRepository.latest/save`를 구현하는 어댑터를 추가하고
조립 지점에서 주입합니다. Model/View 계산 및 화면을 바꿀 필요 없이 저장 계층을 교체할 수 있습니다.
그 단계에서 DBMS·스키마·마이그레이션·사용자 권한·보관 정책·트랜잭션을 결정합니다.
여러 서버 프로세스 운영과 세션 유지가 필요하면 공통 저장소 및 `VENI_SECRET_KEY` 설정도 필요합니다.

## 검증

기본 테스트 (별도 테스트 라이브러리 불필요):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

43개 테스트: 수치 정답, 단위 차원/과다 사용량, 0·음수·NaN·무한대·누락값,
가격/판매량 경계, 손익분기 산출 불가, 모듈별 단독 등록·실행,
모듈 내부 상호 import 금지, 데이터 복사·브라우저 분리, CSRF와 HTML 이스케이프,
오류 입력 보존, 선택적 원가 연동과 데이터 없음 처리, 한글 요청 토큰 거부,
각 모듈 단독 MVC 입력→계산→결과 흐름과 오류 처리, 극단적인 지수 입력,
잘못된 CLI 옵션, 순환 참조·계층 경계, 실제 Git 제외 규칙.
Git 제외 규칙 테스트 2개는 Git이 설치되어 있어야 실행되며, 없으면 건너뜁니다.

모듈별 테스트를 독립적으로 실행할 수 있습니다. 각 명령은 해당 모듈만 등록한 앱으로
화면·계산·입력 오류·브라우저 데이터 분리를 검증하며, 모듈의 계산 정답 테스트도 포함합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.property.test_module -v
.\.venv\Scripts\python.exe -m unittest tests.material_cost.test_module -v
.\.venv\Scripts\python.exe -m unittest tests.menu_pricing.test_module -v
.\.venv\Scripts\python.exe -m unittest tests.marketing.test_module -v
.\.venv\Scripts\python.exe -m unittest tests.cost_optimization.test_module -v
```

검증 결과: 업장 4개, 재료비 6개, 메뉴 6개, 마케팅 4개, 운영 개선 5개,
공통·통합 10개, 구조 3개, 업로드 준비 5개가 통과했습니다. 합계 43개입니다.
업로드 대상 소스만 복사한 별도 폴더와 런타임 의존성만 설치한 새 환경에서도 43개가 통과했습니다.

실제 브라우저 검사 (서버를 기본 포트로 켠 상태, Chrome 설치 필요):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tests\browser_smoke.py
```

다른 포트의 서버를 검사할 때는 다음처럼 지정합니다.

```powershell
.\.venv\Scripts\python.exe run.py --port 5051
# 별도 터미널에서 실행
.\.venv\Scripts\python.exe tests\browser_smoke.py --base-url http://127.0.0.1:5051
```

1440×1100, 768×1024, 390×844, 320×740에서 홈·다섯 모듈, 계산 제출, 표 생성,
원가 가져오기, 오류 표시, 페이지 가로 넘침, JS 오류를 확인합니다.
결과·스크린샷은 `tmp/ui/`에 생성합니다. 가로가 긴 표는 표 영역에서 스크롤합니다.

후속 구조 점검 및 변경 파일·오류 수정 내역은 [구현 기록](docs/implementation-log.md#후속-개발-구조-점검과-보완)을 참고하세요.

## GitHub 업로드 전 확인

[최종 점검 보고서](docs/release-review.md)에 10개 점검 항목, 수정 사항과 검증 범위를 정리했습니다.
`.github/workflows/tests.yml`은 업로드 후 push/PR에서 Windows·Ubuntu의 Python 3.12 테스트를 실행하도록
구성했습니다. GitHub 원격 CI는 아직 실행하지 않았으며, 로컬 검증은 Windows에서 수행했습니다.

`.gitignore`는 가상환경·캐시·QA 이미지·로그·DB 파일·IDE 설정·환경 파일·키·인증 파일을 제외합니다.
개인 사업 자료는 `local-data/`, `data/private/`, `uploads/`처럼 제외된 경로에 보관하세요.
`.env.example`만 예외로 허용하지만, 추가한다면 실제 값 대신 설명용 자리표시자만 사용해야 합니다.
현재 실행은 별도 환경 파일 없이 프로세스 시작 시 임시 비밀키를 생성합니다. `.env` 파일을 자동으로 읽지는 않습니다.

Git을 사용해 업로드할 때, 아직 저장소를 초기화하지 않았다면 다음 순서로 대상 파일을 미리 확인합니다.

```powershell
git init -b main
git status --short --ignored
git add --dry-run .
```

검토할 대상은 소스·테스트·문서·의존성 목록·Git 설정·CI 설정입니다.
`.venv/`, `tmp/`, `.env*`, 키·개인 자료가 추가 대상에 나타나면 커밋 전에 제외하세요.
`.gitignore`는 이미 추적 중인 파일이나 과거 커밋을 삭제하지 않습니다. 이후 민감한 파일을
잘못 커밋했다면 기록 정리와 노출된 키 교체가 별도로 필요합니다.
GitHub 웹에서 폴더를 직접 업로드할 때는 `.gitignore`가 자동 필터로 적용되지 않으므로
가상환경·로컬 파일을 직접 선택에서 제외해야 합니다.

이번 검토에서는 프로젝트 루트의 Git 초기화·커밋·원격 연결·업로드를 실행하지 않았습니다.
원본 계획서의 이름·학번·개인 경로는 공개 소스에 복사하지 않았습니다.
자료를 추가할 때 개인정보·이용권한과 프로젝트의 공개 범위를 확인하세요. 재사용 라이선스는 아직 지정하지 않았습니다.

## 후속 구현

실제 매물/상권/유동인구 데이터, 실제 광고 업체 견적·성과 데이터, 학습 모델/LLM,
판매 수요 예측, 레시피 다중 재료 합산, 추가 모듈 간 연동, 영구 저장,
계정·인증·권한, 운영 배포는 미구현입니다. 이번 결과의 추천은 설명 가능한 규칙 비교입니다.
