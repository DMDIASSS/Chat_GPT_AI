@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP_TRAINING.bat first.
  exit /b 1
)
if not exist "tools\luau.exe" (
  echo Get the official Luau CLI from https://github.com/luau-lang/luau/releases/latest
  echo Put luau.exe in this folder's tools directory. This is separate from JJSploit.
  exit /b 1
)
if not exist "private\engine.json" (
  echo Run PREPARE_TRAINING.bat with your quoted RoWorld place path first.
  exit /b 1
)
.venv\Scripts\python.exe -u training\train.py --engine private\engine.json --luau tools\luau.exe %*
exit /b %errorlevel%
