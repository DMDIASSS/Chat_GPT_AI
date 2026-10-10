@echo off
setlocal
cd /d "%~dp0"
set "SEED=%~dp0..\experiments\replay_tas_link_01\checkpoints\0"
if not exist "%SEED%\POLICY.lt" (
 set "SEED=%~dp0..\Curriculum_V2\results\replay_bc_20261010T081846Z_ed9e235\checkpoint\0"
)
if not exist "%SEED%\POLICY.lt" (
 echo ERROR: Replay+TAS-linked GigaLearn seed checkpoint not found in the known locations.
 echo Edit SEED in 3_CREATE_BRANCH.bat to point at the folder containing POLICY.lt.
 pause
 exit /b 1
)
py -3.11 frozen_cli.py create --seed "%SEED%" --name nexto_rotation_01
if errorlevel 1 (
 echo Branch creation failed or branch already exists; no source checkpoints were modified.
 pause
 exit /b 1
)
pause
