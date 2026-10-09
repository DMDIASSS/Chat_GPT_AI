@echo off
setlocal
cd /d "%~dp0"
title Chat GPT AI - RLViser

echo ===== Chat GPT AI - WATCH CHECKPOINT =====
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python virtual environment not found. Run START_HERE.bat first.
  goto failed
)
if not exist "watch.py" (
  echo ERROR: watch.py is missing. Extract the add-on ZIP into this project folder.
  goto failed
)

.venv\Scripts\python.exe -c "from rlgym.rocket_league.rlviser import RLViserRenderer" >nul 2>&1
if errorlevel 1 (
  echo Installing lightweight viewer Python dependencies...
  .venv\Scripts\python.exe -m pip install "rlgym[rl-rlviser]"
  if errorlevel 1 goto failed
)

if not exist "rlviser.exe" (
  echo Downloading RLViser v0.8.7 for Windows from the official GitHub release...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'https://github.com/VirxEC/rlviser/releases/download/v0.8.7/rlviser.exe' -OutFile 'rlviser.exe' -ErrorAction Stop } catch { Write-Error $_; exit 1 }"
  if errorlevel 1 (
    echo Download failed. Visit https://github.com/VirxEC/rlviser/releases/tag/v0.8.7
    echo and download rlviser.exe into this folder manually.
    goto failed
  )
)

.venv\Scripts\python.exe watch.py --preset smoke
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo.
echo Viewer setup or playback failed; copy the error message above.
pause
exit /b 1
