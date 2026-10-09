@echo off
setlocal EnableExtensions
cd /d "%~dp0"
".venv\Scripts\python.exe" -u skillforge_imitation.py evaluate --seeds 24 --seed 928314 --difficulty near
if errorlevel 1 echo Evaluation failed. Need successful search discovery first.
pause
