# Project Audit — klotto-generator (로또·연금복권 프로 v3.0)

- 감사 일시: 2026-10-06 (UTC)
- 감사 방식: 코드 감사 + 임시 디렉터리 프로브(읽기 전용 2건, 격리 쓰기 측정 1건). 코드 수정 없음.
- 테스트: `pytest -q` 77개 전부 통과, `pyright` 0 errors, `scripts/check_utf8.py` 통과(152 files), `compileall` 통과.
- production/사용자 데이터 변경 없음 (프로브는 `%TEMP%` 격리 경로의 임시 DB/파일만 사용).
- 직전 감사(`PROJECT_AUDIT.md` 2026-10-04판, 커밋 `80e64e9`에서 remediation됨)의 재현 주장을 이번 감사에서 개별 반증 검증함.

## 1. Executive Summary

프로젝트 전체 상태: 핵심 사용자 흐름(번호 생성·당첨 확인·동기화·백업/복원·엑셀 내보내기·QR 확인)은
구현되어 있고, 방어 코드(입력 정규화·원자 저장·손상 파일 보존·DB 스키마 보장)가 촘촘하다.
2026-10-04 감사에서 지적된 Critical/High 4건(상태 폐기·묶음 상한 우회·정적 데이터 크래시)은
이번 감사에서 **수정된 것으로 확인(반증)되었다.**

전체 위험도: **Needs Work (수리 필요)**. 정상 경로가 아닌 **백업 합치기·신규 설치·종료·다중 실행
경로**에서 데이터 무결성과 안정성을 깨는 결함이 남았다. 평상시에는 드러나지 않지만 한 번 터지면
사용자 데이터가 조용히 오염·유실되는 방향이다.

가장 중요한 문제 4개:

1. 전체 백업을 합치기(merge) 모드로 반복 불러오면 구매 목록 수량이 매번 증가한다 (ISSUE-001, High, Confirmed).
2. `ALLOWED_MISSING_DRAWS = [146]` 잔재로 신규 DB는 146회를 영원히 건너뛰고도 상태를 `full`로 표시한다 (ISSUE-002, Medium, Confirmed).
3. 종료 시 백그라운드 스레드 join 타임아웃이 만료되면 스레드 실행 중 파괴로 비정상 종료할 수 있다 (ISSUE-003, Medium, Likely).
4. 다중 인스턴스 실행 시 파일 락 경합으로 저장이 조용히 실패한다 (ISSUE-004, Medium, Likely).

데이터 손상/유실 가능성 여부: **있다.** ISSUE-001(수량 오염), ISSUE-004(저장 실패 묵살)가 직접 해당한다.
다만 DB 커밋 단위·원자적 JSON 저장 덕분에 저장소 파일 자체가 깨지는 유형의 손상은 관찰되지 않았다.

가장 먼저 수정해야 할 영역: `klotto/data/store/normalization.py`의 병합 시 수량 정책,
`klotto/config.py`의 stale allowlist, 앱 시작부의 단일 인스턴스 가드.

## 2. Project Understanding

### 프로젝트 목적

PyQt6 기반 데스크톱 앱. 로또 6/45와 연금복권 720+의 번호 생성·전략 백테스트·당첨 확인·데이터
동기화·백업/내보내기를 하나의 앱에서 제공한다. 참고 문서 중 실제로 존재하는 것은 `README.md`와
`AGENTS.md`뿐이며, 지시문에 언급된 `CLAUDE.md`는 리포지터리에 없다.

### 주요 entrypoint

- `run_klotto.py` → `klotto/main.py::main()` → `LottoApp` 생성·표시 → `window.start_sync()`
- CLI/배치: `scripts/scrape_lotto_history.py`, `scripts/export_to_excel.py`,
  `scripts/fetch_pension720_stats.py`, `scripts/refresh_lotto_data.py` + `update_lotto.bat`

### 핵심 모듈

| 영역 | 모듈 |
|---|---|
| 앱 시작·전역 예외 | `klotto/main.py`, `klotto/config.py` |
| 메인 윈도우·동기화 오케스트레이션 | `klotto/ui/main_window/window.py`, `klotto/core/sync_service.py` |
| 당첨 DB·통계 | `klotto/core/stats.py` (SQLite 우선, JSON 폴백), `klotto/core/draws.py` |
| 네트워크 | `klotto/net/http.py`, `klotto/net/client.py` (동행복권 API) |
| 통합 상태 저장소 | `klotto/data/store/` (base/api/backup/campaigns/favorites/history/normalization/pension720/strategy_prefs/tickets), `klotto/data/store_utils.py`, `klotto/data/app_state.py` |
| 전략·생성·백테스트 | `klotto/core/strategy/` + `strategy_engine.py`, `generator.py`, `generation_service.py`, `backtest.py`, `pension720_engine.py` |
| UI 페이지 | `klotto/ui/main_window/pages/` (생성·통계·AI·백테스트·연금복권·당첨확인·데이터·설정) |
| QR·내보내기 | `klotto/ui/scanner.py`, `klotto/qr_utils.py`, `klotto/data/exporter.py`, `scripts/export_to_excel.py` |

### 데이터 저장 방식

- 당첨 번호: `~/.lotto_generator/lotto_history.db` (SQLite, 회차 PK) + `winning_stats.json` (캐시, 원자 저장).
- 사용자 상태(즐겨찾기·기록·구매 목록·묶음·설정): `~/.lotto_generator/app_state.json` (원자 저장 + 프로세스 간 파일 락).
- 연금복권 기준 데이터: 리포 `data/pension720_stats.json` 번들.

### 외부 의존성

동행복권 API 2종(로또 회차 조회·연금복권 목록), 선택 의존성(`opencv`·`pyzbar`·`openpyxl`, 부재 시 기능별 graceful degrade).

### 핵심 실행 흐름

`설정·최신 정보 [가져오기]` → `LottoApp.start_sync` → `LottoSyncWorker(QThread)`가
`estimate_latest_draw → split_missing_draws → fetch(200ms 간격·1회 재시도)` →
`finished` 시그널 → GUI 스레드 `_on_sync_finished`에서 `upsert_winning_data`(레코드당
SELECT+UPSERT+JSON 전체 저장) → `settle_tickets_if_possible` → `store.save()` → 전체 뷰 갱신.
`Entry Point → Handler → Core Logic → DB/File/API → Result` 구조가 전 흐름에서 일관된다.

## 3. Audit Coverage & Limitations

### 실제 확인한 주요 모듈

`main.py`, `config.py`, `sync_service.py`, `stats.py`, `draws.py`, `net/http.py`,
`net/client.py`, `store/base.py`, `store/backup.py`, `store/history.py`,
`store/tickets.py`, `store/campaigns.py`, `store/normalization.py`, `store_utils.py`,
`app_state.py`, `generation_service.py`, `lotto_rules.py`, `strategy/engine.py`(rank),
`backtest.py`(개요), `data/pension720.py`(로드/정규화), `qr_utils.py`, `data/exporter.py`(개요),
`window.py`(전체), `pages/data.py`(전체), `pages/number_generation.py`(묶음 흐름),
`pages/settings.py`(동기화 배선), `pages/pension720.py`(데이터 로드),
`dialogs/export_import.py`(전체), `ui/scanner.py`(오류 처리), `task_thread.py`,
`klottogenerator.spec`, `scripts/scrape_lotto_history.py`, `scripts/export_to_excel.py`,
`scripts/refresh_lotto_data.py`, `update_lotto.bat`.

### CodeGraph로 분석한 호출 관계

- `main` entrypoint 탐색: `klotto/main.py::main` 호출자 3곳(`main`·`klottogenerator`·`run_klotto`), 테스트 홉 내 커버 없음.
- `import_backup_payload`/`export_backup_payload`: 호출자 4곳, `tests/test_app_state.py`에서 커버.
- `ExportImportDialog`: 호출자 10곳(`data.py`·`check.py`·`backtest.py` 등), `tests/test_ui_shell.py`에서 간접 커버.

### 실행한 테스트·프로브

- `pytest -q`: **77 passed** (본 감사 세션, 최종 코드 상태).
- `pyright`: **0 errors, 0 warnings**. `check_utf8.py`: 152 files 통과. `compileall` 통과.
- 프로브 1 (반복 merge 가져오기): 격리 임시 상태로 동일 백업 2회 merge → 수량 1→2→3 확인 (ISSUE-001 확정 근거).
- 프로브 2 (벌크 upsert 비용): 격리 임시 DB에 300건 upsert 3.4초 → 1244건 환산 약 14초 이상 (ISSUE-005 근거).
- 프로브 3 (API 직접 확인): 146회 정상 응답·미추첨 회차 빈 `list` 응답 확인.

### 확인하지 못한 환경/외부 서비스

실제 GUI 실행(보조 검증만 수행, headless 전체 실행 아님), PyInstaller 번들 실행, macOS/Linux,
실물 카메라 QR 스캔, 네트워크 장애 주입, 동행복권 API 스키마 변경 시나리오.

### CodeGraph·분석상의 한계

CodeGraph는 MCP가 아닌 로컬 CLI(`codegraph explore`)로 2회 사용했으며, 호출자 탐색 위주로만
활용하고 모든 이슈 근거는 파일 직접 열람·프로브로 재확인했다. UI 이벤트 체인(시그널/슬롯)의
런타임 순서는 정적 분석으로만 파악하여 동시성 이슈는 Likely로 분류했다.

## 4. High-Risk Issues

### [ISSUE-001] 백업 합치기 반복 시 구매 목록 수량이 매번 증가한다

- **위치:** `klotto/data/store/normalization.py` `merge_ticket_entries` (379~399행),
  호출: `klotto/data/store/backup.py` `import_backup_payload` (47행),
  진입: `klotto/ui/main_window/pages/data.py` `import_backup` (259행, 기본값 merge)
- **우선순위:** High
- **신뢰도:** Confirmed
- **문제:** 동일 백업 파일을 합치기 모드로 반복 불러올 때마다 같은 티켓의 `quantity`가 1씩 증가한다.
- **발생 조건:** 내 번호 관리 → 전체 불러오기 → 기존 목록에 합치기(기본 선택)를 같은 파일에 2회 이상 실행.
- **영향:** 구매 개수·당첨 정산 집계가 부풀려지고, 되돌릴 UI 수단이 없다(가져오기 전 스냅샷은 수동 복구만 가능).
- **근거:** `merge_ticket_entries`의 `push_ticket`이 키 충돌 시 `quantity`를 합산(390행)하고,
  `normalize_ticket_entry`가 수량을 그대로 보존(220행)한다. 격리 프로브로 1→2→3 증가를 실측했다.
- **반증 확인:** `history`는 (번호, 날짜) 키로 중복 제거되고 `favorites`도 중복되지 않음을 같은
  프로브로 확인했다. `merge_pension720_tickets`는 id 기준 유지라 증가하지 않는다.
  문제는 lotto `ticketBook` 병합에만 있다.
- **호출/영향 범위:** `import_backup_payload` ← `DataPage.import_backup` ← 사용자 클릭.
  영향 모듈: 구매 목록 집계(`get_total_ticket_count`), 정산(`settle_tickets_if_possible`의 settled 카운트), 데이터 페이지 표시.
- **권장 수정 방향:** merge 시 수량은 `max(기존, 유입)` 또는 유입 무시로 변경하고, 변경된 행 수를
  결과에 포함해 다이얼로그에 보고한다. overwrite 모드는 현행 유지.
- **필요한 회귀 테스트:** 동일 백업 2회 merge 후 수량 불변 테스트 / 서로 다른 수량의 두 백업 merge 시
  정책(max/ignore) 테스트 / merge 후 `checked` 상태 보존 테스트.

### [ISSUE-002] `ALLOWED_MISSING_DRAWS = [146]` 잔재로 신규 DB가 영구히 불완전해진다

- **위치:** `klotto/config.py` (74행), 소비: `klotto/core/sync_service.py` (64~79행),
  `klotto/ui/main_window/window.py` `refresh_data_health` (178~184행)
- **우선순위:** Medium
- **신뢰도:** Confirmed (코드 경로 확정 + API 실측, 신규 설치 E2E만 미실행)
- **문제:** 과거 146회 누락의 우회책으로 하드코딩된 allowlist가 DB 복원 후에도 남아 있다.
  신규 설치(빈 DB)의 최초 동기화는 146회를 수집 대상에서 제외하고, 건강 검사는 146회 부재를
  `full`로 판정한다.
- **발생 조건:** 빈 DB에서 최초 동기화. 기존 DB(146회 보유)에는 무해하다.
- **영향:** 신규 사용자의 DB가 영구히 146회 없이 `최신 정보까지 모두 준비됨`으로 표시되고,
  빈도 통계·백테스트가 1개 회차만큼 어긋난다.
- **근거:** `split_missing_draws`의 `allowed_missing`이 양쪽 모두에서 제외된다. 146회가 현재
  API에서 정상 제공됨을 본 세션에서 2회 실측했고, 2026-04 커밋(`21470a4`)에서 우회책으로
  추가된 이력을 `git log -S`로 확인했다.
- **반증 확인:** `full_repair` 모드도 `missing["all"]` 기준이라 146회를 복구하지 못한다(동일 allowlist 적용).
  테스트는 allowlist를 `{6}`으로 따로 주입하므로 기존 테스트는 깨지지 않는다.
- **호출/영향 범위:** `LottoSyncWorker._get_sync_targets` ← `start_sync`(시작·설정 화면) /
  `refresh_data_health` ← 시작·동기화 완료. 영향: `dataHealth.availability`, 빈도 분석 캐시.
- **권장 수정 방향:** allowlist를 빈 리스트로 변경하고, 최초 동기화 후 `missing['all']`이 비었음을
  단언하는 테스트를 추가한다.
- **필요한 회귀 테스트:** 빈 DB + allowlist 미적용 상태에서 1..N 동기화 계획에 146 상당의
  중간 회차가 포함되는지 단언하는 단위 테스트.

### [ISSUE-003] 종료 시 join 타임아웃 만료 후 스레드 파괴로 비정상 종료할 수 있다

- **위치:** `klotto/ui/main_window/window.py` `_cancel_background_work` (409~430행),
  `closeEvent` (432~442행)
- **우선순위:** Medium
- **신뢰도:** Likely (정적 근거 강함, GUI 종료 재현 미실시)
- **문제:** `worker.wait(10000)`·`task.wait(5000)`의 반환값을 무시하고 그대로 종료를 진행한다.
  타임아웃 만료 시 부모 없는 `QThread`가 실행 중 파괴되어 Qt가 프로세스를 abort한다.
- **발생 조건:** 동기화 fetch가 타임아웃 상한(API 10초×최대 2 시도+0.5초 대기 ≈ 20초/회차)에 걸린
  상태에서 창을 닫거나, 대량 묶음 생성(CPU 바운드, 최대 300장×360 시도) 중 창을 닫을 때.
- **영향:** 종료 중 크래시. DB는 레코드 단위 커밋·원자 저장이라 저장소 파손 위험은 낮고,
  메모리상의 미반영분(가져왔으나 upsert 전 레코드)은 다음 실행에서 재수집된다.
- **근거:** `wait()` 반환 미확인, 워커가 부모 없이 생성(`LottoSyncWorker(...)` in `start_sync`),
  `TaskThread`는 부모가 있으나 `wait(5000)` 만료 후에도 `finished`→`_finish_task`가 뒤늦게
  버튼 상태를 뒤집을 수 있다. 직전 감사의 ISSUE-004(cancel+join 부재)는 수정됐으나 타임아웃
  만료 경로가 남았다.
- **반증 확인:** 정상 조건(네트워크 안정·소량 작업)에서는 타임아웃 안에 끝나므로 평상시에는
  발생하지 않는다. `cancel()` 플래그는 루프 반복마다 확인되므로 fetch 1회만 끝나면 종료된다.
- **호출/영향 범위:** `closeEvent` ← 윈도우 종료. 영향: 종료 안정성. 데이터 경로와는 분리.
- **권장 수정 방향:** `wait()` 실패 시 `terminate()` 후 재대기 대신, 진행 중 저장을 건너뛰고
  사용자에게 종료 지연을 알리는 모달(최대 N초) + 실패 시 강제 종료 순으로 처리한다.
  워커에 부모를 지정하거나 `deleteLater`를 `finished`에 연결한다.
- **필요한 회귀 테스트:** (offscreen) 동기화 실행 중 `closeEvent` 호출 시 크래시 없이 종료되는
  테스트 / `wait()` 만료 시나리오에서 워커가 유실되지 않음을 단언하는 테스트.

### [ISSUE-004] 다중 인스턴스 실행 시 저장이 조용히 실패한다

- **위치:** `klotto/data/store_utils.py` `acquire_file_lock` (42~58행),
  `save_json_atomic` (83~114행), 진입: `klotto/main.py::main` (단일 인스턴스 가드 없음)
- **우선순위:** Medium
- **신뢰도:** Likely (코드상 확정적이나 다중 실행 재현 미실시)
- **문제:** 앱 중복 실행을 막는 장치가 없고(`QSharedMemory`·`QLockFile`·가드 전무),
  두 인스턴스가 저장 경합 시 패자는 최대 10초 대기 후 `False`를 반환한다.
  모든 호출자가 반환값을 무시하므로 사용자는 성공 메시지를 보지만 저장은 유실된다.
- **발생 조건:** 앱을 2회 실행한 상태에서 번호 저장·설정 변경·동기화 완료 저장 등이 겹칠 때.
  크래시 후 30초 이내 재시작(오래된 락 잔재) 시에도 동일하게 실패할 수 있다.
- **영향:** 구매 목록·즐겨찾기·설정 변경의 조용한 유실. SQLite 측도 30초 busy 타임아웃 후
  `upsert`가 `invalid`로 기록되어 동기화 통계를 오염시킨다.
- **근거:** `save()` 반환을 무시하는 호출(`window.apply_theme`, 각 store 메서드,
  `data.py` 삭제/비우기 등), 락 타임아웃 10초 < stale 판정 30초 구조.
- **반증 확인:** 단일 인스턴스 정상 사용에서는 발생하지 않으며, 원자 저장(`os.replace`)과
  SQLite 자체는 파일 파손까지는 막는다. 문제는 가시성 없는 실패다.
- **호출/영향 범위:** `save_json_atomic` ← 전 store + `WinningStatsManager._save`.
  영향: 전역 상태·캐시 JSON.
- **권장 수정 방향:** 시작 시 `QLockFile` 기반 단일 인스턴스 가드(2번째 실행은 기존 창 활성화 후 종료),
  저장 실패 시 상태바/다이얼로그로 즉시 통지, 락 stale 판정을 크래시 감지와 분리.
- **필요한 회귀 테스트:** 락 선점 상태에서 `save()`가 `False`를 반환하고 호출자가 이를
  사용자에게 노출하는 경로 테스트 / 2번째 인스턴스 시작이 거부되는 테스트.

### [ISSUE-005] 최초·전체 동기화 완료 핸들러가 GUI 스레드를 수십 초 멈춘다

- **위치:** `klotto/ui/main_window/window.py` `_on_sync_finished` (268~346행),
  `klotto/core/stats.py` `upsert_winning_data` (399~446행)
- **우선순위:** Medium
- **신뢰도:** Likely (비용 실측 + 코드 경로 확정, 실 GUI 프리즈 미관측)
- **문제:** fetch는 워커 스레드지만 완료 후 1244건 upsert가 GUI 스레드에서 순차 실행된다.
  건당 DB SELECT 1회 + UPSERT + JSON 전체 파일 재기록(락 포함)이 발생한다.
- **발생 조건:** 빈 DB 최초 실행 또는 빠진 회차 모두 채우기. 이후 증분 동기화(1~2건)에서는 무시 가능.
- **영향:** 완료 직전 수십 초간 UI 무응답(측정: 격리 300건 3.4초 → 1244건 환산 약 14초 이상,
  파일 증가에 따라 초선형 증가). 이 구간에는 중단 버튼도 동작하지 않아 강제 종료를 유발할 수 있다.
- **근거:** 프로브 실측 + `_save()`→`save_json_atomic` 호출 위치(upsert 440~444행).
  진행률 표시는 fetch 단계에서 멈춰 있어 사용자는 완료 지점을 알 수 없다.
- **반증 확인:** 데이터 정합성 자체는 보장된다(레코드 단위 커밋, 실패 시 캐시 미반영 후 `invalid` 반환).
  빈도 분석 캐시는 무효화 후 재계산이라 오염되지 않는다.
- **호출/영향 범위:** `_on_sync_finished` ← `LottoSyncWorker.finished`. 영향: 시작·전체복구 UX.
- **권장 수정 방향:** 완료 핸들러를 청크 단위로 나누어 `QTimer.singleShot`으로 분할 적용하거나,
  JSON 캐시 저장을 루프 밖 1회로 이동하고, 완료 단계 전용 진행 표시를 추가한다.
- **필요한 회귀 테스트:** 1200건 bulk 완료 핸들러의 GUI 블로킹 상한(예: 2초 이내 per 청크) 테스트 /
  분할 적용 후에도 `inserted/updated` 집계가 동일한지 단언하는 테스트.

## 5. Potential Functional Gaps

- **(Confirmed Gap)** 백업 merge가 `strategyPrefs`·`syncMeta`를 백업 시점으로 되돌린다.
  `backup.py` 57~65행이 현행 설정을 무조건 덮어쓴다. `dataHealth`는 가져오기 직후
  `refresh_all_views`에서 재계산되어 자가치유되지만, 전략 선택·`syncMeta.lastSuccessAt`은
  고지 없이 롤백된다. 가져오기 결과 요약을 표시하지 않아 사용자는 변경을 알 수 없다.
- **(Confirmed Gap)** 가져오기 전 스냅샷(`app_state.preimport-*.json`, `data.py` 257행)은
  쓰기만 하고 UI 복원 경로가 없다. ISSUE-001 오염 시 수동 파일 교체만 가능하다.
- **(Likely Gap)** `app_state.json`이 유효한 JSON이지만 dict가 아닐 때(예: 리스트) 백업 없이
  교체된다. `base.py` 110~121행: `load_json_data`가 리스트를 반환하면 corrupt 검사를 통과해
  `_migrate_legacy_state`가 덮어쓴다. 원본 바이트는 유실된다.
- **(추정)** JSON 가져오기(`import_any_json`)에 크기 상한이 없어 비정상 대용량 파일 선택 시
  메모리 급증이 가능하다. 사용자 선택 파일 경로라 악의적 도달 가능성은 낮다.

## 6. Documentation Mismatches

- `CLAUDE.md`가 지시문에 언급되지만 리포지터리에 없다 (직전 감사에서도 동일 지적). 없음이 아니라
  부재 자체가 mismatch이므로 명시한다.
- README의 빠른 시작·CLI 도구(엑셀 내보내기·연금복권 스냅샷)·선택 패키지(`opencv`·`pyzbar`·`openpyxl`)
  설명은 실제 구현과 일치한다. `scripts/refresh_lotto_data.py`·`update_lotto.bat`(본 세션 추가분)는
  README에 미기재이나 감사 기준시점 신규 파일이라 mismatch로 분류하지 않는다.
- README의 "20여 종" 전략 수량은 정적 카운트로 검증하지 않았다 (기능 영향 없음).

## 7. Recommended Fix Plan

### Phase 1 — Immediate

- ISSUE-001: merge 병합 시 수량 정책을 `max`/무시로 변경 + 가져오기 결과 보고.
  ISSUE-002: `ALLOWED_MISSING_DRAWS` 비우기 + 중간 회차 포함 단언 테스트.

### Phase 2 — Stability

- ISSUE-004: 단일 인스턴스 가드 + 저장 실패 사용자 통지.
- ISSUE-003: 종료 join 타임아웃 처리(반환 확인·지연 고지·안전한 파기 순서).
- ISSUE-005: 완료 핸들러 청크 분할 + JSON 캐시 저장 1회화 + 완료 단계 진행 표시.
- 백업 merge의 prefs 덮어쓰기 범위 축소(설정계는 유지 옵션) + preimport 스냅샷 UI 복원.

### Phase 3 — Structural

- 상태 저장 호출자의 `save()` 반환 처리 규약 통일(실패 전파 또는 중앙 토스트).
- 동기화 완료 경로를 워커 스레드까지 확장하고 GUI에는 적용 결과만 전달하는 구조.
- 비-dict `app_state`에 대한 corrupt 처리 일원화.

실제 코드는 수정하지 않았다.

## 8. Test Recommendations

- **Unit:** 동일 백업 2회 merge 후 수량 불변 / 서로 다른 수량 merge 정책 / `merge 후 checked 보존`.
  빈 DB 동기화 계획에 중간 회차 포함 여부 / `find_gap_draws` 경계(0건·연속·끝 회차).
- **Integration:** 가져오기→스냅샷 생성→수동 복원 왕복 / 손상 `app_state` 시작 시 백업+고지 /
  비-dict 상태 파일 시작 시 원본 보존 / 락 선점 중 저장 실패 전파.
- **End-to-End:** (offscreen) 최초 실행 전체 동기화 후 `missing['all']` 비어 있음 /
  가져오기 후 당첨 확인·백테스트가 오염 없이 동작.
- **Concurrency:** 동기화 실행 중 종료·실행 중 재시작(중복 워커 거부)·저장 경합 2-프로세스.
- **Regression:** 146회 포함 연속성(`count == max`), QR 스킵 게임 보고, CSV 수식 이스케이프(기존).
- **Platform-specific:** 번들 실행에서 `scripts.export_to_excel` import·한글 경로 저장 /
  Windows 락 파일 stale(절전·크래시) 복구.

## 9. Final Assessment

| 항목 | 평가 | 근거 |
|---|---|---|
| Functional Correctness | Acceptable | 핵심 흐름 정상, 방어적 정규화·검증이 촘촘. 단 merge 수량 정책 오류 1건(High). |
| Runtime Stability | Needs Work | 종료 join·다중 실행·최초 동기화 프리즈가 현실 경로에 남아 있음. |
| Data Integrity | Needs Work | 파일 파손은 막히나, 조용한 오염(수량)·유실(저장 실패)이 가능. |
| Error Resilience | Acceptable | 네트워크 재시도·폴백·손상 파일 보존이 갖춰짐. 통지 없는 실패가 일부 잔존. |
| Cross-platform Robustness | Acceptable | UTF-8·원자 저장·경로 처리 양호. 번들·macOS/Linux 실측은 미실시. |
| Test Confidence | Good | 77 passed + pyright/UTF-8/compileall 전부 녹색. 동시성·종료 경로는 미커버. |

**실제로 먼저 수정할 문제 3개:**

1. ISSUE-001 백업 합치기 수량 증가 (High, Confirmed) — 사용자 데이터 오염이 자동 누적된다.
2. ISSUE-002 stale allowlist `[146]` 제거 (Medium, Confirmed) — 1줄 수정으로 신규 설치 완전성 회복.
3. ISSUE-004 단일 인스턴스 가드 + 저장 실패 통지 (Medium, Likely) — 조용한 유실을 가시적 실패로 전환.
