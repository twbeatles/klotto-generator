# 기능 구현 점검 보고서 (2026-02-26)

## 검토 범위
- 기준 문서: `README.md`
- 요청 참조 문서: `claude.md` (저장소 내 미발견)
- 코드 범위: `klotto/` 전체, `run_klotto.py`, `scripts/`
- 스모크 체크: `python -m py_compile ...` 성공, `python -m scripts.test_stats` 성공

## 핵심 결론
현재 앱은 기본 생성/통계/히스토리/즐겨찾기 흐름은 동작하지만, README에 명시된 일부 기능이 실제 UI/로직에서 빠져 있고, 제약 실패 시 결과가 그대로 저장되는 로직 등 실사용 품질에 직접 영향을 주는 이슈가 있습니다.

## 후속 반영 현황 (2026-02-27)
- 상태: 본 문서의 주요 이슈 항목을 코드에 반영 완료.
- 검증: `python -m py_compile ...`, `python scripts/test_stats.py`, `python -m scripts.test_stats`, `python scripts/verify_db.py` 통과.

### 반영 요약
- [완료] 제약 실패 세트 미반영 + 부분 성공 안내 적용
- [완료] 고정수/제외수 범위 입력 UI/파서 구현 (`1-10, 20` 형식)
- [완료] QR 스캔 메인 메뉴 진입 + 스캔 후 즉시 당첨확인 연결
- [완료] 종료 시 백그라운드 워커/네트워크 워커 정리 루틴 추가
- [완료] `SettingsManager` KeyError 방어 및 `SETTINGS_FILE` 구성 추가
- [완료] 당첨통계 import 카운트와 실제 저장 성공 수 일치
- [완료] 스크립트 공통 DB resolver 도입 (`scripts/common.py`)
- [완료] 버전/패키징명/README/requirements 정합성 반영
- [완료] 스크래퍼 SSL 기본 검증 복원 + `--insecure` 옵션 추가

### 추가 성능 최적화 반영
- 히스토리/즐겨찾기 중복 검사를 인덱스 기반(`set`)으로 최적화
- 다건 생성/가져오기 시 배치 저장 경로(`add_many`) 적용으로 파일 I/O 축소
- 당첨 통계에 회차 인덱스 및 분석 캐시 도입으로 반복 조회 성능 개선
- QR 스캐너 지연 로딩으로 초기 앱 로딩 시간 개선

## 주요 이슈 (심각도 순)

### [높음] 제약 실패 시에도 번호 세트가 결과/히스토리에 반영됨
- 근거: `klotto/ui/main_window.py:326`, `klotto/ui/main_window.py:357`, `klotto/ui/main_window.py:360`, `klotto/ui/main_window.py:362`
- 설명: `max_retries` 내에서 유효 조합을 찾지 못해도 마지막 `nums`를 그대로 `result_sets`에 추가하고 히스토리에 저장합니다.
- 영향: 연속수 제한/중복 회피 조건을 만족하지 않는 번호가 사용자에게 정상 결과처럼 노출될 수 있습니다.
- 권장: 재시도 실패 시 해당 세트를 폐기하고 사용자에게 경고(또는 생성 개수 감소 안내) 처리.

### [높음] README 핵심 기능(고정수/제외수, 범위 입력) 미구현
- README 근거: `README.md:8`, `README.md:9`
- 코드 근거: `klotto/ui/main_window.py:323`, `klotto/ui/main_window.py:324`
- 설명: UI에서 고정수/제외수 입력을 받지 않고, 내부값이 항상 빈 집합으로 고정됩니다.
- 영향: 문서 신뢰도 하락 + 기대 기능 미제공.
- 권장: 입력 필드 + 파서(`1-10, 20` 형식) + 유효성 검증 + 충돌 처리(고정수∩제외수, 6개 초과 등) 추가.

### [높음] QR 스캔 기능이 UI 플로우에 연결되어 있지 않음
- README 근거: `README.md:33`
- 코드 근거: 스캐너 구현은 `klotto/ui/scanner.py`에 있으나, 메인/다이얼로그에서 호출 경로 없음 (`klotto/ui/main_window.py`에서 미참조)
- 영향: 사용자 관점에서 “스캔 지원” 기능 접근 불가.
- 권장: 하단 메뉴 또는 즐겨찾기/히스토리 다이얼로그에 “QR 스캔” 진입 버튼 추가.

### [중간] 종료 시 백그라운드 스레드 정리 미흡
- 근거: `klotto/main.py:47`~`klotto/main.py:50`, `klotto/ui/main_window.py:472`
- 설명: 백그라운드 동기화 워커를 시작하지만, 윈도우 종료 시 `cancel()/wait()` 정리가 없습니다.
- 영향: 종료 타이밍에 따라 스레드 잔존/경고(`QThread destroyed while thread is still running`) 가능성.
- 권장: `closeEvent`에서 `_sync_worker` 및 네트워크 워커 정리 루틴 추가.

### [중간] 설정 매니저 잠재 런타임 오류
- 근거: `klotto/core/settings.py:12`, `klotto/config.py:43`
- 설명: `SettingsManager`는 `APP_CONFIG['SETTINGS_FILE']`를 요구하지만 `APP_CONFIG`에 해당 키가 없습니다.
- 영향: 현재 미사용이지만, 추후 연결 시 즉시 `KeyError` 발생.
- 권장: `SETTINGS_FILE` 키 추가 또는 `APP_CONFIG.get(...)` 기반 방어 처리.

### [중간] 당첨통계 가져오기 건수 표시가 실제 저장 성공과 불일치 가능
- 근거: `klotto/ui/dialogs.py:1441`, `klotto/ui/dialogs.py:1443`, `klotto/core/stats.py:173`
- 설명: `add_winning_data()`는 성공/실패 반환값이 없는데, 호출 후 무조건 `imported_count += 1`.
- 영향: 사용자에게 과대 집계된 가져오기 성공 수가 표시될 수 있음.
- 권장: `add_winning_data()`가 bool 반환하도록 변경하거나 삽입 전후 상태를 비교해 카운트.

### [중간] 스크립트 실행/DB 경로 일관성 부족
- 근거:
  - `python scripts/test_stats.py` 실행 시 `ModuleNotFoundError: No module named 'klotto'`
  - `scripts/verify_db.py`는 `repo/data/lotto_history.db`만 확인
  - 앱 실제 DB 선택 로직은 `klotto/config.py:16`~`klotto/config.py:38`
- 영향: 운영/개발 점검 스크립트 사용성 저하, 오진 가능.
- 권장: 스크립트를 `python -m scripts.xxx` 기준으로 맞추거나 `sys.path`/공통 DB resolver 사용.

### [낮음] 버전/패키징 문서 불일치
- 근거:
  - `klotto/__init__.py:4` (`2.4`) vs `klotto/config.py:45` (`2.5`)
  - `README.md:56` 출력 파일명 vs `klottogenerator.spec`의 `output_name = 'LottoGeneratorPro_v25'`
- 영향: 릴리즈 식별 혼선.
- 권장: 버전/아티팩트 명 단일 소스화.

### [낮음] 의존성 정의 정합성 문제
- 근거: `requirements.txt`, `README.md:43`
- 설명: `requirements.txt`에 `pillow` 누락(README 설치 명령에는 포함), `beautifulsoup4`는 현재 코드 사용 흔적 없음.
- 영향: 환경 재현성 저하.
- 권장: 실제 import 기준으로 requirements 정리.

### [낮음] 데이터 수집 스크립트의 SSL 검증 비활성화
- 근거: `scripts/scrape_lotto_history.py:63` (`verify=False`)
- 영향: MITM 취약성 및 데이터 신뢰성 저하.
- 권장: 기본 `verify=True` 유지 + 실패 시 명시적 옵션으로만 우회.

## 우선 보완 순서 제안
1. 생성 로직 실패 처리(유효 조합 보장) 수정
2. 고정수/제외수 + 범위 입력 UI/파서 구현
3. QR 스캔 기능 UI 진입 연결
4. 종료 시 스레드 정리 루틴 추가
5. 설정/의존성/버전/문서 정합성 정리

## 참고
- `claude.md`는 저장소 내 검색 결과가 없어 본 점검에서 제외했습니다.
