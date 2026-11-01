@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing .venv Python & pause & exit /b 1)
if not exist "data\isolated\mechanics_comparison01.json" (echo Run MECHANICS_0_COMPARE first. & pause & exit /b 1)
".venv\Scripts\python.exe" -u slater_mechanics_trainer.py resume --selection data/isolated/mechanics_comparison01.json
pause
