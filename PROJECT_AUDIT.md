# Project Audit — klotto-generator (로또·연금복권 프로 v3.0)

- 감사 일시: 2026-10-04 (UTC)
- 감사 방식: 코드 감사만 수행, 코드 수정 없음
- 테스트: `pytest -q` 39개 전부 통과 확인
- 프로브: 임시 디렉터리(`%TEMP%`) 파일로만 동작 검증, production/사용자 데이터 변경 없음

## 1. Executive Summary

프로젝트 전체 상태: 핵심 사용자 흐름(번호 생성, 당첨 확인, 동기화, 백업/복원, 엑셀 내보내기)은
구현되어 있고 단위 테스트 39개가 전부 통과한다. 전략 엔진·정규화·병합 로직에 방어 코드가
촘촘히 들어가 있어 전반적인 완성도는 양호하다.

전체 위험도: **Needs Work (수리 필요)**. 정상 경로가 아닌 **손상·경계·종료 경로**에서
데이터 무결성과 안정성을 깨는 결함이 확인되었다. 평상시에는 드러나지 않지만, 한 번 터지면
복구가 어려운 방향(데이터 폐기·고아 참조·시작 불가)이다.

가장 중요한 문제 4개:

1. `app_state.json` 손상 시 전체 상태가 조용히 폐기되고 빈 상태로 덮어써진다 (ISSUE-001, Critical).
2. 백업 가져오기를 반복하면 히스토리가 중복 누적되고 500건 상한에 밀려 오래된 기록이 소실된다 (ISSUE-002, High).
3. 캠페인 총량 상한(300장)을 UI에서 초과 설정할 수 있고, 초과 시 캠페인은 조용히 버려진 채
   티켓만 남아 고아 참조가 생기며 성공 메시지는 그대로 표시된다 (ISSUE-003, High).
4. 연금복권 정적 데이터 파일 손상 시 예외가 그대로 전파되어 앱이 시작조차 되지 않는다 (ISSUE-005, High).

데이터 손상/유실 가능성 여부: **있다.** ISSUE-001(손상 파일 덮어쓰기), ISSUE-002(백업 병합 중복·밀어내기),
ISSUE-003(고아 캠페인 참조)이 직접 해당한다.

가장 먼저 수정해야 할 영역: `klotto/data/store_utils.py` + `klotto/data/store/base.py`의
손상 파일 처리(백업·보존·사용자 통지), 캠페인 생성 경로의 상한 검증, 시작 경로의 정적 데이터 로드 가드.

## 2. Project Understanding

### 프로젝트 목적

PyQt6 기반 데스크톱 앱. 로또 6/45와 연금복권 720+의 번호 생성·전략 백테스트·당첨 확인·
데이터 동기화·백업/내보내기를 하나의 앱에서 제공한다. 참고 문서 중 실제로 존재하는 것은
`README.md`뿐이다. 지시문에 언급된 `CLAUDE.md`, `AGENTS.md`는 리포지터리에 없다.

### 주요 entrypoint

- `run_klotto.py` → `klotto/main.py::main()` → `LottoApp` 생성·표시 → `window.start_sync()`
- CLI 도구: `scripts/export_to_excel.py`, `scripts/fetch_pension720_stats.py`,
  `scripts/scrape_lotto_history.py`, `scripts/verify_db.py`

### 핵심 모듈

| 영역 | 모듈 |
|---|---|
| 앱 시작·전역 예외 | `klotto/main.py`, `klotto/config.py` |
| 메인 윈도우·동기화 오케스트레이션 | `klotto/ui/main_window/window.py`, `klotto/core/sync_service.py` |
| 로또 전략 엔진 | `klotto/core/strategy/engine.py`, `klotto/core/strategy_filters.py`, `klotto/core/lotto_rules.py` |
| 연금복권 엔진 | `klotto/core/pension720_engine.py`, `klotto/data/pension720.py` |
| 통합 상태 저장소 | `klotto/data/store/` (`base/api/backup/campaigns/favorites/history/normalization/pension720/strategy_prefs/tickets`), `klotto/data/store_utils.py`, `klotto/data/app_state.py` |
| 당첨 DB·통계 | `klotto/core/stats.py` (SQLite 우선, JSON 폴백), `klotto/core/draws.py` |
| 네트워크 | `klotto/net/http.py`, `klotto/net/client.py` (동행복권 API) |
| UI 페이지 | `klotto/ui/main_window/pages/` (생성·통계·AI·백테스트·연금복권·당첨확인·데이터·설정) |
| QR·내보내기 | `klotto/ui/scanner.py`, `klotto/qr_utils.py`, `klotto/data/exporter.py`, `scripts/export_to_excel.py` |

### 데이터 저장 방식

- 사용자 상태: `~/.lotto_generator/app_state.json` 단일 파일 (즐겨찾기·히스토리·티켓북·캠페인·
  연금복권·프리셋·설정·동기화 메타·건강 상태 전부 포함). 저장은 임시 파일 후 교체 방식.
- 당첨 이력: `~/.lotto_generator/lotto_history.db` (SQLite, `draws` 테이블),
  `winning_stats.json`은 캐시/폴백 용도.
- 연금복권 기준 데이터: 번들 `data/pension720_stats.json` (읽기 전용 스냅샷) + 공식 서버 갱신.
- 외부 의존성: 동행복권 API 2종, PyQt6, requests, qrcode, Pillow,
  선택 의존성(numpy, opencv-python, pyzbar, openpyxl).

### 핵심 실행 흐름

번호 생성:
`NumberGenerationPage.run_generation → _parse_fixed_exclude(입력 파싱·검증) → StrategyEngine.generate_multiple_sets → explain_set → 결과 테이블 → add_history_many/add_favorite/add_tickets_bulk → store.save → app_state.json`

동기화:
`LottoApp.start_sync → LottoSyncWorker(QThread, 네트워크 fetch) → finished → _on_sync_finished(메인 스레드에서 upsert_winning_data → SQLite+JSON, 티켓 정산, syncMeta 기록) → refresh_all_views`

연금복권 추천:
`Pension720Page.run_recommendation → Pension720Engine.recommend → 테이블 → add_pension720_tickets_bulk → app_state.json`

백업/복원:
`DataPage.export_backup → export_backup_payload → JSON 저장 / import_backup → import_any_json → import_backup_payload(merge) → refresh_all_views`

QR 당첨 확인:
`QRCodeScannerDialog → parse_lotto_qr_url → WinningCheckDialog(qr_payload) → get_draw_data(캐시) 또는 LottoNetworkManager.fetch_draw → 결과 렌더`

## 3. Audit Coverage & Limitations

### 실제 확인한 주요 모듈

- 시작 경로: `run_klotto.py`, `klotto/main.py`, `klotto/config.py`,
  `klotto/ui/main_window/window.py` (전체 읽기)
- 상태 저장소: `store_utils.py`, `store/base.py`, `store/backup.py`, `store/history.py`,
  `store/tickets.py`, `store/campaigns.py`, `store/favorites.py`, `store/normalization.py`,
  `data/app_state.py` (전체 읽기)
- 동기화·통계: `core/sync_service.py`, `core/stats.py`, `core/draws.py`, `net/http.py`,
  `net/client.py` (전체 읽기)
- 생성·검증: `core/lotto_rules.py`, `core/strategy_filters.py`,
  `core/strategy/engine.py::generate_multiple_sets` 주변, `core/backtest.py` (전체 읽기),
  `core/pension720_engine.py::recommend` 주변, `data/pension720.py` (전체 읽기)
- UI 흐름: `pages/number_generation.py`, `pages/pension720.py`(캠페인 저장 부분),
  `pages/data.py`, `pages/check.py`, `dialogs/winning_check.py`(QR·대조 부분),
  `ui/scanner.py`, `qr_utils.py`, `data/exporter.py`, `scripts/export_to_excel.py`,
  `scripts/common.py` (전체 읽기)

### CodeGraph로 분석한 호출 관계

`codegraph_explore` 10회로 entrypoint·저장소·생성 엔진·동기화·내보내기·QR·백테스트·스레드
생명주기를 추적했다. 대표 쿼리: 시작/동기화 흐름, AppState 저장·병합·마이그레이션,
번호 생성 검증 흐름, SQLite 동기화·upsert, TaskThread/QThread 생명주기,
입력 파싱·QR·백테스트·정산, 원자 저장·백업 병합, 스레드 경합·중복 실행.
CodeGraph가 반환한 그대로의 소스와 blast radius를 반증 판단(보호 장치 유무 확인)에 사용했고,
부족한 지점은 직접 파일을 읽어 메웠다.

### 실행한 테스트

- `.venv\Scripts\python.exe -m pytest -q` → **39 passed** (약 25초).
- 임시 디렉터리 한정 프로브(리포지터리·사용자 데이터 미변경)로 다음을 실측 확인:
  `merge_history_entries` 중복 병합 시 2건으로 늘어남, `DataExporter.export_to_csv`의
  수식 메모(`=CMD(1)`) 무보호 기록, 손상 JSON 로드 시 기본값 반환,
  손상 연금복권 파일 로드 시 `JSONDecodeError`, 캠페인 24주×20세트 정규화 거부(`None`),
  캠페인 핸들러에 총량 상한 검사 없음.

### 확인하지 못한 환경/외부 서비스

- 실제 GUI 구동·수동 조작, 동행복권 실서버 동기화, 프록시 환경.
- macOS/Linux 경로·폰트·개행, PyInstaller 번들(`dist/`, `build/` 산출물) 실행.
- 웹캠 QR 스캔 실기기, `openpyxl` 실설치 환경에서의 엑셀 내보내기 내용 검증.
- 2개 프로세스 동시 실행, 디스크 가득·정전 중 쓰기 같은 장애 주입.

### 분석상의 한계

- 동시성 이슈(ISSUE-004, 006)는 코드 흐름으로 확정적 징후까지만 확인하고 GUI 종료 중
  재현까지는 수행하지 않아 신뢰도를 `Likely`로 유지했다.
- 정적 분석(pyright)과 컴파일 검사는 이번 감사에서 실행하지 않았다(감사 범위가
  기능·런타임 안정성이므로). 단, 동작 확인이 필요한 지점은 위 프로브로 대체했다.

## 4. High-Risk Issues

### [ISSUE-001] 손상된 app_state.json이 조용히 폐기되고 빈 상태로 덮어써진다

- **위치:** `klotto/data/store_utils.py::load_json_data` (9~21행),
  `klotto/data/store/base.py::_load_state` (106~112행)
- **우선순위:** Critical
- **신뢰도:** Confirmed
- **문제:** 상태 파일의 JSON 파싱이 실패하면 `load_json_data`가 기본값을 반환하고,
  `_load_state`는 이를 "파일 없음"과 동일하게 취급해 레거시/빈 상태로 새로 만들어
  **같은 경로에 즉시 저장**한다. 손상된 원본은 백업되지 않고 영구 소실된다.
- **발생 조건:** 비정상 종료 중 쓰기, 디스크 문제, 외부 편집 실수 등으로
  `~/.lotto_generator/app_state.json`이 깨진 채 다음에 앱을 시작할 때.
- **영향:** 즐겨찾기·티켓북·캠페인·프리셋·설정 전체 소실. 티켓북은 구매 예정 번호이므로
  당첨 확인 기회 상실로 이어질 수 있다.
- **근거:** 프로브에서 손상 JSON 로드가 기본값 반환으로 폴백됨을 실측했고,
  `_load_state`는 `isinstance(raw, dict)`가 아니면 마이그레이션 상태를 `save_json_atomic`으로
  같은 경로에 쓰는 흐름이 코드상 확정적이다.
- **반증 확인:** 원자 저장(`.tmp` 후 교체)은 쓰기 중 깨짐 확률을 낮추지만,
  이미 깨진 파일을 읽는 경로를 보호하지 못한다. 레거시 파일(`favorites.json` 등)도
  현 버전에서 더는 기록되지 않으므로 마이그레이션 결과는 사실상 빈 상태다.
  손상 감지 로그는 남지만 사용자에게 어떤 통지도 없다.
- **호출/영향 범위:** `AppStateStore.__init__` ← `get_shared_store()` ← `LottoApp.__init__`.
  앱 시작 시 1회, 모든 페이지·매니저가 공유하는 단일 상태이므로 영향은 앱 전체다.
- **권장 수정 방향:** 로드 실패 시 원본을 `app_state.corrupt-<timestamp>.json`으로 보존하고
  덮어쓰지 않은 채 시작 복구(빈 상태 + 경고 다이얼로그 + 손상 파일 위치 안내) 또는
  직전 백업 복원 안내를 제공한다. `save_json_atomic` 성공 후 주기적 스냅샷도 고려한다.
- **필요한 회귀 테스트:** 손상된 `app_state.json`을 둔 임시 상태 파일로 `AppStateStore`를
  초기화했을 때 (a) 원본 파일이 보존되고 (b) 저장소가 빈 상태로 시작하며
  (c) 로그/반환값으로 손상을 알 수 있는지에 대한 단위 테스트.

### [ISSUE-002] 백업 가져오기(merge) 시 히스토리가 중복 누적되고 상한에 밀려 소실된다

- **위치:** `klotto/data/store/backup.py::import_backup_payload` (46행),
  `klotto/data/store/history.py::merge_history_entries` (39~43행)
- **우선순위:** High
- **신뢰도:** Confirmed
- **문제:** `merge_history_entries`에 중복 제거가 없어 같은 백업을 두 번 가져오면
  동일 기록이 2배가 된다. 상한(`MAX_HISTORY` 500)을 넘기면 날짜순 절삭으로
  가장 오래된 기록부터 조용히 버려진다.
- **발생 조건:** 같은 백업 파일을 2회 이상 가져올 때. 백업 복원 안내를 따라 재시도하는
  정상 사용자에게도 현실적으로 발생한다.
- **영향:** 히스토리 부풀리기와 오래된 생성 기록의 영구 소실. 즐겨찾기(키 중복 제거)와
  티켓(키로 수량 병합)은 보호되므로 히스토리만 비대칭적으로 망가진다.
- **근거:** 프로브에서 동일 항목 2건을 병합하면 결과 2건임을 실측했다.
  병합 함수는 정규화→날짜 정렬→절삭만 수행하고 중복 검사를 하지 않는다.
- **반증 확인:** `merge_state`의 정규화는 형식이 깨진 항목을 거르는 역할만 하며 중복을
  막지 못한다. `add_history_many` 경로도 같은 병합 함수를 쓰지만 이 이슈의 직접
  계기는 백업 재가져오기이며, 상위 호출자(`DataPage.import_backup`)에 별도 검사가 없다.
- **호출/영향 범위:** `DataPage.import_backup` → `import_backup_payload` →
  `merge_history_entries`. 히스토리 목록·당첨 대조 소스에 영향을 준다.
- **권장 수정 방향:** `(numbers, date)` 키 기준 중복 제거를 병합 함수에 추가하고,
  가져오기 결과에 `skippedDuplicates`를 포함해 사용자에게 알린다.
- **필요한 회귀 테스트:** 동일 백업을 2회 merge 가져오기해도 히스토리 건수가 변하지 않고,
  500건 초과 시 오래된 기록이 아닌 중복이 제거되는지에 대한 단위 테스트.

### [ISSUE-003] 캠페인 총량 상한(300장)을 UI에서 초과 설정할 수 있고, 초과 시 캠페인이 조용히 버려진다

- **위치:** `klotto/ui/main_window/pages/number_generation.py::_on_campaign_generated` (373~391행),
  `klotto/ui/main_window/pages/pension720.py::_on_campaign_ready` (744~762행),
  `klotto/data/store/normalization.py::normalize_campaign_entry` (238~241행),
  `::normalize_pension720_campaign` (321~324행)
- **우선순위:** High
- **신뢰도:** Confirmed
- **문제:** 스핀박스 상한은 주차 24 × 주당 20 = 최대 480장으로 총량 상한 300장을 넘길 수 있다.
  두 핸들러 모두 총량 검사가 없고, 정규화는 초과 캠페인을 `None`으로 버린다.
  로또 경로는 `add_campaign` 반환을 검사하지 않고, 연금복권 경로는 `add_pension720_campaign`
  반환을 검사하지 않는다. 결과적으로 티켓은 저장되고 캠페인 레코드만 없어져
  `campaignId`가 어디에도 연결되지 않는 고아 참조가 생긴다. 로또 경로는 사용자에게
  "티켓 N개와 캠페인을 저장했습니다"라고 거짓 성공까지 표시한다.
- **발생 조건:** 캠페인 주차를 길게(예: 24주 × 20세트) 설정하고 캠페인을 생성할 때.
  README 예시(4주 × 5세트)보다 크게 쓰는 일반 조작으로 도달 가능하다.
- **영향:** 캠페인 목록에 없는 티켓 무더기, 캠페인 단위 삭제·정리 불가,
  사용자의 성공 인식과 실제 저장 상태의 불일치.
- **근거:** 프로브에서 24×20 정규화가 `None`임을 실측했고, 핸들러 소스에 총량 검사
  문자열이 없음을 확인했다(`campaign-total-cap-check-in-handler: False`).
  `add_campaign`/`add_pension720_campaign`의 `None` 반환을 호출자가 무시하는 것도 코드상 확정적이다.
- **반증 확인:** 프리셋·요청 정규화 등 다른 검증은 이 총량 조건을 검사하지 않는다.
  `prune_orphan_campaigns`는 캠페인 없는 티켓이 아니라 티켓 없는 캠페인만 정리하므로
  이 고아를 수습하지 못한다(방향이 반대다).
- **호출/영향 범위:** 캠페인 생성 2경로 → 상태 저장소. 데이터 관리 탭의 캠페인 삭제·집계와
  티켓북 정리에 파급된다.
- **권장 수정 방향:** 생성 실행 전에 `weeks × sets > 300`이면 차단 경고하고,
  방어적으로 `_on_campaign_*`에서 캠페인 저장 실패 시 생성된 티켓을 롤백하거나
  최소한 실패를 명시한다.
- **필요한 회귀 테스트:** 24주×20세트 캠페인 생성 시 (a) 실행 전 차단되거나
  (b) 티켓과 캠페인이 함께 저장되거나 함께 저장되지 않는 원자성에 대한 UI·저장소 테스트.
  경계값(300장 성공, 301장 차단) 테스트 포함.

### [ISSUE-004] 앱 종료 시 백그라운드 작업 스레드가 정리되지 않아 종료 중 충돌 위험이 있다

- **위치:** `klotto/ui/main_window/window.py::closeEvent` (387~395행),
  `klotto/core/sync_service.py::LottoSyncWorker`, `klotto/ui/main_window/task_thread.py::TaskThread`
- **우선순위:** High
- **신뢰도:** Likely
- **문제:** `closeEvent`는 창 형상 저장만 하고 실행 중인 동기화 워커·생성/백테스트
  `TaskThread`·카메라 워커를 취소·대기하지 않는다. `TaskThread`는 페이지에 parent되어 있어
  실행 중 소멸되면 Qt의 "QThread: Destroyed while thread is still running" 종료 경로를 밟을 수 있고,
  동기화 완료 슬롯은 이미 사라진 `settings_page`에 접근할 수 있다.
- **발생 조건:** 전체 무결성 검사·대규모 백테스트·번호 생성 도중 창을 닫을 때.
  전체 복구는 수백 회차 fetch로 수 분이 걸릴 수 있어 현실적인 조작이다.
- **영향:** 종료 중 크래시, 상태 저장 누락, 드물게 DB·JSON 쓰기 도중 종료.
- **근거:** `closeEvent` 전문에 스레드 정리 코드가 없고, `start_sync`의 중복 실행 가드는
  시작 시점에만 동작한다. 반대로 `scanner.py`·`winning_check.py`의 다이얼로그는
  각자 `closeEvent`에서 워커를 정리하고 있어 메인 윈도우만 빠져 있음이 대조된다.
- **반증 확인:** `TaskThread` 부모가 페이지이므로 이벤트 루프 종료와 함께 정리될 것이라는
  기대는 가능하지만, Qt는 실행 중 스레드 객체 소멸을 허용하지 않으며 명시적
  `quit/wait` 없이는 안전을 보장하지 않는다. 전역 예외 훅도 이 경로를 수습하지 못한다.
- **호출/영향 범위:** `LottoApp.closeEvent` → 전 페이지의 `_task`, `_active_sync_worker`,
  카메라 워커. 동기화·생성·백테스트·스캔 전체가 영향권이다.
- **권장 수정 방향:** `closeEvent`에서 실행 중 작업을 취소하고 `wait()`로 합류시킨 뒤 종료하며,
  동기화 워커는 `cancel()` 후 완료 시그널 무시를 명시한다.
- **필요한 회귀 테스트:** 동기화 실행 중 `close()`를 호출해도 크래시 없이 종료되고,
  부분 fetch가 상태를 깨지 않으며(재시작 시 재동기화로 복구) 다음 시작이 정상인 E2E 테스트.

### [ISSUE-005] 연금복권 정적 데이터 손상 시 앱이 시작조차 되지 않는다

- **위치:** `klotto/data/pension720.py::load_pension720_static_data` (95~100행),
  `klotto/ui/main_window/pages/pension720.py::reload_static_data` (310~320행)
- **우선순위:** High
- **신뢰도:** Confirmed
- **문제:** 정적 데이터 로드에 예외 처리가 전혀 없어 `data/pension720_stats.json`이 깨지면
  `JSONDecodeError`가 `Pension720Page.__init__` → `LottoApp.__init__`으로 전파되어
  메인 윈도우 생성 자체가 실패한다.
- **발생 조건:** 번들/데이터 파일이 깨지거나 사용자가 임의로 편집했을 때 1회로 충분하다.
- **영향:** 앱 실행 불가. 연금복권 기능만의 문제가 아니라 로또 포함 전체 앱이 뜨지 않는다.
- **근거:** 프로브에서 손상 파일 로드가 `JSONDecodeError`를 그대로 던짐을 실측했고,
  호출 경로 어디에도 try/except가 없다.
- **반증 확인:** 전역 예외 훅(`exception_hook`)은 사후 다이얼로그만 띄울 뿐 시작을
  복구하지 않는다. 파일 부재(`not exists → []`) 경로는 처리되므로 손상과 부재의
  비대칭이 명확하다.
- **호출/영향 범위:** `LottoApp.__init__` → `Pension720Page.__init__` → `reload_static_data`.
- **권장 수정 방향:** 로드 실패 시 빈 통계 + `pension720DataHealth(none)` + 상태 메시지 폴백으로
  시작을 보장하고, 설정 페이지에 복구(공식 데이터 확인) 안내를 노출한다.
- **필요한 회귀 테스트:** 손상된 정적 파일을 지정해도 `Pension720Page`가 빈 상태로 생성되고
  건강 상태가 `none`으로 기록되는 단위 테스트.

### [ISSUE-006] DB를 읽을 수 없으면 전체 회차 재수집 폭주가 발생한다

- **위치:** `klotto/core/sync_service.py::_get_existing_draws` (45~56행),
  `::_get_sync_targets` (58~92행)
- **우선순위:** Medium
- **신뢰도:** Likely
- **문제:** `draws` 테이블 부재·스키마 불일치·잠금 등으로 조회가 실패하면 빈 집합을 반환하고,
  표준 동기화는 `1회차 ~ 예상 최신 회차` 전체(약 1,200회차)를 수집 대상으로 잡는다.
  회차당 네트워크 1회 + 200ms 대기로 수 분~수십 분의 동기화가 시작되고,
  대부분 실패하면 `failure/warning`만 남는다.
- **발생 조건:** 구버전·수동 편집된 DB, 외부 스크립트와 동시 접근(DB 잠금),
  번들 DB 복사(`config._get_db_path`)가 비어 있는 디렉터리에 일어난 경우.
- **영향:** 장시간 무응답성 동기화, API 부하, AI·백테스트 기능 잠금(`dataHealth` 미충족),
  사용자는 원인(DB 문제)이 아닌 네트워크 문제로 오인한다.
- **근거:** `OperationalError → return set()`과 `latest_existing = 0 → range(1, current+1)`이
  코드상 직접 연결된다. `_ensure_db_schema`는 테이블 생성만 하고 스키마 마이그레이션이 없어
  컬럼 불일치 시 `SELECT` 실패가 같은 경로를 탄다.
- **반증 확인:** `_fetch_draw`의 개별 실패 처리는 수집 중 오류를 세지만,
  수집 대상 자체가 비정상적으로 커지는 것을 막지 못한다. `HISTORICAL_SYNC_BATCH_SIZE`는
  과거 누락에만 적용되고 이 경로의 `new_targets`에는 적용되지 않는다.
- **호출/영향 범위:** `LottoSyncWorker.run` → `_on_sync_finished` → `refresh_data_health`.
  통계·AI·백테스트 게이트 전반에 파급된다.
- **권장 수정 방향:** 기존 회차 조회 실패 시 수집 전에 중단하고 "DB 점검 필요" 상태를
  기록한다. 스키마 버전 검사와 대상 상한(예: 1회 동기화 최대 N회차 + 사용자 확인)을 둔다.
- **필요한 회귀 테스트:** 테이블 없는 DB·잠긴 DB에서 워커가 전체 수집 대신 즉시
  `failure` 요약을 내고 대상 목록이 비어 있는지에 대한 테스트.

### [ISSUE-007] 로또 CSV 내보내기가 스프레드시트 수식 인젝션에 무방비하다

- **위치:** `klotto/data/exporter.py::export_to_csv` (30~60행)
- **우선순위:** Medium
- **신뢰도:** Confirmed
- **문제:** 메모·생성일 필드를 그대로 CSV에 기록한다. `=CMD(...)`, `+`, `-`, `@`로 시작하는
  메모가 엑셀에서 수식으로 해석될 수 있다. 연금복권 CSV(`build_pension720_ticket_csv`)에는
  `protect_spreadsheet_formula`가 적용되어 있어 대응이 비대칭적이다.
- **발생 조건:** 악성 메모가 담긴 백업·공유 파일을 가져온 뒤 CSV로 내보내고 엑셀로 열 때.
  로컬 단일 사용자 기준으로는 자해(self-XSS 유사) 수준이지만 공유·백업 교환이 전제된 기능이다.
- **영향:** 수식 실행(외부 명령 연결 포함)으로 이어질 수 있는 파일 기반 페이로드 전달.
- **근거:** 프로브에서 메모 `=CMD(1)`이 가공 없이 기록됨을 실측했다.
  같은 리포지터리의 연금복권 경로에 보호 함수가 존재하므로 의도된 정책과의 괴리도 명확하다.
- **반증 확인:** 즐겨찾기 메모 길이 제한(200자)은 수식 실행을 막지 못한다.
  엑셀 내보내기(`export_to_excel`)는 숫자·DB 컬럼 위주라 노출이 작지만 CSV 경로와는 별개다.
- **호출/영향 범위:** `ExportImportDialog` → `DataExporter.export_to_csv`.
- **권장 수정 방향:** 연금복권과 동일한 `protect_spreadsheet_formula`를 로또 CSV의
  모든 문자열 셀에 적용한다.
- **필요한 회귀 테스트:** `=`, `+`, `-`, `@` 시작 메모가 `'` 접두사로 이스케이프되고,
  정상 메모는 그대로 유지되는 단위 테스트.

### [ISSUE-008] QR 디코딩 오류 처리에 구멍이 있다

- **위치:** `klotto/ui/scanner.py::_decode_frame` (189~206행), `klotto/qr_utils.py::parse_lotto_qr_url` (35~48행)
- **우선순위:** Low
- **신뢰도:** Likely
- **문제:** (a) `try`가 `decode(frame)` 호출만 감싸고, 이후 `obj.data.decode('utf-8')`은
  보호 밖에 있어 비-UTF8 페이로드에서 `UnicodeDecodeError`가 슬롯 밖으로 전파된다.
  (b) 동행복권 도메인이 아닌 QR은 조용히 무시되어 스캔 실패 피드백이 없다.
  (c) 게임 문자열이 12자리 미만이거나 정규화에 실패하면 해당 게임이 조용히 건너뛰어지고,
  일부만 파싱된 채 몇 게임인지 사용자에게 알리지 않는다.
- **발생 조건:** 훼손·비표준 QR 스캔, 로또가 아닌 QR 조준, 인쇄 번짐으로 일부 게임이 깨진 경우.
- **영향:** 드물게 스캐너 크래시 또는 "스캔은 됐는데 결과가 이상"한 경험. 당첨 판정 오류는 아니다.
- **근거:** 코드상 try 범위가 명확하고, `_handle_result`의 파싱 오류 처리는 그 이후 단계만
  담당한다. 상위 호출자 중 이 슬롯의 예외를 잡는 곳은 없다.
- **반증 확인:** 전역 예외 훅이 크래시를 다이얼로그로 바꾸지만 스캔 흐름은 복구되지 않는다.
  (b)(c)는 설계상 관대함일 수 있어 심각도를 Low로 유지한다.
- **호출/영향 범위:** `CameraWorker` 프레임 콜백 → `_decode_frame` → `_handle_result` →
  `parse_lotto_qr_url` → 당첨 확인 다이얼로그.
- **권장 수정 방향:** 프레임 처리 전체를 try로 감싸고, 무시된 QR·건너뛴 게임 수를
  상태 라벨에 표시한다.
- **필요한 회귀 테스트:** 비-UTF8 바이트·비로또 URL·깨진 게임 문자열 입력에 대한
  `parse_lotto_qr_url`·`_decode_frame` 단위 테스트.

## 5. Potential Functional Gaps

- **Confirmed Gap — 연금복권 티켓에 정산 생명주기가 없다.** 로또 티켓은 동기화 완료 시
  `settle_tickets_if_possible`로 자동 정산되고 `checked{drawNo,rank,checkedAt}`가 기록되지만,
  연금복권 티켓(`normalize_pension720_ticket`)에는 `checked` 필드 자체가 없고
  데이터 갱신 시 자동 정산도 없다. 당첨 확인은 `resolve_pension720_ticket_check` 주문형
  조회로만 가능하다. 티켓 상태(대기/당첨/미당첨) 목록 관리가 로또와 비대칭이다.
- **Confirmed Gap — 백업 가져오기에 병합만 있고 덮어쓰기·사전 백업이 없다.**
  `import_backup_payload`는 `mode='overwrite'`를 지원하지만 UI(`DataPage.import_backup`)는
  항상 `merge`로 호출한다. 가져오기 전 현재 상태를 자동 백업하지도 않으므로,
  오래된 백업의 `syncMeta`·`dataHealth`·설정이 현재값을 덮어쓰는 방향의 실수를 되돌릴 수 없다
  (UI 경로에서는 `refresh_all_views`가 건강 상태를 재계산해 주므로 건강 상태 자체는 회복된다).
- **Confirmed Gap — 필터가 너무 엄격하면 요청보다 적은 세트가 조용히 반환된다.**
  `generate_multiple_sets`는 시도 상한(`max(200, quantity*80)`)을 넘기면 가진 만큼만 반환하고,
  `_on_generated`는 실제 개수를 성공 문구(`N개 세트를 생성했습니다`)로 표시한다.
  부족 사실·원인 필터를 사용자에게 알리지 않는다.
- **Likely Gap — 네트워크 재시도·백오프가 없다.** 회차당 1회 시도(`API_TIMEOUT` 10초),
  고정 200ms 대기로 전체 복구를 순차 수행한다. 일시적 장애 시 해당 회차는 실패 처리되고
  사용자가 전체 동기화를 다시 돌려야 한다. 진행률·취소 UI도 설정 페이지 로그 수준이다.
- **Likely Gap — 연금복권 저장 상한(1,000장) 초과분이 조용히 버려진다.**
  `merge_pension720_tickets`는 최신 1,000장만 유지하고 나머지를 절삭한다.
  대량 캠페인 저장 시 오래된 티켓이 통지 없이 사라질 수 있다.
- **추정 — 복수 프로세스 동시 실행에 대한 보호가 없다.** `app_state.json` 저장에 파일 잠금이 없고,
  마지막 쓰기가 이긴다. SQLite 동시 쓰기는 `database is locked` 오류로 끝나며,
  이는 ISSUE-006의 빈 집합 경로와 결합될 수 있다. 단일 데스크톱 앱 전제에서는 발생 빈도가 낮다.
- **추정 — 테마 변경이 저장소를 과도하게 기록한다.** `apply_theme`가 호출될 때마다
  `store.save()`로 전체 상태를 다시 쓰고, `ThemeManager` 리스너가 해제되지 않아
  윈도우 재생성 시 누적될 수 있다. 기능 오류는 아니고 I/O·수명 관점의 문제다.

## 6. Documentation Mismatches

- **없지 않다. 다음 불일치가 확인되었다.**
- README "한 번에 추출할 게임 수 (1 ~ 50세트)" vs 실제 `MAX_SETS = 20` 및
  스핀박스 범위(1~20). 세트 수 상한 설명이 실제와 다르다. Confirmed.
- README "안전한 데이터 관리: 단일 통합 상태 저장, 자동 복구" vs ISSUE-001의 실제 동작(손상 시
  폐기·덮어쓰기, 복구 없음). "자동 복구" 표현이 실제보다 강하다. Confirmed.
- README "스프레드시트 수식 인젝션 방지가 적용된 표준 CSV" vs 로또 내보내기(`DataExporter`)는
  미적용. 방지는 연금복권 CSV에만 있다. 부분적 불일치. Confirmed.
- `CLAUDE.md`, `AGENTS.md`가 리포지터리에 존재하지 않는다. 감사 지시문이 전제로 한
  개발 규칙 문서가 없으므로, 해당 문서 기반의 규칙 준수는 검증할 수 없었다.
- README의 전략 카탈로그표(11종)는 `strategy_catalog`의 부분 요약으로 보이며 허위 기재는 아니지만,
  실험 전략·연금복권 전략 등급과 코드의 최신 목록이 1:1 대응하는지는 이번 감사에서 전수 대조하지 않았다.

## 7. Recommended Fix Plan

### Phase 1 — Immediate (데이터 손상·시작 불가·허위 성공)

1. ISSUE-001: 손상 상태 파일 보존 + 덮어쓰기 금지 + 시작 복구 안내.
2. ISSUE-005: 정적 연금복권 데이터 로드 가드(실패 시 빈 상태 시작).
3. ISSUE-003: 캠페인 총량 상한의 실행 전 차단 + 저장 실패 시 롤백·명시.
4. ISSUE-002: 히스토리 병합 중복 제거.

### Phase 2 — Stability (예외·검증·동시성·복구)

5. ISSUE-004: `closeEvent`에서 워커 취소·합류.
6. ISSUE-006: DB 조회 실패 시 수집 중단 + 스키마 검사 + 대상 상한.
7. ISSUE-007: 로또 CSV에 연금복권과 동일한 수식 이스케이프 적용.
8. 네트워크 재시도·백오프·진행률·취소, 생성 부족분 경고, 연금복권 저장 상한 초과 통지.

### Phase 3 — Structural (구조·테스트 가능성)

9. 저장소 쓰기 경로에 파일 잠금·스냅샷·손상 보고를 일원화하고,
  `load_json_data`의 "없음 vs 손상"을 구분하는 결과 타입 도입.
10. 연금복권 티켓 정산 생명주기(`checked` + 자동 정산)를 로또와 대칭으로 설계.
11. 백업 가져오기 모드 선택(merge/overwrite) + 가져오기 전 자동 스냅샷.
12. 테마·리스너·스레드 생명주기의 책임 분리(페이지가 직접 스레드를 소유하지 않도록).

실제 코드는 수정하지 않았다. 위는 방향 제시에 그친다.

## 8. Test Recommendations

- **Unit — 손상 상태 복구:** 깨진 JSON을 임시 경로에 두고 저장소 초기화 →
  기대: 원본 보존 + 빈 상태 시작 + 손상 보고. (ISSUE-001)
- **Unit — 백업 중복:** 동일 페이로드를 2회 merge →
  기대: 히스토리·즐겨찾기·티켓 건수 불변 + `skippedDuplicates` 보고. (ISSUE-002)
- **Unit — 캠페인 경계:** 300장 성공 / 301장 차단, 24×20 정규화 거부 →
  기대: 차단 또는 원자 저장(티켓·캠페인 동시 성공/실패). (ISSUE-003)
- **Unit — 정적 데이터 손상:** 깨진 연금복권 파일 로드 →
  기대: 예외 대신 빈 목록 + `none` 건강 상태. (ISSUE-005)
- **Unit — CSV 이스케이프:** `=`,`+`,`-`,`@` 시작 메모 →
  기대: `'` 접두사, 정상 메모 불변. (ISSUE-007)
- **Unit — QR 파싱:** 비-UTF8 바이트, 비로또 URL, 12자리 미만 게임 혼합 →
  기대: 크래시 없음 + 건너뛴 게임 수 보고. (ISSUE-008)
- **Integration — 동기화 정산:** fetch된 회차 삽입 후 →
  기대: 해당 회차 티켓 `checked` 기록 + `syncMeta.lastSuccess*` 갱신 + 건강 상태 `full` 조건 충족.
- **Integration — DB 불가:** 테이블 없는 DB로 표준 동기화 →
  기대: 전체 수집 대신 즉시 실패 요약 + 대상 0건. (ISSUE-006)
- **End-to-End — 생성→저장→대조:** 고정수·제외수 충돌 입력 →
  기대: 작업 미실행 + 입력 오류 다이얼로그. 정상 생성 →
  기대: 테이블·히스토리·티켓북·당첨 대조가 일관.
- **Concurrency — 종료 중 작업:** 동기화·백테스트 실행 중 창 닫기 →
  기대: 크래시 없음 + 부분 상태로 다음 시작 정상. (ISSUE-004)
- **Concurrency — 중복 동기화:** 동기화 중 재요청 →
  기대: 단일 워커 유지(현재 가드 동작 확인).
- **Regression — 세트 수 상한:** 문서·스핀·정규화의 상한(20)을 고정하는 테스트로
  README 수정 시 깨지도록(문서-코드 동기화 강제) 한다.
- **Platform-specific — 경로·인코딩:** `~` 홈 미설정, 한글 경로, 읽기 전용 상태 파일에서의
  저장 실패가 조용한 `False`가 아니라 사용자에게 보고되는지 확인(Windows/Linux).

## 9. Final Assessment

| 항목 | 평가 | 근거 |
|---|---|---|
| Functional Correctness | Acceptable | 핵심 흐름 동작, 39개 테스트 통과. 단 캠페인·병합·부족분 같은 경계에서 조용한 실패 존재 |
| Runtime Stability | Needs Work | 시작 불가 경로(005), 종료 중 스레드(004), 재수집 폭주(006) |
| Data Integrity | Needs Work | 손상 폐기(001), 백업 중복·밀어내기(002), 고아 캠페인(003) |
| Error Resilience | Needs Work | 재시도 없음, 일부 조용한 스킵(QR·게임·세트 부족) |
| Cross-platform Robustness | Acceptable | `pathlib`·홈 디렉터리 기반으로 이식성은 양호하나 mac/Linux·번들 실검증 없음 |
| Test Confidence | Acceptable | 핵심 로직 커버리지와 39개 통과는 양호하나 손상·동시성·QR 오류 경로 공백 |

**실제로 먼저 수정할 문제 3개:**

1. **[ISSUE-001] 손상 상태 파일의 조용한 폐기 (Critical)** — 한 번의 디스크·종료 사고로
   전체 상태가 소실된다. 보존·통지부터 넣는다.
2. **[ISSUE-005] 손상 정적 데이터로 인한 시작 불가 (High)** — 수정이 가장 싸고(try/except +
   폴백) 효과가 확실하다.
3. **[ISSUE-003] 캠페인 상한 우회와 고아 참조 (High)** — 거짓 성공 메시지와 함께
   데이터 정합성을 깨므로 실행 전 차단이 시급하다.

## 10. Remediation Status (2026-10-04)

이 감사에서 지적된 항목은 모두 수정되었고, 회귀 테스트와 함께 검증되었다.

- ISSUE-001~008 전부 수정 (손상 상태 보존, 히스토리 중복 제거, 캠페인 상한 차단,
  종료 시 스레드 정리, 정적 데이터 폴백, DB 불가 시 중단, CSV 수식 이스케이프, QR 디코딩 강화).
- 추가 안정화: 동기화 1회 재시도·진행률·취소 UX, 연금복권 티켓 정산 생명주기,
  백업 가져오기 전 자동 스냅샷 + merge/overwrite 선택, JSON 저장 파일 잠금,
  SQLite 잠금 대기 30초, 테마 리스너 정리.
- 테스트 39개 → 72개, `pytest`·`pyright`·`check_utf8`·`compileall` 전부 통과.
- README의 세트 수 상한·캠페인 상한·백업 방식·동기화 취소·QR 안내 문구를 실제 동작에 맞게 수정했다.


