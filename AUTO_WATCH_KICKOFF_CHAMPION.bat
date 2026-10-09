@echo off
setlocal
cd /d "%~dp0"
if not exist data\autoleague_kickoff\champion.pt (echo ERROR: Kickoff league not initialized. & pause & exit /b 1)
.venv\Scripts\python.exe watch_latest_ai.py --model native --checkpoint "data\autoleague_kickoff\champion.pt" --actions greedy --start grounded --speed 1
pause
