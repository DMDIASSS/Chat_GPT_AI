@echo off
cd /d "%~dp0"
echo First small PPO integration test: writes only tactical_balance_smoke.
".venv\Scripts\python.exe" balance_train.py --mode smoke --steps 96 --rollout 48 --games 4 --decisions 90
if errorlevel 1 pause
