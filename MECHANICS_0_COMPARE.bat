@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing .venv Python & pause & exit /b 1)
echo Stop training processes that modify the compared checkpoints.
".venv\Scripts\python.exe" -u slater_mechanics_trainer.py compare --candidate-rivals
pause
