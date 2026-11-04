@echo off
setlocal
cd /d "%~dp0"
if exist "runs\copy01\copy_state.json" goto resume
".venv\Scripts\python.exe" run.py copy-train --run copy01 --forever --wandb online
goto done
:resume
".venv\Scripts\python.exe" run.py copy-train --run copy01 --resume --forever --wandb online
:done
if errorlevel 1 goto failed
echo Copying stopped safely. Watch with 24, export with 25, or report with 26.
pause
exit /b 0
:failed
echo COPY_FAILED - Keep the error above. Missing login: run 17_WANDB_SETUP.bat.
echo Missing teachers: run 3_FETCH_TRAINERS.bat. See FROZEN_TEACHER_COPYING.md.
pause
exit /b 1
