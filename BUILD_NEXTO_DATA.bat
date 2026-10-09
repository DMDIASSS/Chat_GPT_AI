@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract this add-on into E:\Downloads\Chat_GPT_AI, next to train.py and .venv
 pause
 exit /b 1
)
if not exist "data\replays\ranked-duels" (
 echo ERROR: No ranked-duels folder; check replay download location.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" build_nexto_dataset.py --input "data\replays\ranked-duels" --max-samples 150000 --every 8 --teacher-batch 256 --device cpu
if errorlevel 1 (
 echo ERROR: Could not build Nexto teacher dataset. Check above message.
) else (
 echo Done. Run DISTILL_NEXTO.bat next.
)
pause
