@echo off
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (
 echo Standard Python 3.11 not found. Use a working Python 3.11 installation.
 pause & exit /b 1
)
"%PY%" curriculum_app.py
if errorlevel 1 pause
