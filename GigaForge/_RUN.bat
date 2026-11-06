@echo off
setlocal
cd /d "%~dp0"
set "GIGA_BOOT=.venv_native\Scripts\python.exe"
set "GIGA_ARGS="
if exist "%GIGA_BOOT%" goto launch
set "GIGA_BOOT=..\novaforge\.venv\Scripts\python.exe"
if exist "%GIGA_BOOT%" goto launch
set "GIGA_BOOT=..\NovaForge\.venv\Scripts\python.exe"
if exist "%GIGA_BOOT%" goto launch
set "GIGA_BOOT=py"
set "GIGA_ARGS=-3.11"
:launch
"%GIGA_BOOT%" %GIGA_ARGS% -u runtime_bootstrap.py %*
exit /b %errorlevel%
