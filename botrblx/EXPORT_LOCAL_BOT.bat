@echo off
setlocal
cd /d "%~dp0"
echo Update271 standalone Lua exporter
echo This reads your existing model locally. No weights are downloaded or uploaded.
if defined BOTRBLX_PROJECT_ROOT goto root_selected
set "BOTRBLX_PROJECT_ROOT=%~dp0.."
if exist "%BOTRBLX_PROJECT_ROOT%\.venv\Scripts\python.exe" goto root_selected
if exist "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" set "BOTRBLX_PROJECT_ROOT=E:\Downloads\Chat_GPT_AI"
:root_selected
if defined BOTRBLX_PYTHON goto python_selected
set "BOTRBLX_PYTHON=%BOTRBLX_PROJECT_ROOT%\.venv\Scripts\python.exe"
:python_selected
if not exist "%BOTRBLX_PYTHON%" goto missing_python
"%BOTRBLX_PYTHON%" -u "%~dp0export_standalone.py" --project-root "%BOTRBLX_PROJECT_ROOT%" %*
set "BOTRBLX_EXIT=%errorlevel%"
echo.
echo Export exit code: %BOTRBLX_EXIT%
echo You can close this window after a successful export.
pause
exit /b %BOTRBLX_EXIT%
:missing_python
echo ERROR: Missing existing project Python: %BOTRBLX_PYTHON%
echo Extract botrblx into E:\Downloads\Chat_GPT_AI beside .venv.
pause
exit /b 1
