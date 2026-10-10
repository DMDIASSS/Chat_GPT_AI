@echo off
cd /d "%~dp0"
echo Place your .replay files in data\replay_defense\replays (including subfolders).
echo This ranks replays by shots+saves and extracts up to 12 threats per replay.
.venv\Scripts\python.exe -u replay_defense.py index --max-shots 12 --leads 1.5 3 5 10
if errorlevel 1 echo EXTRACT FAILED. Send the traceback.
pause
