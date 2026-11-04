@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py export-v5 --model runs\diverse01 --name "NovaForge Diverse"
if errorlevel 1 goto failed
echo In RLBot v5 add the printed exports\...\bot.bot.toml and start an offline 1v1.
pause
exit /b 0
:failed
echo V5_EXPORT_FAILED - Keep the error above.
pause
exit /b 1
