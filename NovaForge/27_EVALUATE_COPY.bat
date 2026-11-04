@echo off
setlocal
cd /d "%~dp0"
echo Pause copying with 22 and wait for it to exit before evaluating.
".venv\Scripts\python.exe" run.py evaluate --model runs\copy01 --baseline runs\copy01\checkpoints\initial.zip --config runs\copy01\config.json --opponents scripted,nexto,ripple,chronos,galactus --pairs 5 --seconds 20 --out reports\copy_eval_%RANDOM%_%RANDOM%.json
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py copy-report --run copy01
if errorlevel 1 goto failed
echo Upload the new copy report ZIP from reports. Resume with 21.
pause
exit /b 0
:failed
echo EVALUATION_FAILED - Keep the error above.
pause
exit /b 1
