@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_versatile_trainer.py preflight --source data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt --dataset data/isolated/versatile_data01
if errorlevel 1 goto done
.venv\Scripts\python.exe -u slater_versatile_trainer.py smoke --source data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt --dataset data/isolated/versatile_data01 --run versatile_smoke01
:done
pause
