@echo off
cd /d "%~dp0"
echo Stages: recovery, wavedash, kickoff, aerial_touch, air_dribble, flip_reset, double_tap, ground_pinch, wall_pinch, ceiling_touch
set /p STAGE=Stage to watch:
set /p WHO=Watch baseline or candidate? [baseline/candidate]:
if "%WHO%"=="" set WHO=candidate
".venv\Scripts\python.exe" -u mechanics_watch.py --stage "%STAGE%" --source "%WHO%" --speed 1 --episodes 10
if errorlevel 1 (echo Playback failed. Send traceback.)
pause
