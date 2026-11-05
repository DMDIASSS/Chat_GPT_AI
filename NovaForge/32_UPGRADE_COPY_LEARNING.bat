@echo off
setlocal
cd /d "%~dp0"
echo Pause copying with 22 and wait for it to exit before upgrading.
".venv\Scripts\python.exe" run.py copy-upgrade --run copy02
if errorlevel 1 goto failed
echo Upgrade ready. Start or resume with 21. Your published student is preserved.
pause
exit /b 0
:failed
echo UPGRADE_FAILED - Keep the error above. No fresh bot is needed.
pause
exit /b 1
