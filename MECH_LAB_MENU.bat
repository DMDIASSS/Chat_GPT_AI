@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo This add-on must be extracted into E:\Downloads\Chat_GPT_AI.
 pause
 exit /b 1
)
:menu
echo.
echo ============== Chat GPT AI MECHANICS LAB ==============
echo  1. Validate RocketSim scenarios (NO training)
echo  2. Train RECOVERY - 1024 decisions
echo  3. Train WAVEDASH - 1024 decisions
echo  4. Train KICKOFF timing vs frozen Nexto - 1024 decisions
echo  5. Train AERIAL TOUCH - 1024 decisions
echo  6. Train AIR DRIBBLE - 1024 decisions
echo  7. Train FLIP RESET - 1024 decisions [experimental]
echo  8. Train DOUBLE TAP - 1024 decisions [experimental]
echo  9. Train GROUND PINCH - 1024 decisions [experimental]
echo  A. Train WALL PINCH - 1024 decisions [experimental]
echo  B. Train CEILING TOUCH - 1024 decisions [experimental]
echo  C. Evaluate selected stage vs 10K baseline + Nexto
 echo D. Watch selected mechanic stage in RLViser
 echo Q. Quit
choice /C 123456789ABCDQ /N /M "Choose task: "
set "CH=%errorlevel%"
if "%CH%"=="14" goto end
if "%CH%"=="1" (
 ".venv\Scripts\python.exe" -u mechanics_doctor.py
 goto after
)
if "%CH%"=="2" set "STAGE=recovery"
if "%CH%"=="3" set "STAGE=wavedash"
if "%CH%"=="4" set "STAGE=kickoff"
if "%CH%"=="5" set "STAGE=aerial_touch"
if "%CH%"=="6" set "STAGE=air_dribble"
if "%CH%"=="7" set "STAGE=flip_reset"
if "%CH%"=="8" set "STAGE=double_tap"
if "%CH%"=="9" set "STAGE=ground_pinch"
if "%CH%"=="10" set "STAGE=wall_pinch"
if "%CH%"=="11" set "STAGE=ceiling_touch"
if "%CH%"=="12" goto evaluate
if "%CH%"=="13" goto watch
set "OPP=passive"
if "%STAGE%"=="kickoff" set "OPP=nexto"
".venv\Scripts\python.exe" -u mechanics_train.py --stage "%STAGE%" --steps 1024 --episode-decisions 100 --rollout 256 --minibatch 64 --epochs 2 --device cpu --opponent "%OPP%"
if errorlevel 1 (
 echo Stage training failed. If a checkpoint already exists, use --resume and a larger --steps from PowerShell.
)
goto after
:evaluate
set /p "STAGE=Stage to evaluate (see list): "
set "OPP=passive"
if "%STAGE%"=="kickoff" set "OPP=nexto"
".venv\Scripts\python.exe" -u mechanics_evaluate.py --stage "%STAGE%" --opponent "%OPP%" --episodes 12 --seed 741 --competitive --competitive-games 12
goto after
:watch
set /p "STAGE=Stage to watch (see list): "
".venv\Scripts\python.exe" -u mechanics_watch.py --stage "%STAGE%" --source candidate --speed 1
goto after
:after
echo.
pause
goto menu
:end
endlocal
