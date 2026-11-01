@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -u -m replay_il.launch pause --run replay_mixed3v3_02 --dataset data\isolated\replay_imitation\dataset_mixed3v3_02 %*
set "PAUSE_EXIT=%ERRORLEVEL%"
pause
exit /b %PAUSE_EXIT%
