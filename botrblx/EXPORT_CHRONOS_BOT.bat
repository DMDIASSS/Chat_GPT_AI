@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" botrblx\build_chronos.py --download
) else (
  python botrblx\build_chronos.py --download
)
if errorlevel 1 (
  echo Chronos export failed. Check the error above.
) else (
  echo Ready: downloads\TurboBall_Chronos.lua
)
pause
