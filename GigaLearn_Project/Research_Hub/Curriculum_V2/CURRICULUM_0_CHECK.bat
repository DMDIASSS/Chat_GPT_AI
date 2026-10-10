@echo off
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 not found; edit PY in this launcher. & pause & exit /b 1)
"%PY%" curriculum_cli.py check
if errorlevel 1 echo Check failed. Read diagnostics.
pause
