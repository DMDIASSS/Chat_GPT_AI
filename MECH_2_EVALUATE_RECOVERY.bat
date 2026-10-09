@echo off
cd /d "%~dp0"
echo PAIRWISE recovery test + frozen Nexto competitive guardrail
".venv\Scripts\python.exe" -u mechanics_evaluate.py --stage recovery --episodes 12 --episode-decisions 100 --seed 741 --competitive --competitive-games 12
if errorlevel 1 (echo FAILED. Save the traceback.&pause&exit /b 1)
pause
