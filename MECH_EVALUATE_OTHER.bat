@echo off
cd /d "%~dp0"
echo Valid stage names: wavedash aerial_touch kickoff air_dribble flip_reset double_tap ground_pinch wall_pinch ceiling_touch
set /p STAGE=Enter stage to evaluate:
".venv\Scripts\python.exe" -u mechanics_evaluate.py --stage "%STAGE%" --episodes 12 --seed 741 --competitive --competitive-games 12
if errorlevel 1 (echo FAILED. Save traceback.&pause&exit /b 1)
pause
