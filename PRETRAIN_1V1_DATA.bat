@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run START_HERE.bat to create your Python environment first.
  pause
  exit /b 1
)
if not exist "replays_to_dataset.py" (
  echo ERROR: Copy this add-on next to the original replays_to_dataset.py and train.py.
  pause
  exit /b 1
)
echo Converting downloaded ranked 1v1 replays to an imitation dataset...
".venv\Scripts\python.exe" replays_to_dataset.py --input "data\replays\ranked-duels" --every 8 --max-samples 200000
if errorlevel 1 goto failed
echo Pretraining Chat GPT AI with behavior cloning...
".venv\Scripts\python.exe" pretrain.py --epochs 8 --batch 256
if errorlevel 1 goto failed
echo SUCCESS: Pretrained policy should be data\bc_policy.pt
pause
exit /b 0
:failed
echo Pretraining failed. Check converter diagnostics above.
pause
exit /b 1
