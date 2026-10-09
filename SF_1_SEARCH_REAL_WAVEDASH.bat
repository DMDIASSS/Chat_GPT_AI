@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Extract into existing Chat_GPT_AI project folder.& pause & exit /b 1)
echo CEM search, real RocketSim. No Nexto actor weights changed.
echo STARTER RUN: 6 generations x 24 candidates x 4 varied training situations.
".venv\Scripts\python.exe" -u skillforge_search.py --population 24 --generations 6 --training-seeds 4 --holdout-seeds 16 --seed 1001 --difficulty near
if errorlevel 1 echo Search stopped with error. See traceback above.
pause
