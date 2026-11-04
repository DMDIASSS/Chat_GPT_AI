@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py viewer-setup
if errorlevel 1 goto failed
echo RLViser is ready. Run 24_WATCH_COPY.bat to view your student.
pause
exit /b 0
:failed
echo VIEWER_SETUP_FAILED - Keep the error above.
pause
exit /b 1
