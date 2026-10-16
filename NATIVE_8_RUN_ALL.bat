@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_native_campaign.py prepare --bank data/isolated/ranked_duels_quality_bank01.bin
if errorlevel 1 goto done
.venv\Scripts\python.exe -u slater_native_campaign.py all --run native_quality02 --bank data/isolated/ranked_duels_quality_bank01.bin
:done
pause
