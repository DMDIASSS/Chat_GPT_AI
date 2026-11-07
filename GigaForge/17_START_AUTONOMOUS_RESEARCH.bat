@echo off
setlocal
cd /d "%~dp0"
echo Start/resume research02: larger paired evaluations and protected promising actors.
echo Close older trainers first. Chronos uses Breakout; Galactus uses Octane.
call "%~dp0_RUN.bat" run research --run research02
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo RESEARCH_COMMAND_FAILED - keep the error above. Models and earlier runs were preserved.
pause
exit /b 1
