@echo off
setlocal
cd /d "%~dp0"
set "COPY_RUN=copy01"
if exist "runs\copy02\copy_state.json" set "COPY_RUN=copy02"
".venv\Scripts\python.exe" run.py copy-report --run %COPY_RUN%
if errorlevel 1 goto failed
echo Upload the printed copy report ZIP from NovaForge\reports in the chat.
pause
exit /b 0
:failed
echo COPY_REPORT_FAILED - Keep the error above.
pause
exit /b 1
