@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u teamplay_v2.py eval --games 40 --episodes 330 --seed 891231 --run-dir data\teamplay_v2\cycle9_shared_2v2
pause
