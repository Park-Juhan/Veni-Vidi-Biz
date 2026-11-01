# 1차 프로토타입 구현 기록

작업 기준일: 2026-11-01 (한국 시간).

| 단계 | 구현 결과 | 주요 추가·변경 파일 |
|---|---|---|
| 1. 문서 분석 | 계획서 7p, SRS, 설계서 분석. 부록 프롬프트와 사용자 지시 구분. 외부 자료·계산 가정 정리 | `docs/analysis-and-plan.md` |
| 2. 기술 선택 | Python 유지, 사용자의 Flask 선택 반영. 서버 렌더링과 CSS 차트로 빌드·의존성 최소화 | `requirements.txt`, `requirements-dev.txt` |
| 3. 디렉터리 | 5개 모듈 각각 Model/Controller/View/Repository. 조립·계약·공통 영역 분리 | `app/modules/*/`, `app/main/`, `app/integrations/`, `tests/` |
| 4. 공통 MVC/UI | 공통 요청 흐름, 입력 검증, CSRF, 메모리 계약, 반응형 탐색/입력/결과/표/차트, 오류 화면 | `app/common/*`, `app/main/application.py`, `run.py` |
| 5. 모듈 기본 화면 | 모든 모듈 독립 URL, 가상 기본값, 사용자 입력 출처 선택, 모듈별 View 확장 지점 | `app/modules/*/controllers/routes.py`, `views/*/index.html` |
| 6. 핵심 처리 | 업장 후보/초기비용, 재료 원가, 메뉴 가격/매출/공헌이익, 마케팅 비교, 절감/손익분기점 | `app/modules/*/models/service.py`, `models/decision_engine/engine.py` |
| 6. 선택적 연동 | 재료 사용 원가를 읽기 전용 DTO로 메뉴에 전달. 출처/시점 표시, 직접 입력 대체 | `app/integrations/contracts.py`, 재료 Model, 메뉴 Controller |
| 7. 검증 | 자동 테스트 18개, 실제 Chrome 3개 화면 너비에서 홈+5모듈 제출 및 예외 흐름 검증 | `tests/test_prototype.py`, `tests/browser_smoke.py` |
| 8. 사용 설명 | 실행·단독 모듈 실행·계산 기준·범위·저장 한계·DB 교체·검증 방법 | `README.md` |

## 확인한 계산 예시

- 원두 1kg당 20,000원, 2kg 구매, 18g 사용 → 총 구매 40,000원, 1회 사용 원가 360원.
- 메뉴 재료비 1,200원 + 기타 변동비 300원, 목표 65% → 4,285.714…원, 100원 단위 올림 4,300원.
- 월 비용 8,000,000원, 매출 12,000,000원 → 운영 손익 4,000,000원.
- 기본 감축 시나리오 → 월 300,000원 절감, 매출 유지 시 운영 손익 4,300,000원.
- 기본 재료비 2,500,000원 → 손익분기 월 매출 약 6,947,368.42원.

## 화면 검증

실제 Chrome에서 1440×1100, 768×1024, 390×844로 확인했다.
태블릿 홈 장식의 가로 넘침을 발견해 장식 영역의 overflow를 수정했다.
기본 화면, 모듈 계산, 결과 표/차트, 원가 연동, 서버 검증 오류를 검사하며 스크린샷을 생성한다.
스크린샷은 데스크톱 홈·메뉴 결과, 모바일 홈, 태블릿 운영 결과를 직접 시각 확인했다.
QA 파일 위치는 `tmp/ui/`, 재실행 명령은 README 참고.

## 남은 범위

DB/실데이터/인증/학습 모델/운영 배포는 구현하지 않았다. 계획서와 SRS의 장기 목표를 완료했다고 표시하지 않는다.
추가 모듈 간 연동은 재료→메뉴 외에는 미구현이다. 메뉴 수익은 공헌이익이며 실제 순이익과 다르다.

## 후속 개발: 구조 점검과 보완

점검일: 2026-11-01 (한국 시간). 확정된 Python/Flask MVC 모듈형 모놀리식을 유지했다.
앞서 구현한 5개 모듈의 화면·계산·Repository·Blackboard를 검증하고,
모듈별 테스트의 독립성과 공통 View/모듈 View의 책임 분리를 보완했다.
실제 DB 서버·파일 DB·테이블·DB 연결은 추가하지 않았다.

### 생성한 파일 (이번 작업)

- `tests/module_support.py`: 모듈별 메모리 Repository를 사용하는 Model 생성과 독립 MVC 검증 공통 흐름.
- `tests/property/__init__.py`, `tests/property/test_module.py`: 업장 단독 화면·계산·오류 및 초기 자금 정답.
- `tests/material_cost/__init__.py`, `tests/material_cost/test_module.py`: 재료비 단독 흐름·환산·단위 오류.
- `tests/menu_pricing/__init__.py`, `tests/menu_pricing/test_module.py`: 메뉴 단독 흐름·가격·경계값.
- `tests/marketing/__init__.py`, `tests/marketing/test_module.py`: 마케팅 단독 흐름·적합 대안 없음 처리.
- `tests/cost_optimization/__init__.py`, `tests/cost_optimization/test_module.py`: 운영 개선 단독 흐름·절감·손익분기점.

기존 `test_prototype.py`의 모듈별 계산 테스트를 해당 파일로 이동했다.
각 모듈은 다른 모듈을 등록하지 않고 화면·제출·결과·잘못된 입력·익명 브라우저별 데이터 분리를 검사한다.

### 수정한 파일 (이번 작업)

| 파일 | 변경 내용 |
|---|---|
| `app/common/web.py` | 비 ASCII CSRF 토큰은 400 처리. View에 Model 객체를 전달하지 않고 표시용 데이터만 전달 |
| `app/common/templates/module.html` | 메뉴 전용 분기를 제거하고 `module_inputs` View 확장 블록 제공 |
| `app/modules/menu_pricing/views/menu_pricing/index.html` | 원가 가져오기 UI를 메뉴 모듈의 View가 소유 |
| `app/modules/menu_pricing/controllers/routes.py` | 가져올 원가가 없는 오류에서도 사용자의 연동 선택 유지 |
| `tests/test_prototype.py` | 모듈별 계산 테스트 이동, 한글 토큰·연동 선택 유지 회귀 테스트 추가 |
| `tests/browser_smoke.py` | 검사 서버 URL 선택, 원가 데이터가 없는 오류와 체크박스 유지 검증 추가 |
| `README.md` | 모듈별 독립 테스트, 최신 개수·결과, 다른 포트 브라우저 검사 방법 추가 |
| `docs/implementation-log.md` | 이번 변경 파일·검증·미구현·오류와 개선 사항 기록 |

### 현재 구현된 기능과 구조

| 모듈 | 입력 및 출력 | 독립성 / Blackboard |
|---|---|---|
| 부동산 및 업장 | 지역·고객층·예산·면적·시설 평가·항목별 초기 비용 → 후보 비교·필요 자금·부족 자금 | 자체 Model/Controller/View/Repository, 조건 비교 Blackboard |
| 재료비 | 단가·구매량·단위·사용량 → 총 구매 비용·기준 단가·사용 원가 | 자체 MVC/Repository, 단순 계산이므로 Blackboard 없음 |
| 메뉴 가격 | 원가·변동비·목표 공헌이익률·판매량 → 가격·매출·공헌이익 비교 | 자체 MVC/Repository, 원가 직접 입력 가능, Blackboard 없음 |
| 마케팅 | 고객층·예산·시간·규모·목적 → 가상 채널 비용·직접/업체 비교·조건 충족 여부 | 자체 MVC/Repository, 조건 비교 Blackboard |
| 운영 개선 | 월 매출·지출·이전 월 비용·감축률 → 비중·증감·절감 전후 손익·손익분기 매출 | 자체 MVC/Repository, 비용 대안 Blackboard |

세 Blackboard는 각 모듈의 `models/decision_engine/`에 있으며 요청마다 독립 작업 공간을 생성한다.
모듈 간 직접 내부 import는 없고, 재료→메뉴 연동은 `app/integrations/contracts.py`의 공개 계약을 사용한다.
조립 지점 `app/main/application.py`에서 의존성을 주입한다. View/Controller의 Repository 직접 접근은 없다.
공통 CSS의 데스크톱·태블릿·모바일 레이아웃과 입력 검증·오류 안내를 유지했다.

### 발견한 오류와 개선

1. 잘못된 한글 CSRF 토큰을 보내면 `hmac.compare_digest`가 `TypeError`를 발생시켰다.
   먼저 회귀 테스트로 재현한 뒤 ASCII 여부 검사로 수정했다. 이제 500 대신 400 안내를 반환한다.
2. 가져올 재료 원가가 없으면 오류 화면에서 가져오기 체크박스가 해제됐다.
   실패 전 선택을 보존하도록 Controller를 수정하고, HTTP 테스트와 실제 브라우저에서 확인했다.
3. 공통 View가 메뉴 전용 UI를 알고 있었다. 해당 UI를 메뉴 View로 옮겨 모듈 책임을 명확히 했다.
4. 기존 테스트는 한 파일에 모여 있었다. 모듈별 계산 테스트를 분리하고 각 모듈의 단독 MVC 검증을 추가했다.

### 실행 방법

전체 앱:

```powershell
.\.venv\Scripts\python.exe run.py
```

http://127.0.0.1:5000 접속. 기본 포트와 별개로 최신 코드 검증용 서버는
`run.py --port 5051`로 실행했고 http://127.0.0.1:5051 에서 검증했다.

모듈 단독 실행 (각 명령을 따로 실행):

```powershell
.\.venv\Scripts\python.exe run.py --module property
.\.venv\Scripts\python.exe run.py --module material_cost
.\.venv\Scripts\python.exe run.py --module menu_pricing
.\.venv\Scripts\python.exe run.py --module marketing
.\.venv\Scripts\python.exe run.py --module cost_optimization
```

동시에 실행할 때는 `--port`를 각각 다르게 지정한다. 가상환경 설치와 전체 설명은 README 참고.

### 테스트 결과

| 구분 | 별도 실행 명령 (`.venv\Scripts\python.exe -m unittest` 뒤 인자) | 결과 |
|---|---|---|
| 업장 | `tests.property.test_module -v` | 4/4 통과 |
| 재료비 | `tests.material_cost.test_module -v` | 6/6 통과 |
| 메뉴 | `tests.menu_pricing.test_module -v` | 6/6 통과 |
| 마케팅 | `tests.marketing.test_module -v` | 4/4 통과 |
| 운영 개선 | `tests.cost_optimization.test_module -v` | 5/5 통과 |
| 전체 (공통·통합 10개 포함) | `discover -v` | 35/35 통과 |

모듈별 명령은 각각 별도 프로세스로 실제 실행했다. 단독 실행 테스트는 선택한 모듈의 URL만
등록되는지 확인하며, 메뉴 모듈은 재료비 모듈 없이 직접 입력으로 계산한다.
전체 테스트에는 모듈 간 내부 import 검사, 원가 연동 계약, 잘못된 입력과 직전 정상 결과 유지가 포함된다.

Chrome 검사:

```powershell
.\.venv\Scripts\python.exe tests\browser_smoke.py --base-url http://127.0.0.1:5051
```

1440×1100, 768×1024, 390×844에서 홈과 다섯 모듈의 입력→계산→결과를 확인했다.
원가 연동 성공·데이터 없음·오류 선택 유지도 통과했다. 페이지 가로 넘침과 JS 실행 오류는 없었다.
현재 스크린샷·기계 판독 결과는 `tmp/ui/`에 생성했으며 모바일 메뉴 결과 화면도 직접 시각 확인했다.

### 미구현 및 후속 개선

- 실제 DB 서버·영구 저장·스키마·마이그레이션: 현재 지시에 따라 미구현. Repository 계약은 분리되어 있다.
- 실제 상권/유동인구/매물, 광고 업체 견적/성과, 학습 모델/LLM과 수요 예측: 미구현.
- 여러 재료의 레시피 합산과 재료→메뉴 외 추가 모듈 연동: 미구현.
- 인증·권한·운영 배포: 미구현. 현재는 가상 예시와 입력 가정을 사용하는 로컬 데모다.
- 영업비용 구분·실제 판매 수요·규칙 가중치 검증은 실제 자료를 확보한 뒤 확장할 항목이다.

## GitHub 업로드 전 전체 검토

2026-11-01 (한국 시간), 10개 점검 항목의 결과와 이번 변경 파일을
[최종 검토 보고서](release-review.md)에 정리했다.

`.gitignore`의 환경·인증·로컬 파일 제외 범위를 보강하고 실제 Git 규칙으로 검증했다.
극단 지수 입력의 Decimal 오류를 422 입력 오류로 처리하고 기존 정상 결과를 보존한다.
CLI 옵션 검증·줄바꿈 기준·GitHub Actions 구성·순환 참조/MVC 경계 테스트를 추가했다.
현재 전체 테스트는 43개이며 기존 35개 기록은 이전 단계의 검증 결과다.
업로드 대상 소스 복사본과 런타임 의존성만 설치한 새 환경에서도 43개가 통과했다.
Chrome 반응형 검증은 1440/768/390/320px로 확대했으며 페이지 가로 넘침·JS 오류는 없었다.
실제 DB·GitHub 업로드·원격 CI 실행은 수행하지 않았다.
