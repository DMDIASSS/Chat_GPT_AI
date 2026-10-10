@echo off
setlocal
set "PILOT=%~dp0"
set "TAS=%PILOT%..\..\..\..\data\tas"
if not "%~1"=="" set "TAS=%~1"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 not found: %PY% & pause & exit /b 1)
if not exist "%TAS%" (
 echo TAS folder not found at %TAS%
 echo Drag and drop your TAS folder onto this BAT file.
 pause & exit /b 1
)
"%PY%" "%PILOT%tas_pilot.py" inspect --folder "%TAS%"
pause
