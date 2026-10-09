@echo off
cd /d "%~dp0"
echo Before continuing, confirm native fine-tuning maintained Nexto baseline skill.
echo Resumes to 10,000 CUMULATIVE decision ticks, not physics ticks.
set /p OKAY=Continue training to 10000 decisions? Type YES: 
if /I not "%OKAY%"=="YES" exit /b 0
.venv\Scripts\python.exe native_nexto.py --mode train --resume --steps 10000 --rollout 512 --minibatch 128 --epochs 2 --episode-decisions 450 --scenarios grounded --device cpu
pause
