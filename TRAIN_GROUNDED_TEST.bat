@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found.
  pause
  exit /b 1
)
if not exist "chatgpt_ai\grounded_rewards.py" (
  echo Install first with INSTALL_GROUNDED.bat
  pause
  exit /b 1
)
if not exist "data\checkpoints\chat_gpt_ai\1000050\PPO_POLICY.pt" (
  echo NOTE: Standard 1m checkpoint not found; this will resume latest if one exists.
)
if exist "data\checkpoints\chat_gpt_ai" if not exist "data\checkpoints\chat_gpt_ai_before_grounded" (
  echo Backing up old PPO checkpoints, please wait...
  powershell -NoProfile -Command "Copy-Item -LiteralPath 'data\checkpoints\chat_gpt_ai' -Destination 'data\checkpoints\chat_gpt_ai_before_grounded' -Recurse -ErrorAction Stop"
  if errorlevel 1 (
    echo Backup failed - not starting training.
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe train.py --preset grounded --steps 1250000 --workers 2 --batch 10000 --minibatch 2000 --save-every 50000 --device cuda:0
pause
