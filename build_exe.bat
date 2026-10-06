@echo off
chcp 65001 >nul
cd /d "%~dp0"
title HPDFTool - One-Click Executable Builder

REM ---------------------------------------------------------------------------
REM  Usage: Place this batch file in the same directory as HPDFTool.py, then double-click to run.
REM  Optional: Put an 'app.ico' file in the same folder to use it as the application icon.
REM  Modes: --onefile = Bundles everything into a single .exe (easy to distribute, slower startup)
REM         --onedir  = Bundles into a folder (faster startup, less antivirus false positives)
REM ---------------------------------------------------------------------------
set MODE=--onefile

echo ==== [1/4] Checking Python Environment ====
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9 or higher first.
    echo Ensure the option "Add python.exe to PATH" is checked during installation.
    pause
    exit /b 1
)

echo ==== [2/4] Setting Up an Isolated Virtual Environment (Optimizes Output Size) ====
if not exist .venv_build python -m venv .venv_build
call .venv_build\Scripts\activate.bat

echo ==== [3/4] Installing Required Dependencies ====
python -m pip install --upgrade pip -q
pip install pymupdf pillow pyinstaller -q
if errorlevel 1 goto :err

echo ==== [4/4] Building Executable (This may take 1-2 minutes) ====
set ICON=
if exist app.ico set ICON=--icon app.ico
pyinstaller --noconsole %MODE% --clean --name HPDFTool %ICON% HPDFTool.py
if errorlevel 1 goto :err

echo.
echo ===========================================================================
echo  BUILD SUCCESSFUL!
if "%MODE%"=="--onefile" (echo  Executable Path: dist\HPDFTool.exe) else (echo  Executable Path: dist\HPDFTool\HPDFTool.exe)
echo ===========================================================================
explorer dist
pause
exit /b 0

:err
echo.
echo [ERROR] Build failed. Please review the logs above or share the error details.
pause
exit /b 1