@echo off
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 not found & pause & exit /b 1)
echo Choose the numeric checkpoint folder under resultseplay_bc_...
set /p "CHECKPOINT=Full replay BC checkpoint path: "
set /p "EXPNAME=New Hub experiment name: "
"%PY%" curriculum_cli.py branch-to-hub --checkpoint "%CHECKPOINT%" --name "%EXPNAME%"
if errorlevel 1 (echo Branch failed; inspect message. & pause & exit /b 1)
pause
