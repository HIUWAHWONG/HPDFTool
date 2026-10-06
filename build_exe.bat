@echo off
chcp 65001 >nul
cd /d "%~dp0"
title HPDFTool 一键打包

REM ---------------------------------------------------------
REM  用法: 把本文件和 HPDFTool.py 放在同一个文件夹, 双击运行即可
REM  可选: 放一个 app.ico 在同目录, exe 会使用它作为图标
REM  模式: onefile = 单个 exe, 方便分发(启动稍慢)
REM        onedir  = 一个文件夹, 启动更快, 也更不容易被杀毒软件误报
REM ---------------------------------------------------------
set MODE=--onefile

echo ==== [1/4] 检查 Python ====
python --version >nul 2>&1
if errorlevel 1 (
    echo 未找到 Python。请先安装 Python 3.9 或更高版本，安装时务必勾选 "Add python.exe to PATH"。
    pause
    exit /b 1
)

echo ==== [2/4] 创建干净的虚拟环境（体积更小）====
if not exist .venv_build python -m venv .venv_build
call .venv_build\Scripts\activate.bat

echo ==== [3/4] 安装依赖 ====
python -m pip install --upgrade pip -q
pip install pymupdf pillow pyinstaller -q
if errorlevel 1 goto :err

echo ==== [4/4] 开始打包（需要一两分钟）====
set ICON=
if exist app.ico set ICON=--icon app.ico
pyinstaller --noconsole %MODE% --clean --name HPDFTool %ICON% HPDFTool.py
if errorlevel 1 goto :err

echo.
echo ================================================
echo  打包成功！
if "%MODE%"=="--onefile" (echo  程序位置: dist\HPDFTool.exe) else (echo  程序位置: dist\HPDFTool\HPDFTool.exe)
echo ================================================
explorer dist
pause
exit /b 0

:err
echo.
echo 打包失败，请把上面的报错信息发给我。
pause
exit /b 1
