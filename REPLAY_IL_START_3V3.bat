@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Existing project .venv not found.
 pause
 exit /b 1
)
dir /s /b "data\replays\ranked-standard\*.replay" >nul 2>&1
if errorlevel 1 (
 echo No 3v3 replays found. Run DOWNLOAD_3V3_GROUP.bat first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u replay_il_mixed.py %*
set "MIXED_EXIT=%ERRORLEVEL%"
pause
exit /b %MIXED_EXIT%
