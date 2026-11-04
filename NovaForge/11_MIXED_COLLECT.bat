@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py collect --teacher nexto,ripple,chronos,galactus --opponent nexto --samples 40000 --out datasets\mixed40k.npz
if errorlevel 1 goto failed
echo Collection complete. Next run 12_MIXED_PRETRAIN.bat
pause
exit /b 0
:failed
echo COLLECTION_FAILED - Keep the error above. Existing outputs need a fresh filename.
pause
exit /b 1
