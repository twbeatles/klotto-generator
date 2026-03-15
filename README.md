# 🎰 Lotto 6/45 Generator Pro v2.5

**Lotto Generator Pro**는 파이썬과 PyQt6로 제작된 현대적이고 강력한 로또 번호 생성기입니다. 동행복권 공식 사이트의 내부 정보를 활용하여 실시간 당첨 정보를 제공하며, **1회차부터 현재까지의 전체 당첨 통계**를 분석하여 최적의 행운 번호를 제안합니다.

## ✨ 주요 기능

### 1. 강력한 번호 생성
- **고정수/제외수**: 반드시 포함하거나 제외할 숫자를 지정할 수 있습니다.
- **범위 입력 지원**: `1-10, 20, 30-35` 형식으로 편리하게 입력 가능합니다.
- **연속수 제한**: 연속된 숫자가 나오지 않도록 제한하여 확률을 높입니다.
- **대량 생성**: 한 번에 최대 20게임까지 생성 가능합니다.

### 2. 📊 역대 당첨 통계 (NEW in v2.5)
- **전체 역사 분석**: 1회차부터 현재까지 모든 당첨 번호 분석
- **자동 동기화**: 앱 실행 시 최신 당첨 정보 자동 업데이트
- **핫/콜드 넘버**: 가장 많이/적게 나온 번호 TOP 10 표시
- **번호대별 분포**: 구간별 출현 빈도 시각화

### 3. 스마트 분석 시스템
- **자동 분석**: 생성된 번호의 합계, 홀짝 비율을 실시간으로 계산
- **최적 조합 추천**: 통계적으로 당첨 확률이 높은 구간(합계 100~175) 안내
- **당첨 확인**: 생성된 번호가 역대 당첨 번호와 일치하는지 비교

### 4. 📜 생성 히스토리
- **자동 저장**: 생성한 모든 번호 조합을 자동으로 기록
- **최대 500개**: 최근 500개의 조합을 날짜와 함께 보관
- **중복 감지**: 이전에 생성한 조합과 중복되면 자동 감지

### 5. 사용자 친화적 UI/UX
- **다크 모드**: 눈이 편안한 다크 모드와 깔끔한 라이트 모드 지원
- **3D 로또 공**: 입체감 있는 현대적인 로또 공 디자인
- **즐겨찾기**: 마음에 드는 번호 조합을 별도로 저장하고 관리
- **QR 코드**: 번호 조합을 QR 코드로 생성 및 스캔

### 6. ⚡ 성능 최적화 (2026-02-27)
- **중복 검사 최적화**: 히스토리/즐겨찾기 중복 검사를 인덱스 기반으로 처리하여 생성/가져오기 응답성 개선
- **배치 저장 도입**: 다건 생성 및 JSON 가져오기 시 단일 저장 경로를 사용해 디스크 I/O 감소
- **통계 캐시/인덱스**: 회차 인덱스 + 분석 캐시로 당첨 통계 조회 속도 개선
- **초기 로딩 개선**: QR 스캐너 의존성을 지연 로딩하여 앱 시작 체감 속도 개선

## 🛠️ 설치 및 실행

### 요구 사항
- Python 3.10 이상
- 기본 패키지: `PyQt6`, `requests`, `qrcode`, `Pillow`
- QR 스캐너 선택 패키지: `numpy`, `opencv-python`, `pyzbar`
- 엑셀 내보내기 선택 패키지: `openpyxl`

### 설치
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

QR 스캐너와 엑셀 내보내기까지 사용하려면 선택 의존성을 추가로 설치하세요.

```bash
pip install -r requirements-optional.txt
```

일부 환경(예: Windows arm64 + Python 3.13)에서는 `opencv-python` 휠이 없어 QR 스캐너 의존성 설치가 실패할 수 있습니다. 이 경우 기본 앱은 그대로 사용할 수 있고, QR 기능은 호환 wheel이 있는 Python/아키텍처에서 추가 설치해 주세요.

VS Code/Pylance는 워크스페이스 기본 인터프리터를 `.venv`로 가정합니다. 처음 설정한 뒤에는 `Python: Select Interpreter`에서 `.venv`를 선택하거나 창을 다시 로드해 주세요.

### 실행
```bash
python run_klotto.py
```

### 빌드 (실행 파일 생성)
```bash
pip install pyinstaller
pyinstaller klottogenerator.spec
```
빌드된 실행 파일은 `dist/LottoGeneratorPro_v25.exe` (단일 파일)로 생성됩니다.

`klottogenerator.spec`는 빌드 환경에 설치된 선택 의존성을 감지해 QR 스캐너용 `cv2`/`pyzbar` 바이너리를 함께 포함합니다. 선택 의존성이 없는 환경에서도 앱은 빌드되지만 QR 스캐너 기능은 비활성 상태로 배포됩니다.

## 🔎 개발 품질 체크

### Pylance/Pyright
저장소 기본 타입 체크 모드는 `standard`입니다.

```bash
.venv\Scripts\activate
pyright --outputjson
```

### UTF-8/인코딩 검증
한글 문서와 소스가 UTF-8로 유지되는지 아래 스크립트로 빠르게 확인할 수 있습니다.

```bash
.venv\Scripts\activate
python scripts/check_utf8.py
```

### 자동 검증
GitHub Actions의 `Repo Health` 워크플로가 push / pull request마다 다음 항목을 검사합니다.

- UTF-8 인코딩 검증
- `pyright --outputjson`
- `python -m compileall ...`

### 컴파일 검증
```bash
python -m compileall klotto scripts run_klotto.py klottogenerator.py
```

## 📁 프로젝트 구조

```
klotto-generator/
├── klotto/                  # 메인 패키지
│   ├── config.py           # 설정 및 상수
│   ├── utils.py            # 유틸리티 및 테마 관리
│   ├── core/               # 핵심 로직
│   │   ├── analysis.py     # 번호 분석
│   │   ├── generator.py    # 번호 생성
│   │   ├── stats.py        # 당첨 통계 (SQLite DB 연동)
│   │   └── sync_service.py # 백그라운드 동기화 서비스
│   ├── data/               # 데이터 관리
│   │   ├── favorites.py    # 즐겨찾기
│   │   └── history.py      # 히스토리
│   ├── net/                # 네트워크
│   │   └── client.py       # API 클라이언트
│   └── ui/                 # UI 컴포넌트
│       ├── dialogs.py      # 다이얼로그
│       ├── main_window.py  # 메인 윈도우
│       └── widgets.py      # 위젯
├── data/                    # 로또 역대 당첨 DB (생성/동봉 시)
│   └── lotto_history.db    # SQLite DB (1회~현재)
├── scripts/                 # 유틸리티 스크립트
│   ├── common.py                 # 스크립트 공통 경로/DB resolver
│   ├── check_utf8.py             # UTF-8/대체 문자 검증
│   ├── test_stats.py             # 통계 로드 점검
│   ├── verify_db.py              # DB 상태 점검
│   ├── scrape_lotto_history.py   # DB 스크래핑
│   └── export_to_excel.py        # 엑셀 내보내기
├── run_klotto.py            # 실행 진입점
├── klottogenerator.py       # 레거시 단일 파일 버전 (호환 유지)
├── klottogenerator.spec     # PyInstaller 설정
├── requirements.txt         # 기본 실행 의존성
├── requirements-optional.txt # QR/엑셀 선택 의존성
├── pyrightconfig.json       # Pylance/Pyright 설정
├── .editorconfig            # UTF-8/에디터 규칙
├── .gitattributes           # Git 줄바꿈 정책
├── .vscode/settings.json    # 워크스페이스 분석/인코딩 설정
├── .github/workflows/repo-health.yml # CI 저장소 헬스 체크
├── .gitignore               # 빌드/캐시/로컬 산출물 제외
└── README.md
```

## ⌨️ 단축키

| 단축키 | 기능 | 설명 |
|---|---|---|
| **Enter** | 번호 생성 | 설정된 옵션으로 새 번호를 생성합니다. |

## 🎛️ 하단 메뉴

| 버튼 | 기능 |
|---|---|
| 📊 통계 | 내 생성 번호 통계 |
| 📜 히스토리 | 생성 히스토리 |
| ⭐ 즐겨찾기 | 즐겨찾기 관리 |
| 📈 당첨통계 | **역대 전체 당첨 통계** |
| 🎯 당첨확인 | 내 번호 당첨 확인 |
| 📷 QR 스캔 | 동행복권 QR 이미지/카메라 스캔 후 즉시 당첨 확인 |
| 💾 데이터관리 | 데이터 내보내기/가져오기 |

## 📁 데이터 저장 경로

```
~/.lotto_generator/
├── settings.json        # 사용자 설정(테마/옵션)
├── favorites.json       # 즐겨찾기 데이터
├── history.json         # 생성 히스토리
├── winning_stats.json   # 당첨 통계 캐시
└── lotto_history.db     # 역대 당첨 DB (자동 복사)
```

- Windows: `C:\Users\Username\.lotto_generator\`
- macOS/Linux: `~/.lotto_generator/`

## 📝 변경 이력

### v2.5 유지보수 (2026-03-15)
- ✅ 선택적 네이티브 의존성(`cv2`, `pyzbar`) import를 Pylance 친화적으로 정리
- 🧪 `.venv` 기반 워크스페이스/Pyright 설정 정합성 강화
- 🔤 UTF-8 검증 스크립트(`scripts/check_utf8.py`) 및 GitHub Actions 리포지토리 헬스 체크 추가
- 📦 `requirements.txt` / `requirements-optional.txt` 분리 및 PyInstaller spec 선택 의존성 번들링 정리

### v2.5 유지보수 (2026-03-10)
- ✅ Pylance/Pyright 전수 정리 완료 (`errorCount: 0`)
- 🔒 Optional 반환 API 가드 및 타입 힌트 정합성 강화
- 🧹 `__pycache__/*.pyc` 추적 제거 및 `.gitignore` 강화
- 🔤 UTF-8 인코딩 정책 고정 (`.editorconfig`, `.vscode/settings.json`)
- 📘 문서/빌드 설정(`README`, `spec`) 정합성 업데이트

### v2.5 유지보수 (2026-02-27)
- ✅ 기능 점검 이슈 전 항목 반영 (생성/QR/스레드/스크립트/문서 정합성)
- ⚡ 생성/히스토리/통계 경로 성능 최적화
- 🧩 스크립트 실행/DB 경로 일원화 (`python scripts/x.py`, `python -m scripts.x`)
- 🔐 스크래핑 SSL 기본 검증 복원 (`--insecure` 옵션 제공)

### v2.5 (2026-02-04)
- 🎉 **역대 전체 당첨 통계 기능 추가**
  - 1회차~현재까지 모든 당첨 번호 SQLite DB 저장
  - 앱 실행 시 최신 회차 자동 동기화
  - 핫/콜드 넘버, 번호대별 분포 분석
- 📊 **엑셀 내보내기 기능** (`scripts/export_to_excel.py`)
- 🔧 **PyInstaller Onefile 모드** - 단일 EXE 파일 생성
- 📦 역대 당첨 DB를 패키지에 포함

### v2.4 (2026-01-26)
- 🔧 동행복권 API 대응 업데이트
- 📝 프로젝트 문서 최신화

### v2.3 (2026-01-11)
- 🔧 동행복권 API 변경 대응
- 📦 코드베이스 모듈화 리팩토링

### v2.2 (2026-01-11)
- ⚡ 네트워크 엔진 교체
- 🛡️ 입력값 검증 시스템 강화

### v2.1 (2025-12-30)
- ✨ 번호 통계/히스토리 기능 추가
- 🎨 3D 로또 공 디자인

---

