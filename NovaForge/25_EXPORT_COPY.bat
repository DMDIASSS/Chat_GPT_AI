@echo off
setlocal
cd /d "%~dp0"
set "COPY_RUN=copy01"
if exist "runs\copy02\copy_state.json" set "COPY_RUN=copy02"
".venv\Scripts\python.exe" run.py export-v5 --model runs\%COPY_RUN% --name "NovaForge Teacher Copy %COPY_RUN%"
if errorlevel 1 goto failed
echo In RLBot v5 add the printed exports\...\bot.bot.toml and start an offline 1v1.
pause
exit /b 0
:failed
echo EXPORT_FAILED - Keep the error above.
pause
exit /b 1
