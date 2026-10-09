@echo off
cd /d "%~dp0"
echo EXPERIMENT: Fine-tune the ORIGINAL Nexto attention actor for 1,024 decisions.
echo This is NOT a millions-of-steps training job.
echo This saves only to data\native_nexto\last.pt, never overwrites nexto-model.pt.
.venv\Scripts\python.exe native_nexto.py --mode train --steps 1024 --rollout 256 --minibatch 64 --epochs 2 --episode-decisions 450 --scenarios grounded --device cpu
if errorlevel 1 (echo TRAINING FAILED; copy entire traceback.) else (echo Done. Run NATIVE_2_BENCHMARK_TUNED.bat to compare.)
pause
