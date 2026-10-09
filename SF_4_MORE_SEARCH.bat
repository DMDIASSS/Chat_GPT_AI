@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo Larger independent discovery RUN. May take a while on your CPU.
".venv\Scripts\python.exe" -u skillforge_search.py --out data\skillforge\wavedash_large --population 40 --generations 12 --training-seeds 12 --holdout-seeds 30 --seed 1002 --difficulty varied
if errorlevel 1 echo Search stopped with error.
pause
