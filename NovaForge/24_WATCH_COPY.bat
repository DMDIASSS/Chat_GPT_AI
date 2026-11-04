@echo off
setlocal
cd /d "%~dp0"
set "COPY_RUN=copy01"
if exist "runs\copy02\copy_state.json" set "COPY_RUN=copy02"
echo RLViser will be found and opened automatically. Ctrl+C stops viewing.
".venv\Scripts\python.exe" run.py watch --model runs\%COPY_RUN% --config runs\%COPY_RUN%\config.json --opponent scripted --scenario kickoff --seconds 20
pause
