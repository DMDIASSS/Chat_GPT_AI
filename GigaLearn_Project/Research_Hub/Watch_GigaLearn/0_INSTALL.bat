@echo off
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 not found at %PY% & pause & exit /b 1)
"%PY%" install_watch_cpp.py
if errorlevel 1 (echo ERROR: install failed & pause & exit /b 2)
echo SUCCESS: C++ viewer target installed. Next: 1_BUILD.bat in VS 2022 x64 prompt.
pause
