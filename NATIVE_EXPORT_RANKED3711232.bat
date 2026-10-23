@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe export_rlbot_v4.py --checkpoint "data\isolated\gigalearn_native\runs\ranked_duels_train01\checkpoints\3711232" --name Native3711232_Scripted --scripted-kickoff
if errorlevel 1 goto done
.venv\Scripts\python.exe export_rlbot_v4.py --checkpoint "data\isolated\gigalearn_native\runs\ranked_duels_train01\checkpoints\3711232" --name Native3711232_Learned
:done
pause
