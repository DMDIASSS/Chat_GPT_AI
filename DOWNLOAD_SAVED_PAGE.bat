@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=py -3.11"
)
echo Downloading up to 150 EXACT replay IDs from your supplied saved HTML page...
echo Note: these are 2v2, not directly compatible with the current 1v1 converter.
%PYTHON% download_ballchasing.py --from-ids saved_page_replay_ids.txt --max-files 150
if errorlevel 1 echo ERROR: See the messages above.
pause
