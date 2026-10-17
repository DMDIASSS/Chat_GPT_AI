@echo off
cd /d "%~dp0"
echo Pause native campaigns and rebuild before this NEW finite scoring experiment.
.venv\Scripts\python.exe -u slater_native_scoring_experiment.py run
pause
