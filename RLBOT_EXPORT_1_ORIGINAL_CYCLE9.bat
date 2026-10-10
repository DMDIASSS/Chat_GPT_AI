@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe export_rlbot_v4.py --checkpoint "data\autoleague\backups\20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt" --name Cycle9_Original_Test
pause
