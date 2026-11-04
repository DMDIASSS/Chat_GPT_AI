@echo off
setlocal
cd /d "%~dp0"
if exist "runs\diverse01\config.json" goto resume
if not exist "models\mixed_bc.zip" goto missing_model
".venv\Scripts\python.exe" -u run.py train --run diverse01 --config configs\diverse.json --init models\mixed_bc.zip --forever --wandb online
goto done
:resume
".venv\Scripts\python.exe" -u run.py train --run diverse01 --resume --forever --wandb online
goto done
:missing_model
echo No diverse01 run or mixed BC model found.
echo Run 10_MIXED_CHECK.bat, 11_MIXED_COLLECT.bat and 12_MIXED_PRETRAIN.bat first.
pause
exit /b 1
:done
if errorlevel 1 goto failed
echo Training stopped and saved. Run this launcher again to resume.
pause
exit /b 0
:failed
echo TRAINING_FAILED - Keep the console output. See WANDB_AND_CONTINUOUS.md.
pause
exit /b 1
