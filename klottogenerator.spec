# -*- mode: python ; coding: utf-8 -*-
"""
Lotto Generator Pro v2.1 - PyInstaller Spec File
빌드 명령어: pyinstaller klottogenerator.spec
"""

import sys
from pathlib import Path

# 프로젝트 경로
project_path = Path(SPECPATH)

a = Analysis(
    ['klottogenerator.py'],
    pathex=[str(project_path)],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'json',
        'logging',
        'urllib.request',
        'urllib.error',
        'datetime',
        'pathlib',
        'random',
        're',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'tkinter',
        'test',
        'unittest',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LottoGeneratorPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 앱이므로 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 아이콘 파일이 있으면 'icon.ico' 경로 지정
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LottoGeneratorPro',
)

# =============================================================================
# 빌드 방법
# =============================================================================
# 1. PyInstaller 설치
#    pip install pyinstaller
#
# 2. 빌드 실행
#    pyinstaller klottogenerator.spec
#
# 3. 결과물 위치
#    dist/LottoGeneratorPro/LottoGeneratorPro.exe
#
# =============================================================================
# 단일 파일 빌드 (선택사항)
# =============================================================================
# 단일 실행 파일로 빌드하려면 아래 EXE 설정을 사용하세요:
#
# exe = EXE(
#     pyz,
#     a.scripts,
#     a.binaries,
#     a.datas,
#     [],
#     name='LottoGeneratorPro',
#     debug=False,
#     bootloader_ignore_signals=False,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     runtime_tmpdir=None,
#     console=False,
#     disable_windowed_traceback=False,
#     argv_emulation=False,
#     target_arch=None,
#     codesign_identity=None,
#     entitlements_file=None,
#     icon=None,
# )
#
# 그리고 COLLECT 블록을 제거하세요.
# =============================================================================
