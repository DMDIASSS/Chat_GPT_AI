@echo off
setlocal
cd /d "%~dp0.."
if not exist "hub_eval.py" (
 echo Gameplay Evaluator not installed. This does not affect training.
 pause
 exit /b 1
)
echo.
echo NOTE: This tests against GigaLearn .lt baselines, NOT Nexto/Cycle9/Wavedash .pt teachers.
echo Results are FIRST-GOAL episodes, not full games. Do not auto-promote.
py -3.11 hub_eval.py --models tri_teacher_challenger_01 nexto_rotation_01 smoke_balanced_01 --pairs 16 --decisions 1800
if errorlevel 1 (
 echo Evaluation error. Check Hub setup and benchmark logs.
 pause
 exit /b 1
)
pause
