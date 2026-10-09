@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=py -3.11"
)
echo Downloading up to 50 GC3-SSL 1v1 replays via Ballchasing API...
echo API rank syntax is experimental. If rejected, see README_DOWNLOADER.txt.
%PYTHON% download_ballchasing.py --playlist ranked-duels --rank gc3-ssl --max-files 50
if errorlevel 1 echo ERROR: See the messages above, especially rank-filter errors.
pause
