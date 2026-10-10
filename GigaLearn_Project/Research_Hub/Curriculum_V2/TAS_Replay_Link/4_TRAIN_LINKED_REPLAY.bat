@echo off
setlocal
for %%I in ("%~dp0..\..\..\..") do set "ROOT=%%~fI"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 missing & pause & exit /b 1)
set "PYTHONPATH=%ROOT%\.venv\Lib\site-packages;%PYTHONPATH%"
set "PATH=%ROOT%\.venv\Lib\site-packages\torch\lib;%PATH%"
"%PY%" "%~dp0run_pipeline.py" train --epochs 3
if errorlevel 1 (echo TRAINING FAILED; original models untouched & pause & exit /b 1)
echo TRAINING COMPLETED. Read the new validation report; do NOT auto-promote.
pause
