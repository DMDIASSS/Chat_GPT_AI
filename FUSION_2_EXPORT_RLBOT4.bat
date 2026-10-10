@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u fusion_export.py --name Cycle9_Fusion_v1
if errorlevel 1 pause
