@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Python venv missing. Extract into existing project.& pause & exit /b 1)
echo Checking syntax without changing any trained models.
".venv\Scripts\python.exe" -m py_compile skillforge_core.py skillforge_search.py skillforge_preflight.py skillforge_imitation.py
if errorlevel 1 (echo Python syntax FAILED&pause&exit /b 1)
echo Syntax OK. Run SF_0_REAL_PREFLIGHT.bat next.
pause
