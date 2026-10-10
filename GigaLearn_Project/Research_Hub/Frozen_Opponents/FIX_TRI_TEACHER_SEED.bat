@echo off
setlocal
cd /d "%~dp0"
py -3.11 fix_tri_teacher_seed.py
if errorlevel 1 (
 echo Hotfix failed. Do not start the extended training launcher yet.
 pause
 exit /b 1
)
py -3.11 frozen_cli.py run --help >nul
if errorlevel 1 (
 echo Verification failed: frozen_cli still does not parse. Do not start training.
 pause
 exit /b 1
)
echo PASS: frozen_cli.py run parser loads without option conflicts.
echo You can now double-click 1_START_TRAIN_1M.bat to resume the SAME challenger.
pause
exit /b 0
