@echo off
setlocal
cd /d "%~dp0"
set "GCTPY="
if exist ".venv\Scripts\python.exe" set "GCTPY=%CD%\.venv\Scripts\python.exe"
if not defined GCTPY if exist "..\Chat_GPT_AI\.venv\Scripts\python.exe" set "GCTPY=%CD%\..\Chat_GPT_AI\.venv\Scripts\python.exe"
if not defined GCTPY if exist "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" set "GCTPY=E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe"
if not defined GCTPY for /f "delims=" %%P in ('where python 2^>nul') do if not defined GCTPY set "GCTPY=%%P"
if not defined GCTPY (
  echo Could not find a Python interpreter. Install Python with torch and numpy, or put a .venv next to the extension.
  exit /b 1
)
"%GCTPY%" -c "import torch, numpy" >nul 2>&1
if errorlevel 1 (
  echo Python is available, but torch and numpy could not be imported.
  echo Install torch and numpy in the interpreter: "%GCTPY%"
  exit /b 1
)
if /i "%~1"=="--check" exit /b 0
"%GCTPY%" -u model_import_server.py
