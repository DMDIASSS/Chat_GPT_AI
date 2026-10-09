@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo WARNING: requires at least 8 separate physically verified training demonstrations.
".venv\Scripts\python.exe" -u skillforge_imitation.py train --epochs 40 --minimum-trajectories 8
if errorlevel 1 echo Refused to train: too few genuine wavedash examples OR discovery below threshold.
pause
