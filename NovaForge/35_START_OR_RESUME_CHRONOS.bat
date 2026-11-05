@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py fetch-teachers --names chronos,nexto,ripple,galactus
if errorlevel 1 goto failed
if exist "runs\chronos01\config.json" goto resume
".venv\Scripts\python.exe" run.py chronos-train --run chronos01 --forever --wandb online
goto done
:resume
".venv\Scripts\python.exe" run.py chronos-train --run chronos01 --resume --forever --wandb online
:done
if errorlevel 1 goto failed
echo CHRONOS_STOPPED - Watch with 38, compare with 39, export with 40, report with 41.
pause
exit /b 0
:failed
echo CHRONOS_FAILED - Keep the error above. W and B setup is launcher 17.
pause
exit /b 1
