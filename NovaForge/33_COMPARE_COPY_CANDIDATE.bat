@echo off
setlocal
cd /d "%~dp0"
echo Pause copying with 22 and wait for it to exit before comparing.
echo This compares the best held-out candidate with the published bot used by 24 and 27.
echo Both run the same starts on both team sides. This may take several minutes.
".venv\Scripts\python.exe" run.py copy-compare --run copy02
if errorlevel 1 goto failed
echo Upload the newest copy02 report ZIP from reports. Published bot is preserved.
pause
exit /b 0
:failed
echo COMPARISON_FAILED - Keep the error above. If training is running, pause with 22 first.
pause
exit /b 1
