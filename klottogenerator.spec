# -*- mode: python ; coding: utf-8 -*-
"""
Lotto Generator Pro v2.4 - PyInstaller Spec File (Onefile Mode)
빌드 명령어: pyinstaller klottogenerator.spec
"""

import sys
from pathlib import Path

# 프로젝트 경로
project_path = Path(SPECPATH)

# =============================================================================
# 경량화 설정
# =============================================================================
# 불필요한 모듈 제외 목록 (용량 최적화)
exclude_modules = [
    # 과학/데이터 라이브러리
    'matplotlib', 'numpy', 'pandas', 'scipy', 'sklearn',
    'cv2', 'opencv',
    
    # 테스트/개발 도구
    'test', 'tests', 'unittest', 'pytest', 'doctest',
    'setuptools', 'pip', 'wheel',
    
    # 불필요한 UI 프레임워크
    'tkinter', 'wx', 'PySide6', 'PySide2',
    
    # PyQt6 불필요 모듈
    'PyQt6.QtBluetooth', 'PyQt6.QtDBus', 'PyQt6.QtDesigner',
    'PyQt6.QtHelp', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
    'PyQt6.QtNfc', 'PyQt6.QtOpenGL',
    'PyQt6.QtOpenGLWidgets', 'PyQt6.QtPositioning', 'PyQt6.QtPrintSupport',
    'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuick3D', 'PyQt6.QtQuickWidgets',
    'PyQt6.QtRemoteObjects', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort',
    'PyQt6.QtSpatialAudio', 'PyQt6.QtSql', 'PyQt6.QtSvg', 'PyQt6.QtSvgWidgets',
    'PyQt6.QtTest', 'PyQt6.QtTextToSpeech', 'PyQt6.QtWebChannel',
    'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineQuick', 'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebSockets', 'PyQt6.QtXml',
    
    # 기타
    'html', 'http.server', 'xmlrpc',
    'multiprocessing', 'concurrent', 'asyncio',
    'bz2', 'lzma',
    # 'sqlite3' - 이제 필요함 (로또 히스토리 DB)
]

# 필수 hidden imports
hidden_imports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui', 
    'PyQt6.QtWidgets',
    'qrcode',
    'PIL.ImageQt',
    'email',
    'PyQt6.QtNetwork',
]

a = Analysis(
    ['run_klotto.py'],
    pathex=[str(project_path)],
    binaries=[],
    # 로또 히스토리 DB 포함
    datas=[
        (str(project_path / 'data' / 'lotto_history.db'), 'data'),
    ] if (project_path / 'data' / 'lotto_history.db').exists() else [],
    hiddenimports=hidden_imports,

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=exclude_modules,
    noarchive=False,
    optimize=2,  # 최대 최적화 (-OO)
)

# =============================================================================
# 추가 경량화: 불필요한 바이너리/데이터 필터링
# =============================================================================
# Qt 관련 불필요 파일 제거
def filter_binaries(binaries):
    exclude_patterns = [
        'Qt6Quick', 'Qt6Qml',
        'Qt6Sql', 'Qt6Svg', 'Qt6Pdf',
        'Qt6Multimedia', 'Qt6Sensors', 'Qt6Bluetooth',
        'Qt6SerialPort', 'Qt6Test', 'Qt6DBus',
        'opengl32sw', 'd3dcompiler',
        'QtBluetooth', 'QtMultimedia',
        'QtPositioning', 'QtQml', 'QtQuick', 'QtSensors',
        'QtWebEngine', 'QtWebSockets',
        'icudt', 'icuin', 'icuuc',  # ICU 라이브러리 (대용량)
    ]
    filtered = []
    for name, path, type_ in binaries:
        if not any(pattern.lower() in name.lower() for pattern in exclude_patterns):
            filtered.append((name, path, type_))
    return filtered

a.binaries = filter_binaries(a.binaries)

# 불필요한 데이터 파일 제거
def filter_datas(datas):
    exclude_patterns = [
        'translations', 'examples', 'doc', 'docs',
        'test', 'tests', '__pycache__',
    ]
    filtered = []
    for dest, src, type_ in datas:
        if not any(pattern.lower() in dest.lower() for pattern in exclude_patterns):
            filtered.append((dest, src, type_))
    return filtered

a.datas = filter_datas(a.datas)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,
)

# =============================================================================
# ONEFILE 모드 설정
# =============================================================================
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LottoGeneratorPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # 심볼 제거로 용량 감소
    upx=True,    # UPX 압축 사용
    upx_exclude=[
        'vcruntime140.dll',
        'python*.dll',
        'Qt6Core.dll',
        'Qt6Gui.dll', 
        'Qt6Widgets.dll',
    ],
    runtime_tmpdir=None,
    console=False,  # GUI 앱이므로 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 아이콘 파일이 있으면 'icon.ico' 경로 지정
    version=None,
    uac_admin=False,
    uac_uiaccess=False,
)

# =============================================================================
# 빌드 방법
# =============================================================================
# 1. 필수 설치
#    pip install pyinstaller
#    pip install pyinstaller-hooks-contrib  # 추가 hooks
#
# 2. (선택) UPX 설치 - 추가 압축
#    https://github.com/upx/upx/releases 에서 다운로드
#    upx.exe를 PATH에 추가하거나 프로젝트 폴더에 복사
#
# 3. 빌드 실행
#    pyinstaller klottogenerator.spec
#
# 4. 결과물 위치
#    dist/LottoGeneratorPro.exe (단일 파일)
#
# =============================================================================
# 예상 파일 크기
# =============================================================================
# - UPX 미사용: 약 40-50 MB
# - UPX 사용:   약 20-30 MB
#
# =============================================================================
