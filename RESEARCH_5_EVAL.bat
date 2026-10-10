@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe afk_aggressive_research.py evaluate --radical --eval-games 120
pause
