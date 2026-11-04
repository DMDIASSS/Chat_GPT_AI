@echo off
setlocal
cd /d "%~dp0"
echo Open the standalone rlviser.exe first. Ctrl+C stops viewing.
".venv\Scripts\python.exe" run.py watch --model runs\copy01 --config runs\copy01\config.json --opponent scripted --scenario kickoff --seconds 20
pause
