@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m unittest -v test_fusion_logic
if errorlevel 1 pause
