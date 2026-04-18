# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Lotto Generator Pro v3.0 (onefile)."""

import sys
from importlib.util import find_spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project_path = Path(SPECPATH)
is_windows = sys.platform.startswith('win')

output_name = 'LottoGeneratorPro_v30'
entry_script = 'run_klotto.py'

exclude_modules = [
    'matplotlib',
    'pandas',
    'scipy',
    'sklearn',
    'test',
    'tests',
    'unittest',
    'pytest',
    'doctest',
    'setuptools',
    'pip',
    'wheel',
    'tkinter',
    'wx',
    'PySide6',
    'PySide2',
    'PyQt6.QtBluetooth',
    'PyQt6.QtDBus',
    'PyQt6.QtDesigner',
    'PyQt6.QtHelp',
    'PyQt6.QtMultimedia',
    'PyQt6.QtMultimediaWidgets',
    'PyQt6.QtNfc',
    'PyQt6.QtOpenGL',
    'PyQt6.QtOpenGLWidgets',
    'PyQt6.QtPositioning',
    'PyQt6.QtPrintSupport',
    'PyQt6.QtQml',
    'PyQt6.QtQuick',
    'PyQt6.QtQuick3D',
    'PyQt6.QtQuickWidgets',
    'PyQt6.QtRemoteObjects',
    'PyQt6.QtSensors',
    'PyQt6.QtSerialPort',
    'PyQt6.QtSpatialAudio',
    'PyQt6.QtSql',
    'PyQt6.QtSvg',
    'PyQt6.QtSvgWidgets',
    'PyQt6.QtTest',
    'PyQt6.QtTextToSpeech',
    'PyQt6.QtWebChannel',
    'PyQt6.QtWebEngineCore',
    'PyQt6.QtWebEngineQuick',
    'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebSockets',
    'PyQt6.QtXml',
    'html',
    'http.server',
    'xmlrpc',
    'multiprocessing',
    'concurrent',
    'asyncio',
    'bz2',
    'lzma',
]

hidden_imports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtNetwork',
    'qrcode',
    'PIL.ImageQt',
    'email',
    'klotto.core.draws',
    'klotto.core.sync_service',
    'klotto.core.backtest',
    'klotto.core.strategy_catalog',
    'klotto.core.strategy_engine',
    'klotto.core.strategy_filters',
    'klotto.data.app_state',
    'klotto.data.models',
    'klotto.net.client',
    'klotto.net.http',
    'klotto.ui.dialogs',
    'klotto.ui.main_window',
    'klotto.ui.scanner',
    'klotto.ui.widgets',
    'klotto.ui.widgets.strategy_editor',
    'klotto.ui.widgets.winning_info',
    'zoneinfo',
]


def has_module(name):
    return find_spec(name) is not None


optional_hidden_imports = []
optional_binaries = []
optional_datas = []

if has_module('numpy'):
    optional_hidden_imports.append('numpy')

if has_module('cv2'):
    optional_hidden_imports.append('cv2')
    optional_binaries.extend(collect_dynamic_libs('cv2'))

if has_module('pyzbar'):
    optional_hidden_imports.append('pyzbar.pyzbar')
    optional_binaries.extend(collect_dynamic_libs('pyzbar'))

if has_module('tzdata'):
    optional_hidden_imports.append('tzdata')
    optional_datas.extend(collect_data_files('tzdata'))


a = Analysis(
    [entry_script],
    pathex=[str(project_path)],
    binaries=optional_binaries,
    datas=[
        (str(project_path / 'data' / 'lotto_history.db'), 'data'),
    ] + optional_datas if (project_path / 'data' / 'lotto_history.db').exists() else optional_datas,
    hiddenimports=hidden_imports + optional_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=exclude_modules,
    noarchive=False,
    optimize=2,
)


def filter_binaries(binaries):
    exclude_patterns = [
        'Qt6Quick',
        'Qt6Qml',
        'Qt6Sql',
        'Qt6Svg',
        'Qt6Pdf',
        'Qt6Multimedia',
        'Qt6Sensors',
        'Qt6Bluetooth',
        'Qt6SerialPort',
        'Qt6Test',
        'Qt6DBus',
        'opengl32sw',
        'd3dcompiler',
        'QtBluetooth',
        'QtMultimedia',
        'QtPositioning',
        'QtQml',
        'QtQuick',
        'QtSensors',
        'QtWebEngine',
        'QtWebSockets',
        'icudt',
        'icuin',
        'icuuc',
    ]
    filtered = []
    for name, path, type_ in binaries:
        if not any(pattern.lower() in name.lower() for pattern in exclude_patterns):
            filtered.append((name, path, type_))
    return filtered



def filter_datas(datas):
    exclude_patterns = [
        'translations',
        'examples',
        'doc',
        'docs',
        'test',
        'tests',
        '__pycache__',
    ]
    filtered = []
    for dest, src, type_ in datas:
        if not any(pattern.lower() in dest.lower() for pattern in exclude_patterns):
            filtered.append((dest, src, type_))
    return filtered



a.binaries = filter_binaries(a.binaries)
a.datas = filter_datas(a.datas)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=output_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=not is_windows,
    upx=not is_windows,
    upx_exclude=[
        'vcruntime140.dll',
        'python*.dll',
        'Qt6Core.dll',
        'Qt6Gui.dll',
        'Qt6Widgets.dll',
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    version=None,
    uac_admin=False,
    uac_uiaccess=False,
)
