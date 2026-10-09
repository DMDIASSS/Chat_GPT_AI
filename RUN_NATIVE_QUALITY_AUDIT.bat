@echo off
cd /d "%~dp0"
echo Chat GPT AI - Original Nexto vs Tuned Native Nexto (quality benchmark)
echo This ONLY reads existing checkpoints. Does NOT train or overwrite your AI.
if not exist "data\native_nexto\last.pt" (
  echo ERROR: Missing data\native_nexto\last.pt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u native_quality_eval.py --checkpoint "data\native_nexto\last.pt" --games 20 --episode-decisions 750 --scenarios kickoff
if errorlevel 1 echo BENCHMARK FAILED. Please send full traceback.
pause
