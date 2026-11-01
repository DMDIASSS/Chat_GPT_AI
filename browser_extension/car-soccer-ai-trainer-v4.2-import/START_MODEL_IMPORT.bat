@echo off
cd /d "%~dp0"
set "GCTPY="
if exist ".venv\Scripts\python.exe" set "GCTPY=%CD%\.venv\Scripts\python.exe"
if not defined GCTPY if exist "..\Chat_GPT_AI\.venv\Scripts\python.exe" set "GCTPY=%CD%\..\Chat_GPT_AI\.venv\Scripts\python.exe"
if not defined GCTPY if exist "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" set "GCTPY=E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe"
if not defined GCTPY (
 echo Could not find your Slater Python environment.
 echo Run model_import_server.py using a Python environment with torch and numpy installed.
 pause
 exit /b 1
)
"%GCTPY%" -u model_import_server.py
pause
