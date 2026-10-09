@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract this upgrade into your Chat_GPT_AI project root.
 pause
 exit /b 1
)
if not exist "data\checkpoints\chat_gpt_ai" (
 echo ERROR: Student PPO checkpoint not found. Run distillation and START_STUDENT_PPO.bat first,
 echo or keep your existing trained checkpoint folder at data\checkpoints\chat_gpt_ai.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -c "from rlgym.rocket_league.rlviser import RLViserRenderer; print('RLViser Python integration is available')"
if errorlevel 1 (
 echo Viewer dependency missing. Run: .venv\Scripts\python.exe -m pip install "rlgym[rl-rlviser]"
 pause
 exit /b 1
)
".venv\Scripts\python.exe" benchmark_vs_nexto.py --games 3 --episode-decisions 750 --seed 123 --render --speed 1
if errorlevel 1 echo Viewer failed; check that the RLViser desktop executable is installed/running.
pause
