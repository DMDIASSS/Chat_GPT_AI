@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_versatile_trainer.py resume --run versatile01 --cycles 3
pause
