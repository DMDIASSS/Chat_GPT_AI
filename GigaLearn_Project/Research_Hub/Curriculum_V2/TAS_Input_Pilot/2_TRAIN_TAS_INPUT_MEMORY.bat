@echo off
setlocal
set "PILOT=%~dp0"
for %%I in ("%PILOT%..\..\..\..") do set "ROOT=%%~fI"
set "TAS=%ROOT%\data\tas"
if not "%~1"=="" set "TAS=%~1"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 not found: %PY% & pause & exit /b 1)
if not exist "%TAS%" (echo TAS folder not found: %TAS% & echo Drag TAS folder onto this BAT & pause & exit /b 1)
set "PYTHONPATH=%ROOT%\.venv\Lib\site-packages;%PYTHONPATH%"
set "PATH=%ROOT%\.venv\Lib\site-packages\torch\lib;%PATH%"
"%PY%" "%PILOT%tas_pilot.py" train-inputs --folder "%TAS%" --output "%PILOT%results" --epochs 5
if errorlevel 1 (echo FAILED - read error message & pause & exit /b 1)
echo.
echo TAS input-memory experiment completed. NOT a GigaLearn policy.
pause
