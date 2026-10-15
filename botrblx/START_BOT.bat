@echo off
setlocal
cd /d "%~dp0"
set "BOTRBLX_LAUNCH_LOG=%~dp0launcher.log"
> "%BOTRBLX_LAUNCH_LOG%" echo [%date% %time%] Starting botrblx from %~dp0
echo Update271 Roblox bridge
echo Launcher log: %BOTRBLX_LAUNCH_LOG%

rem Prefer an explicit interpreter, then this checkout, then the known project.
if defined BOTRBLX_PROJECT_ROOT goto root_selected
set "BOTRBLX_PROJECT_ROOT=%~dp0.."
if exist "%BOTRBLX_PROJECT_ROOT%\.venv\Scripts\python.exe" goto root_selected
if exist "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" set "BOTRBLX_PROJECT_ROOT=E:\Downloads\Chat_GPT_AI"

:root_selected
if defined BOTRBLX_PYTHON goto python_selected
set "BOTRBLX_PYTHON=%BOTRBLX_PROJECT_ROOT%\.venv\Scripts\python.exe"

:python_selected
>> "%BOTRBLX_LAUNCH_LOG%" echo Project: %BOTRBLX_PROJECT_ROOT%
>> "%BOTRBLX_LAUNCH_LOG%" echo Python: %BOTRBLX_PYTHON%
if not exist "%BOTRBLX_PYTHON%" goto missing_python
if not exist "%~dp0bridge271.py" goto missing_bridge
if not exist "%~dp0client271.lua" goto missing_client
echo Python: %BOTRBLX_PYTHON%
echo Project: %BOTRBLX_PROJECT_ROOT%
echo Keep this window open. Wait for READY, then execute JJSploit_Launch.lua.
"%BOTRBLX_PYTHON%" -u "%~dp0bridge271.py" --project-root "%BOTRBLX_PROJECT_ROOT%" %*
set "BOTRBLX_EXIT=%errorlevel%"
>> "%BOTRBLX_LAUNCH_LOG%" echo Bridge exit code: %BOTRBLX_EXIT%
echo.
echo Bridge exit code: %BOTRBLX_EXIT%
echo Python log: %~dp0bridge.log
goto finish

:missing_python
set "BOTRBLX_EXIT=1"
echo ERROR: Project Python was not found: %BOTRBLX_PYTHON%
>> "%BOTRBLX_LAUNCH_LOG%" echo ERROR: Project Python was not found.
echo Place botrblx inside Chat_GPT_AI, beside its .venv folder.
echo Or set BOTRBLX_PROJECT_ROOT to the folder containing your training project.
goto finish

:missing_bridge
set "BOTRBLX_EXIT=1"
echo ERROR: bridge271.py is missing beside this launcher. Download the whole botrblx folder.
>> "%BOTRBLX_LAUNCH_LOG%" echo ERROR: bridge271.py missing.
goto finish

:missing_client
set "BOTRBLX_EXIT=1"
echo ERROR: client271.lua is missing beside this launcher. Download the whole botrblx folder.
>> "%BOTRBLX_LAUNCH_LOG%" echo ERROR: client271.lua missing.

:finish
pause
exit /b %BOTRBLX_EXIT%
