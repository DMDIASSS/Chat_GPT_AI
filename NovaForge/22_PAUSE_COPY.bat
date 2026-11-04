@echo off
setlocal
cd /d "%~dp0"
set "COPY_RUN=copy01"
if exist "runs\copy02\copy_state.json" set "COPY_RUN=copy02"
".venv\Scripts\python.exe" run.py pause --run %COPY_RUN%
if errorlevel 1 goto failed
echo Wait for the copying console to save and exit. Resume with 21.
pause
exit /b 0
:failed
echo PAUSE_FAILED - Keep the error above.
pause
exit /b 1
