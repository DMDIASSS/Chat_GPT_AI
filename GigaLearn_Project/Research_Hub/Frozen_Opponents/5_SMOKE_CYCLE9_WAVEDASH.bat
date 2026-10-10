@echo off
setlocal
cd /d "%~dp0"
py -3.11 frozen_cli.py run --name nexto_rotation_01 --steps 8192 --rotation 4096 --games 4
if errorlevel 1 (
 echo ROTATION FAILED. Send logs. Existing checkpoints are preserved.
 pause
 exit /b 1
)
echo SUCCESS: Additional opponent cycles saved. Verify log shows Cycle9 + Wavedash.
pause
