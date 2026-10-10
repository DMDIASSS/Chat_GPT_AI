@echo off
setlocal
for %%I in ("%~dp0..\..\..\..") do set "ROOT=%%~fI"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 missing & pause & exit /b 1)
set "PYTHONPATH=%ROOT%\.venv\Lib\site-packages;%PYTHONPATH%"
"%PY%" "%~dp0run_inputs.py"
if errorlevel 1 (echo INPUT FOLLOWING FAILED; no game model modified & pause & exit /b 1)
echo Input-following report written. It is NOT a native GigaLearn policy.
pause
