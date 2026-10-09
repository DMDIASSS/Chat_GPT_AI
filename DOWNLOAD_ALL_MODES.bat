@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=py -3.11"
)
echo Downloading up to 200 GC3-SSL replays across all four ranked modes...
echo NOTE: Only 1v1 is currently accepted by your imitation-learning converter.
%PYTHON% download_ballchasing.py --playlist all --rank gc3-ssl --max-files 200
if errorlevel 1 echo ERROR: See the messages above, especially rank-filter errors.
pause
