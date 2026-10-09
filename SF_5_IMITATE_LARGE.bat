@echo off
setlocal EnableExtensions
cd /d "%~dp0"
".venv\Scripts\python.exe" -u skillforge_imitation.py train --path data\skillforge\wavedash_large --epochs 40 --minimum-trajectories 8
if errorlevel 1 echo Need at least 8 varied successful training demonstrations AND 50 percent holdout success.
pause
