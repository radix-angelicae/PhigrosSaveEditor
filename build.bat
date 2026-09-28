@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title Phigros Save Editor - Build EXE

echo ==========================================================
echo    Phigros Cloud Save Editor   One-click EXE Build
echo ==========================================================
echo.

rem ---------- 0. Check Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.9-3.12 and tick "Add python.exe to PATH".
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
echo Python %PYVER% detected.
echo.

rem ---------- pip mirror: change to  set "MIRROR="  to use official PyPI ----------
set "MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"
set "TRUSTHOST=pypi.tuna.tsinghua.edu.cn"

rem ---------- 1. venv ----------
set "PY=.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" (
    echo [1/5] venv already exists, skip.
    goto :step2
)
echo [1/5] Creating venv .venv ...
python -m venv .venv
if exist ".venv\Scripts\python.exe" goto :step2
echo       venv failed, fall back to system Python.
set "PY=python"

:step2
echo       using: %PY%
"%PY%" -c "import sys;print('       ok', sys.version.split()[0])"

rem ---------- 2. upgrade pip ----------
echo [2/5] Upgrading pip ...
"%PY%" -m pip install -U pip -q --disable-pip-version-check --index-url %MIRROR% --trusted-host %TRUSTHOST%
if errorlevel 1 "%PY%" -m pip install -U pip -q --disable-pip-version-check

rem ---------- 3. install deps ----------
echo [3/5] Installing pycryptodome and pyinstaller ...
"%PY%" -m pip install -r requirements.txt --disable-pip-version-check --index-url %MIRROR% --trusted-host %TRUSTHOST%
if errorlevel 1 (
    echo       mirror failed, retry with official PyPI ...
    "%PY%" -m pip install -r requirements.txt --disable-pip-version-check
    if errorlevel 1 goto :fail
)

rem ---------- 4. clean ----------
echo [4/5] Cleaning old build ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist PhigrosSaveEditor.spec del /q PhigrosSaveEditor.spec

rem ---------- 5. build ----------
echo [5/5] Building with PyInstaller, takes 1-3 minutes ...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name PhigrosSaveEditor --hidden-import Crypto --hidden-import Crypto.Cipher --hidden-import Crypto.Util.Padding --hidden-import phigros_cloud --hidden-import phi_format --hidden-import phi_paths --hidden-import phi_theme --hidden-import phi_undo --hidden-import phi_views --hidden-import phi_cloud_ui --hidden-import phi_files --hidden-import phi_unlock --hidden-import phi_unlock_ui --hidden-import phi_chapters --hidden-import phi_app --collect-submodules Crypto --icon resources\app.ico --add-data resources;resources phigros_editor.py
if errorlevel 1 goto :fail

echo.
echo ==========================================================
echo    BUILD OK
echo    Output: %~dp0dist\PhigrosSaveEditor.exe
echo    Double click to run, no Python needed.
echo ==========================================================
echo.
if not exist "dist\PhigrosSaveEditor.exe" echo [WARN] exe not found under dist, something went wrong.
echo.
echo [6/6] Refreshing Windows icon cache ...
ie4uinit.exe -ClearIconCache >nul 2>&1
if errorlevel 1 echo   (cache tool unavailable, skipped)
echo.
echo If Explorer still shows the old icon, it is Explorer cache. Try:
echo   1. Move or rename the exe, then look again
echo   2. Or run: taskkill /f /im explorer.exe  then  start explorer.exe
echo.
pause
exit /b 0

:fail
echo.
echo [BUILD FAILED] Please check:
echo   1. Python 3.9 - 3.12 recommended, 3.13 may break PyInstaller
echo   2. Network access to PyPI, or edit this file: set MIRROR= to use official source
echo   3. Avoid restricted folders, put this folder on Desktop and retry
echo   4. Manual fallback: see README.md section "Manual build command"
pause
exit /b 1
