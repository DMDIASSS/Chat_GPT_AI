@echo off
setlocal EnableExtensions
cd /d "%~dp0"
".venv\Scripts\python.exe" -u skillforge_imitation.py evaluate --path data\skillforge\wavedash_large --seeds 30 --seed 928315 --difficulty varied
if errorlevel 1 echo No discovery yet, or an error occurred.
pause
