@echo off
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (
  echo Python 3.11 not found in default location. Please run: py -3.11 install_cpp.py
  pause
  exit /b 1
)
"%PY%" install_cpp.py
if errorlevel 1 (echo CPP installation failed! & pause & exit /b 1)
echo C++ source installed, now open VS2022 x64 Native Tools Prompt and run CURRICULUM_2_BUILD_CPP.bat
pause
