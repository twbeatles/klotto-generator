@echo off
chcp 65001 >nul
rem ============================================================
rem One-click lotto DB + Excel refresh launcher.
rem Usage: double-click this file. Add "nopause" to skip the
rem final keypress wait (for automated runs):
rem   update_lotto.bat nopause
rem Encoding: this file is intentionally ASCII-only because
rem cmd.exe may parse it in a legacy code page. All Korean
rem messages are printed by scripts\refresh_lotto_data.py,
rem which runs as UTF-8 (chcp 65001 + PYTHONUTF8=1).
rem ============================================================
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ first.
    pause
    exit /b 1
)

python scripts\refresh_lotto_data.py
if errorlevel 1 (
    echo [ERROR] Refresh failed. See messages above.
    pause
    exit /b 1
)

echo [DONE] Latest Excel file has been created in this folder.
if /i not "%~1"=="nopause" pause
exit /b 0
