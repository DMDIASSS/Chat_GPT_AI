@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: This add-on must be extracted into the original Chat_GPT_AI folder.
 pause
 exit /b 1
)
if not exist "chatgpt_ai\grounded_rewards.py" (
 echo ERROR: Run INSTALL_FAST_TRACK.bat first.
 pause
 exit /b 1
)
echo.
echo STEP 1: Validate actual installed RocketSim and Nexto TorchScript.
".venv\Scripts\python.exe" fast_track_doctor.py --engine-smoke
if errorlevel 1 goto fail
echo.
echo STEP 2: Collect 5000 decision ticks of REAL closed-loop Nexto RocketSim play.
echo No API key or human replays required. Existing rollout shards are preserved.
".venv\Scripts\python.exe" collect_nexto_rollouts.py --max-decisions 5000 --episode-decisions 450 --save-every 5000 --scenarios grounded --teacher-device cpu
if errorlevel 1 goto fail
echo.
echo STEP 3: Validate teacher demonstration dataset.
".venv\Scripts\python.exe" inspect_nexto_dataset.py
if errorlevel 1 goto fail
echo.
echo STEP 4: Distill 12 epochs into 92-feature, 90-action compatible student.
if exist "data\bc_policy.pt" (
 ".venv\Scripts\python.exe" distill_nexto.py --dataset "data\datasets\nexto_rollouts" --out "data\nexto_student_policy.pt" --init "data\bc_policy.pt" --epochs 12 --batch 256
) else (
 ".venv\Scripts\python.exe" distill_nexto.py --dataset "data\datasets\nexto_rollouts" --out "data\nexto_student_policy.pt" --epochs 12 --batch 256
)
if errorlevel 1 goto fail
if not exist "data\nexto_student_policy.pt" (
 echo No improved policy saved. Inspect metrics and collect additional rollouts before starting PPO.
 goto fail
)
echo.
echo DONE: Nexto student model saved at data\nexto_student_policy.pt
 echo NEXT: START_STUDENT_PPO.bat after checking README.md
pause
exit /b 0
:fail
echo ERROR: Fast Track first experiment stopped. Look for the first error above.
echo Your existing PPO checkpoints and original replays are untouched.
pause
exit /b 1
