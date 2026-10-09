@echo off
cd /d "%~dp0"
echo KICKOFF speed/time drill against frozen Nexto. Not proof of speedflip.
".venv\Scripts\python.exe" -u mechanics_train.py --stage kickoff --opponent nexto --steps 1024 --episode-decisions 75 --rollout 256 --minibatch 64 --epochs 2 --device cpu
if errorlevel 1 (echo FAILED. Save traceback.&pause&exit /b 1)
pause
