@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py compare-progress --run diverse01
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py report --run diverse01
if errorlevel 1 goto failed
echo Comparison and report complete. Upload the newest progress ZIP in reports.
pause
exit /b 0
:failed
echo COMPARISON_FAILED - If training is running, pause with 15_MIXED_PAUSE.bat and wait for it to save/exit.
echo Keep any other error shown above for diagnosis.
pause
exit /b 1
