@echo off
setlocal
for %%I in ("%~dp0..\..\..\..") do set "ROOT=%%~fI"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 missing: %PY% & pause & exit /b 1)
set "PYTHONPATH=%ROOT%\.venv\Lib\site-packages;%PYTHONPATH%"
"%PY%" "%~dp0run_pipeline.py" link
if errorlevel 1 (echo FAILED & pause & exit /b 1)
echo LINKED DATASET READY. Now run 2_INSTALL_READER.bat.
pause
