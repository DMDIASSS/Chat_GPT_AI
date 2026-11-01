@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Existing project .venv is missing. Restore it before setting up Freestyle.
  pause
  exit /b 1
)
echo Installing only Freestyle monitoring and native build helpers. Your Torch installation is reused.
.venv\Scripts\python.exe -m pip install -r GigaLearn_Project\Native_Backend\requirements.txt -r GigaLearn_Project\Freestyle\requirements.txt
if errorlevel 1 goto failed
call FREESTYLE_NATIVE.bat build
if errorlevel 1 goto failed
rem Setup checks the native trainer. W&B starts separately with real training;
rem its service shutdown must not hold up opening the desktop app.
call FREESTYLE_NATIVE.bat smoke --wandb-mode disabled
if errorlevel 1 goto failed
echo Setup and the finite smoke run completed. Opening Freestyle desktop controls.
call FREESTYLE_APP.bat
exit /b %ERRORLEVEL%
:failed
echo Freestyle setup failed. Read the saved build/smoke error above; the playing models were not used.
pause
exit /b 1
