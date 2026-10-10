@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" rl_camera_server.py --checkpoint "data\autoleague\champion.pt" --opponent nexto --speed 1 --port 8766
if errorlevel 1 pause
