@echo off
setlocal
cd /d "%~dp0"
echo Watching the best held-out training candidate. Launcher 24 watches the published policy.
".venv\Scripts\python.exe" run.py watch --model runs\copy02 --copy-checkpoint validation --config runs\copy02\config.json --opponent scorer --scenario kickoff --seconds 20
pause
