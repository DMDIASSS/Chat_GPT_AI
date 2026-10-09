@echo off
setlocal
cd /d "%~dp0"
if not exist "data\nexto_student_policy.pt" (
 echo ERROR: No Nexto student weights. Run DISTILL_NEXTO.bat first.
 pause
 exit /b 1
)
if not exist "train.py" (
 echo ERROR: Extract into Chat_GPT_AI folder next to train.py.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -c "from chatgpt_ai.config import PRESETS; assert 'grounded' in PRESETS, 'Grounded Upgrade is not installed'"
if errorlevel 1 (
 echo ERROR: Grounded Upgrade is required. Keep it installed.
 pause
 exit /b 1
)
echo.
echo This starts a NEW PPO branch from Nexto student weights, NOT direct fine-tuning of Nexto.
echo Your existing checkpoints will be MOVED to a dated backup folder first.
echo The old checkpoints will NOT be deleted.
choice /C YN /M "Create backup and start 1M timestep PPO experiment"
if errorlevel 2 exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -Command "$src='data\checkpoints\chat_gpt_ai'; if (Test-Path $src) { $stamp=Get-Date -Format yyyyMMdd_HHmmss; Move-Item -LiteralPath $src -Destination ('data\checkpoints\chat_gpt_ai_before_nexto_'+$stamp) -ErrorAction Stop; Write-Host 'Backed up old checkpoints' }"
if errorlevel 1 (
 echo Backup failed. No training started.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" train.py --preset grounded --steps 1000000 --workers 2 --batch 10000 --minibatch 2000 --save-every 100000 --device cuda:0 --fresh --init-policy "data\nexto_student_policy.pt"
if errorlevel 1 echo Training interrupted. Backups remain unchanged.
pause
