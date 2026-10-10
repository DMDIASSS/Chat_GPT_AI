@echo off
cd /d "%~dp0"
echo Isolated 8192 decision PPO tactical balance experiment.
echo Stop AutoLeague/FinishingLab before proceeding.
".venv\Scripts\python.exe" balance_train.py --mode train --steps 8192 --games 80 --decisions 750
if errorlevel 1 pause
