@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing project .venv & pause & exit /b 1)
".venv\Scripts\python.exe" rl_camera_server.py --window --checkpoint "data\autoleague\backups\20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt" --opponent nexto
if errorlevel 1 pause
