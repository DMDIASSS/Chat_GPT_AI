@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract into your existing Chat_GPT_AI project with its .venv.
 pause
 exit /b 1
)
echo Close RLBot first. Checking the existing ReplayDuelsDoubles export.
echo No training or replay parsing is performed.
".venv\Scripts\python.exe" -u replay_il_workflow.py repair --folder "data\rlbot_exports\ReplayDuelsDoubles"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -u replay_il_workflow.py analyze --run replay_scratch01 --export-folder "data\rlbot_exports\ReplayDuelsDoubles" --device cpu --analysis-samples 512
if errorlevel 1 goto failed
echo.
echo Check complete. Report: data\isolated\replay_imitation\runs\replay_scratch01\validation_diagnostics.json
echo Restart RLBot and load the same bot.cfg. Live counters save to the export's CONTROL_DIAGNOSTICS.json.
pause
exit /b 0
:failed
set "REPLAY_CHECK_EXIT=%ERRORLEVEL%"
echo.
echo Check stopped. Preserve the error above; do not delete your data.
pause
exit /b %REPLAY_CHECK_EXIT%
