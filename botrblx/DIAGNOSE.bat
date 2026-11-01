@echo off
setlocal
cd /d "%~dp0"
set "BOTRBLX_DIAG_LOG=%~dp0diagnostic_launcher.log"
> "%BOTRBLX_DIAG_LOG%" echo [%date% %time%] Starting filesystem diagnostic
echo Botrblx filesystem diagnostic - no game inputs
echo Launcher log: %BOTRBLX_DIAG_LOG%
if defined BOTRBLX_PROJECT_ROOT goto root_selected
set "BOTRBLX_PROJECT_ROOT=%~dp0.."
if exist "%BOTRBLX_PROJECT_ROOT%\.venv\Scripts\python.exe" goto root_selected
if exist "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" set "BOTRBLX_PROJECT_ROOT=E:\Downloads\Chat_GPT_AI"

:root_selected
if defined BOTRBLX_PYTHON goto python_selected
set "BOTRBLX_PYTHON=%BOTRBLX_PROJECT_ROOT%\.venv\Scripts\python.exe"

:python_selected
>> "%BOTRBLX_DIAG_LOG%" echo Project: %BOTRBLX_PROJECT_ROOT%
>> "%BOTRBLX_DIAG_LOG%" echo Python: %BOTRBLX_PYTHON%
if not exist "%BOTRBLX_PYTHON%" goto missing_python
if not exist "%~dp0diagnostics.py" goto missing_files
if not exist "%~dp0JJSploit_Diagnose.lua" goto missing_files
echo Close the bot panel and stop START_FILE_BOT.bat before testing.
echo No installs are needed. Keep this CMD window open.
"%BOTRBLX_PYTHON%" -u "%~dp0diagnostics.py" --project-root "%BOTRBLX_PROJECT_ROOT%" %*
set "BOTRBLX_DIAG_EXIT=%errorlevel%"
>> "%BOTRBLX_DIAG_LOG%" echo Diagnostic exit code: %BOTRBLX_DIAG_EXIT%
echo Report: %~dp0DIAGNOSTIC_REPORT.txt
goto finish

:missing_python
set "BOTRBLX_DIAG_EXIT=1"
echo ERROR: Existing project Python was not found: %BOTRBLX_PYTHON%
>> "%BOTRBLX_DIAG_LOG%" echo ERROR: Existing project Python not found.
echo Place botrblx inside Chat_GPT_AI beside .venv, or set BOTRBLX_PROJECT_ROOT.
goto finish

:missing_files
set "BOTRBLX_DIAG_EXIT=1"
echo ERROR: diagnostics.py or JJSploit_Diagnose.lua is missing beside this launcher.
>> "%BOTRBLX_DIAG_LOG%" echo ERROR: Diagnostic package incomplete.

:finish
echo.
pause
exit /b %BOTRBLX_DIAG_EXIT%
