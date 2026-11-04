@echo off
setlocal
cd /d "%~dp0"
set "COPY_RUN=copy01"
if exist "runs\copy02\copy_state.json" set "COPY_RUN=copy02"
".venv\Scripts\python.exe" run.py status --run %COPY_RUN%
pause
