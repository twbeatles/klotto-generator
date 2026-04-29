# Lotto 6/45 Generator Pro v3.0

`Lotto Generator Pro`는 PyQt6 기반 데스크톱 로또 도우미입니다. 이번 `v3.0`에서는 참고 웹앱의 상위 기능을 최대한 데스크톱 흐름에 맞게 이식해, 단순 번호 생성기에서 `전략 추천 + 백테스트 + 티켓북/캠페인 + 통합 상태 저장` 앱으로 확장했습니다.

## 핵심 변화

- 좌측 내비게이션 + 중앙 페이지 스택 구조로 메인 화면을 전면 개편했습니다.
- 상태 저장을 `~/.lotto_generator/app_state.json` 하나로 통합했습니다.
- 레거시 `favorites.json`, `history.json`, `settings.json`은 첫 실행 시 자동 마이그레이션됩니다.
- 웹앱의 전략 카탈로그, 자동 전략, 필터, 시뮬레이션 로직을 Python/PyQt로 포팅했습니다.
- AI 추천과 전략 시뮬레이션은 `data_health=full`일 때만 열리도록 게이트를 추가했습니다.
- 전체 백업(JSON) 내보내기/가져오기와 레거시 JSON 호환을 함께 제공합니다.
- 티켓북/캠페인/동기화 메타/데이터 상태 진단을 앱 내부에서 관리합니다.
- 전략 프리셋, 프록시 설정, 인앱 알림, 전체 무결성 복구 버튼을 UI에 통합했습니다.
- QR 스캔 당첨 확인과 당첨번호 DB 엑셀 내보내기를 앱 UI에서 바로 실행할 수 있습니다.

## 화면 구성

### 1. 번호 생성
- 고정수/제외수, 세트 수, 대상 회차를 지정해 번호를 생성합니다.
- 전략 엔진 설명 점수와 간단한 진단 요약을 함께 보여줍니다.
- 생성 결과를 히스토리, 즐겨찾기, 티켓북으로 바로 보낼 수 있습니다.
- 캠페인 생성 기능으로 여러 주차 티켓을 한 번에 만들 수 있습니다.
- 생성 페이지의 세트 수/고정수/제외수는 통합 상태에 저장되어 새로고침 이후에도 유지됩니다.
- 전략 프리셋을 scope별(`generator`, `ai`, `backtest`)로 저장/불러오기/삭제할 수 있습니다.

### 2. 당첨 통계
- SQLite 기반 당첨 이력으로 빈도, 최근 회차, 최신 상태를 확인합니다.
- 최신 회차와 데이터 건강 상태(`full`, `partial`, `none`)를 함께 표시합니다.

### 3. AI 추천
- 웹앱 전략 카탈로그 기반 AI 추천을 실행합니다.
- `auto_recent_top`, `auto_ensemble_top3`를 포함한 자동 전략을 사용할 수 있습니다.
- 당첨 데이터가 충분하지 않으면 실행이 잠기고 이유를 안내합니다.

### 4. 전략 시뮬레이션
- 여러 전략을 같은 구간에서 비교하는 백테스트를 실행합니다.
- ROI, 적중률, 총상금, 총비용, 처리 회차 수를 표로 비교합니다.
- 이 기능도 `full` 데이터 상태에서만 활성화됩니다.

### 5. 당첨 확인
- 즐겨찾기, 히스토리, 티켓북을 기준으로 과거 회차 또는 대상 회차 결과를 비교합니다.
- `QR 스캔` 버튼으로 로또 QR을 읽고 기존 당첨 확인 다이얼로그의 `qr_payload` 흐름으로 즉시 비교합니다.

### 6. 데이터 관리
- 즐겨찾기, 히스토리, 티켓북, 캠페인 데이터를 탭별로 확인합니다.
- 전체 백업 내보내기/가져오기, 레거시 가져오기/내보내기, 선택 삭제, 현재 탭 비우기를 지원합니다.
- `당첨 DB 엑셀 내보내기`로 현재 SQLite 당첨번호 DB 전체를 `.xlsx` 파일로 저장합니다.
- 백업 가져오기는 UI에서 항상 `merge` 정책으로 동작하며, 손상된 값은 가능한 범위에서 복구 후 반영합니다.

### 7. 설정/동기화
- 현재 데이터 상태와 동기화 메타를 확인합니다.
- 표준 동기화와 전체 무결성 검사/복구를 지원합니다.
- 프록시 URL 저장, 인앱 알림 토글, 시스템 알림 상태 표시(미지원)를 제공합니다.
- 표준 동기화는 `신규 회차 + recent missing + historical missing batch`를 함께 복구합니다.
- 동기화 로그를 페이지 안에서 바로 확인할 수 있습니다.

## 전략 엔진

`klotto/core`에는 웹앱 기준의 전략 카탈로그와 시뮬레이션 로직이 들어 있습니다.

- 전략 카탈로그: `ensemble_weighted`, `consensus_portfolio`, `bayesian_smooth`, `momentum_recent`, `mean_reversion_cycle`, `hot_frequency`, `cold_frequency`, `recency_gap`, `wheel_full`, `wheel_reduced_t3` 등
- 자동 전략: `auto_recent_top`, `auto_ensemble_top3`
- 파라미터: `simulationCount`, `lookbackWindow`, `wheelPoolSize`, `wheelGuarantee`, `seed`, `payoutMode`
- 필터: 홀짝/고저/합계/AC/연속쌍/끝수 분산
- 백테스트: 다중 전략 비교와 진단 요약 제공

## 상태 저장과 데이터 정책

앱의 런타임 데이터는 기본적으로 다음 위치에 저장됩니다.

```text
~/.lotto_generator/
├── app_state.json
├── favorites.json
├── history.json
├── settings.json
├── winning_stats.json
└── lotto_history.db
```

현재 앱이 실제로 주로 쓰는 통합 상태 파일은 `app_state.json`입니다.

- `favorites`: 번호 조합 unique 유지
- `history`: 실제 생성 로그 기준 누적, 중복 허용
- `ticketBook`: `targetDrawNo + source + campaignId + numbers + strategyRequest` 기준 병합 후 `quantity` 증가
- `campaigns`: 연결된 티켓이 없는 orphan 캠페인은 자동 정리
- `syncMeta`: 마지막 성공/실패/경고, 반영 회차, 동기화 모드 저장
- `dataHealth`: `full | partial | none` 상태와 최신 회차/메시지 저장
- `generatorOptions`: 번호 생성 페이지 입력값 유지
- `alertPrefs`: 인앱 알림/새 회차 알림 설정 유지
- `proxyUrl`: 모든 로또 HTTP 요청에 공통 적용

최신 회차 추정은 KST 기준 토요일 22:00 이후에 새 회차를 공개된 것으로 봅니다.

첫 실행 시 레거시 JSON 파일이 있으면 자동으로 흡수하고, 기존 파일은 백업 용도로 그대로 남겨 둡니다.

## 설치

### 요구 사항
- Python 3.10 이상
- 기본 패키지: `PyQt6`, `requests`, `qrcode`, `Pillow`
- 선택 패키지: `numpy`, `opencv-python`, `pyzbar`, `openpyxl`

### 기본 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 선택 기능 설치

QR 스캔과 엑셀 내보내기까지 쓰려면 다음도 설치합니다.

```bash
pip install -r requirements-optional.txt
```

### `.venv`가 깨졌을 때

기존 `.venv`가 다른 Python 경로를 가리키면 재생성하는 편이 가장 빠릅니다.

```bash
rmdir /s /q .venv
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-optional.txt
```

## 실행

```bash
python run_klotto.py
```

## 엑셀 내보내기

동기화된 SQLite 이력은 앱의 `데이터 관리 > 당첨 DB 엑셀 내보내기`에서 저장할 수 있습니다. 동일한 작업은 아래 스크립트로도 실행할 수 있습니다.

```bash
python scripts/export_to_excel.py
```

- 출력 형식은 단일 시트 `로또 당첨번호` 워크북입니다.
- 기본 파일명은 `lotto_history_YYYYMMDD_HHMMSS.xlsx`입니다.
- 앱/스크립트에서 최신 회차를 먼저 동기화한 뒤 내보내면 최신 당첨 결과까지 반영됩니다.

## 테스트와 정적 검증

### pytest

```bash
python -m pytest -q
```

### Pyright

```bash
pyright --outputjson
```

### 컴파일 검증

```bash
python -m compileall klotto scripts run_klotto.py klottogenerator.py
```

### UTF-8 검증

```bash
python scripts/check_utf8.py
```

## 빌드

PyInstaller onefile 빌드는 아래처럼 실행합니다.

```bash
pip install pyinstaller pyinstaller-hooks-contrib
pyinstaller klottogenerator.spec
```

성공하면 결과물은 기본적으로 아래 경로에 생성됩니다.

```text
dist/LottoGeneratorPro_v30.exe
```

`klottogenerator.spec`는 다음 사항을 반영합니다.

- QtWebEngine 미포함
- 전략 엔진/통합 상태 저장 관련 hidden import 포함
- 동기화/프록시/최신 당첨 정보 위젯 모듈을 명시적으로 포함
- QR 스캔 관련 `cv2`, `pyzbar`는 설치된 경우에만 선택 번들
- 엑셀 내보내기용 `scripts.export_to_excel`과 선택 설치된 `openpyxl` 모듈 포함
- `tzdata`가 설치된 경우 KST 회차 계산에 필요한 timezone 데이터를 함께 번들
- 로컬 `data/lotto_history.db`가 있으면 함께 포함

## CI

GitHub Actions `Repo Health` 워크플로는 아래를 검사합니다.

- UTF-8 인코딩 검사
- Pyright
- pytest
- `compileall`

## 프로젝트 구조

```text
klotto-generator/
├── klotto/
│   ├── config.py
│   ├── main.py
│   ├── core/
│   │   ├── analysis.py
│   │   ├── backtest.py
│   │   ├── draws.py
│   │   ├── generator.py
│   │   ├── lotto_rules.py
│   │   ├── stats.py
│   │   ├── sync_service.py
│   │   ├── strategy_catalog.py
│   │   ├── strategy_engine.py
│   │   └── strategy_filters.py
│   ├── data/
│   │   ├── app_state.py
│   │   ├── exporter.py
│   │   ├── favorites.py
│   │   ├── history.py
│   │   ├── models.py
│   │   └── store_utils.py
│   ├── net/
│   │   ├── client.py
│   │   └── http.py
│   └── ui/
│       ├── dialogs/
│       ├── main_window/
│       ├── theme.py
│       └── widgets/
├── tests/
├── data/
├── scripts/
├── run_klotto.py
├── klottogenerator.py
├── klottogenerator.spec
└── README.md
```

## 호환성 메모

- `klottogenerator.py`는 예전 단일 파일 import 표면을 유지하면서 새 모듈들을 재노출합니다.
- 레거시 즐겨찾기/히스토리/설정 JSON import 흐름은 계속 유지됩니다.
- 브라우저 전용 기능(PWA, service worker, 멀티탭)은 데스크톱용 데이터 게이트/진단 UX로 대체했습니다.

## 변경 사항 요약

### v3.0 (2026-04-18)
- 웹앱 기준 전략 엔진, 자동 전략, 백테스트 기능 포팅
- `app_state.json` 중심 통합 상태 저장 계층 도입
- 티켓북, 캠페인, 전략 프리셋/선호값, 동기화 메타, 데이터 상태 추가
- 메인 창을 내비게이션 + 페이지 스택 구조로 전면 개편
- 전체 백업 import/export, 데이터 관리 탭 삭제/정리 동작 추가
- AI 추천/전략 시뮬레이션 데이터 상태 게이트 추가
- KST 기준 최신 회차 계산, 표준/전체 복구 동기화, 프록시 공통 적용 추가
- 설정 화면에 인앱 알림/프록시/복구 UI 추가, 폼 상태 보존 강화
- 손상된 상태/백업 복구 로딩, 기존 티켓 자동 정산, 최신 결과 엑셀 재생성 흐름 보강
- pytest 회귀 테스트와 CI pytest 단계 추가
- PyInstaller spec, gitignore, 문서 전면 갱신
