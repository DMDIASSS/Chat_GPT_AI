@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
chcp 65001 >nul
if exist ".venv\Scripts\python.exe" (
 ".venv\Scripts\python.exe" -u download_2v2_gc3_ssl.py auto %*
) else (
 py -3 -u download_2v2_gc3_ssl.py auto %*
)
set "DOWNLOAD_EXIT=%ERRORLEVEL%"
echo.
echo Download folder: data\replays\ranked-doubles
pause
exit /b %DOWNLOAD_EXIT%
