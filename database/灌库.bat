@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "SCRIPT="
for %%f in ("64_*.py") do set "SCRIPT=%%~ff"

if not defined SCRIPT (
  echo [错误] 同目录找不到 64_*.py
  pause
  exit /b 2
)

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 没找到 python。请先安装 Python 3.10+，安装时勾选 "Add python.exe to PATH"。
  pause
  exit /b 2
)

echo 正在启动知识库向量灌库向导...
echo.
python "%SCRIPT%" %*
echo.
pause
