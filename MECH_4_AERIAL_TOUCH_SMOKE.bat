@echo off
cd /d "%~dp0"
echo AERIAL CONTACT foundation; does not automatically learn flip resets.
".venv\Scripts\python.exe" -u mechanics_train.py --stage aerial_touch --steps 1024 --episode-decisions 120 --rollout 256 --minibatch 64 --epochs 2 --device cpu
if errorlevel 1 (echo FAILED. Save traceback.&pause&exit /b 1)
pause
