@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py collect --teacher ripple --opponent nexto --samples 20000 --out datasets\ripple20k.npz
if errorlevel 1 goto failed
echo Collection complete. Next run 5_PRETRAIN.bat
pause
exit /b 0
:failed
echo COLLECTION_FAILED - Choose a fresh dataset name if the file already exists.
pause
exit /b 1
