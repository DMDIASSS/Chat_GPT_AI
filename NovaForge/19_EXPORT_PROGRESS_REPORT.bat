@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py report --run diverse01
if errorlevel 1 goto failed
echo The report ZIP is in NovaForge\reports. Upload that ZIP in the chat.
pause
exit /b 0
:failed
echo REPORT_FAILED - Keep the console output. See PROGRESS_REPORTS.md.
pause
exit /b 1
