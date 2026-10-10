@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing project .venv & pause & exit /b 1)
".venv\Scripts\python.exe" rl_camera_server.py --opponent nexto --speed 1
if errorlevel 1 pause
