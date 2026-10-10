@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: project virtualenv not found&pause&exit /b 1)
".venv\Scripts\python.exe" -c "import torch, numpy, rlgym, rlgym_tools; from afk_improved_core import verify_starting_files; verify_starting_files(); print('READY: protected Cycle 9 and dependencies verified. Device: CPU')"
if errorlevel 1 (echo FAILED. Install requirements-extra.txt and requirements-train.txt if appropriate. Stop and investigate.&pause&exit /b 1)
echo Passed. Install addon into the original Chat_GPT_AI folder.
pause
