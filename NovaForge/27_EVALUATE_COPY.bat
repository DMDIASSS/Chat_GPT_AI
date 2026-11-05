@echo off
setlocal
cd /d "%~dp0"
set "COPY_RUN=copy01"
if exist "runs\copy02\copy_state.json" set "COPY_RUN=copy02"
set "COPY_BASELINE=runs\%COPY_RUN%\checkpoints\initial.zip"
if "%COPY_RUN%"=="copy02" if exist "runs\copy01\latest.json" set "COPY_BASELINE=runs\copy01"
echo Pause copying with 22 and wait for it to exit before evaluating.
".venv\Scripts\python.exe" run.py evaluate --model runs\%COPY_RUN% --baseline "%COPY_BASELINE%" --config runs\%COPY_RUN%\config.json --opponents scripted,scorer,nexto,ripple,chronos,galactus --pairs 5 --seconds 20 --out reports\copy_eval_%RANDOM%_%RANDOM%.json
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py copy-report --run %COPY_RUN%
if errorlevel 1 goto failed
echo Upload the new copy report ZIP from reports. Resume with 21.
pause
exit /b 0
:failed
echo EVALUATION_FAILED - Keep the error above.
pause
exit /b 1
