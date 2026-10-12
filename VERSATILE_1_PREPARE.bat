@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_versatile_trainer.py prepare --inputs data/replays --out data/isolated/versatile_data01 --workers 2 --max-replays 100
pause
