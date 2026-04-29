# Implementation Review

이 문서는 `IMPLEMENTATION_REVIEW` 기준으로 확인했던 구현 리스크와, 실제 반영 상태를 빠르게 다시 확인할 수 있도록 정리한 메모입니다.

## 상태

- 기준 문서: 2026-04-18 작업 범위
- 현재 상태: 주요 항목 반영 완료
- 검증 상태: `pytest`, `pyright`, `compileall`, PyInstaller build 확인 기준으로 관리

## 반영된 항목

### 1. 동기화 / 데이터 무결성

- `estimate_latest_draw()`를 KST 기준 timezone-aware 계산으로 변경하고 토요일 22:00 전에는 새 회차를 최신으로 보지 않도록 조정
- 표준 동기화에 `신규 회차 + recent missing + historical missing batch` 복구 포함
- 설정 화면에 `전체 무결성 검사/복구` 버튼 추가
- sync summary에 `status`, `mode`, `attemptedDraws`, `fetched_records`, `failed_draws`, `settledTickets`, `recentMissingCount`, `historicalMissingCount` 포함
- sync 완료 후 저장된 `ticketBook` 전체를 다시 정산
- `success / warning / failure / cancelled` 분류와 `syncMeta` 갱신 규칙 정리
- `dataHealth.message`를 `최근 누락 N건 / 과거 누락 M건 / 예상 최신 X회` 형식으로 통일

### 2. 상태 복구 / 정규화

- 손상된 `app_state.json` / 백업 payload에서 잘못된 숫자형 필드(`quantity`, `checked.rank` 등)를 예외 없이 복구
- strategy params/filters와 generator options도 safe int/clamp 기반으로 정규화
- 잘못된 프록시 값은 빈 값으로 정규화
- 잘못된 ticket subfield는 버리되 앱 전체 로드는 계속 진행

### 3. UI 상태 보존

- `refresh_all_views()`는 표시 갱신 위주로 축소
- 생성/AI/백테스트 폼이 refresh 이후에도 사용자가 입력한 값을 유지
- generator 입력값은 `generatorOptions`에 저장
- 고정수/제외수 파싱 오류, 충돌, 고정수 과다, 조합 불가능 조건은 작업 시작 전에 `QMessageBox.warning()`으로 차단
- `generatorOptions.check_consecutive/consecutive_limit`와 전략 필터 `maxConsecutivePairs`를 동기화
- backtest 비교 전략 선택도 새로고침 시 보존

### 4. 설정 화면 노출

- `proxyUrl` 입력 및 저장 추가
- `enableInApp`, `notifyOnNewResult` 토글 추가
- `enableSystemNotification`은 스키마 호환성 유지 + UI disabled 표시
- sync log/health/sync meta 표시 강화

### 5. 네트워크 경로 통합

- 로또 API 요청을 `klotto/net/http.py` 공통 helper로 통합
- background sync와 winning info 조회가 동일한 proxy-aware helper 사용

### 6. 전략 프리셋

- `StrategyRequestEditor`에 scope별 preset 저장/불러오기/삭제 UI 추가
- 현재 request를 scope 기준으로 저장하고 즉시 editor에 반영 가능

### 7. 백업 / 엑셀

- 백업 import UI는 `merge` 정책만 노출
- 데이터 관리 페이지의 `당첨 DB 엑셀 내보내기` 버튼과 `scripts/export_to_excel.py` 흐름으로 최신 DB 상태를 엑셀 workbook으로 재생성 가능
- `lotto_history_20260204_132356.xlsx`는 최신 동기화 후 다시 생성해 반영

### 8. QR / 당첨 확인

- 당첨 확인 페이지에 `QR 스캔` 버튼을 추가
- QR 파서는 양수 회차, 1~45 범위, 6개 unique 번호를 강제
- 성공한 QR payload는 기존 `WinningCheckDialog(qr_payload=...)` 흐름으로 전달

## 관련 파일

- `klotto/core/draws.py`
- `klotto/core/sync_service.py`
- `klotto/data/app_state.py`
- `klotto/net/client.py`
- `klotto/net/http.py`
- `klotto/ui/main_window/window.py`
- `klotto/ui/widgets/strategy_editor.py`
- `klotto/ui/widgets/winning_info.py`
- `klotto/qr_utils.py`
- `klottogenerator.spec`
- `README.md`

## 검증 체크리스트

- `python -m pytest -q`
- `pyright`
- `python -m compileall klotto tests`
- `pyinstaller klottogenerator.spec`

## 메모

- Windows onefile 빌드에서 KST 회차 계산이 깨지지 않도록 `.spec`에 `tzdata` bundle 경로를 추가했습니다.
- tracked 엑셀 파일은 유지하되, 일반 export 산출물은 `.gitignore`로 계속 제외합니다.
