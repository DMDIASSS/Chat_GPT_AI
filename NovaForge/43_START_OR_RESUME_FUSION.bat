@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py fetch-teachers --names chronos,ripple,galactus,nexto
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py chronos-combine --run fusion01
if errorlevel 1 goto failed
if exist "runs\fusion01\STOP" goto done
".venv\Scripts\python.exe" run.py chronos-train --run fusion01 --resume --forever --wandb online
:done
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo COMMAND_FAILED - Keep the output above.
pause
exit /b 1
