@echo off
setlocal
cd /d "%~dp0"
echo Pause Freestyle before continuing. The parent run and all checkpoints are preserved.
call FREESTYLE_NATIVE.bat check-build >nul 2>&1
if not errorlevel 1 goto prepared
echo Building revised rewards. Existing compiler outputs are reused.
call FREESTYLE_NATIVE.bat build
if errorlevel 1 goto failed
:prepared
if exist "data\isolated\freestyle\runs\freestyle_rewards02\protocol.json" goto resume
call FREESTYLE_NATIVE.bat fork --from-run freestyle01 --run freestyle_rewards02
if errorlevel 1 goto failed
:resume
call FREESTYLE_NATIVE.bat resume --run freestyle_rewards02 --wandb-mode online --updates 200 %*
set "FREESTYLE_EXIT=%ERRORLEVEL%"
pause
endlocal & exit /b %FREESTYLE_EXIT%
:failed
echo Continuation stopped. Read the error above; parent checkpoints remain preserved.
pause
endlocal & exit /b 1
