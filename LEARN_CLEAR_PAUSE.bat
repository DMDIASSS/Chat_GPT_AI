@echo off
cd /d "%~dp0"
echo WARNING: only clear pause when learner has fully exited.
choice /C YN /M "Has the learner fully exited?"
if errorlevel 2 exit /b 1
if exist "data\afk_improved\learning\learning.pause" del "data\afk_improved\learning\learning.pause"
echo Pause request cleared; next run may resume safely.
pause
