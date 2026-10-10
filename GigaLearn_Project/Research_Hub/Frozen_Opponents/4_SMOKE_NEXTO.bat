@echo off
setlocal
cd /d "%~dp0"
py -3.11 frozen_cli.py run --name nexto_rotation_01 --steps 4096 --rotation 4096 --games 4
if errorlevel 1 (
 echo SMOKE FAILED. Send reports\frozen_ppo.log or command prompt output.
 pause
 exit /b 1
)
echo SUCCESS: First frozen Nexto training cycle saved. Inspect gameplay before scaling.
pause
