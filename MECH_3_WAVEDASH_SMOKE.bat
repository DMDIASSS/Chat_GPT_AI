@echo off
cd /d "%~dp0"
echo WAVEDASH proof-of-concept, 1024 decisions, isolated from recovery and original Nexto
".venv\Scripts\python.exe" -u mechanics_train.py --stage wavedash --steps 1024 --episode-decisions 90 --rollout 256 --minibatch 64 --epochs 2 --device cpu
if errorlevel 1 (echo FAILED. Save traceback.&pause&exit /b 1)
pause
