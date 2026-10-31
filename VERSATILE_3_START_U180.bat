@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_versatile_trainer.py start --source data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt --dataset data/isolated/versatile_data01 --run versatile01 --cycles 3
pause
