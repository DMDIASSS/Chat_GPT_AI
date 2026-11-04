@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -r requirements-wandb.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py wandb-check
if errorlevel 1 goto login_needed
echo W_AND_B_READY - Copy frozen teachers with 21_START_OR_RESUME_COPY.bat or continue PPO with 18.
pause
exit /b 0
:login_needed
echo W_AND_B_LOGIN_CHECK_FAILED - Your saved login may be missing, invalid, or unreachable.
echo If needed, run this locally in NovaForge, then rerun this script:
echo .venv\Scripts\python.exe -m wandb login
echo The key stays with the W and B SDK on your PC.
pause
exit /b 1
:failed
echo W_AND_B_INSTALL_FAILED - Keep the pip error above for diagnosis.
pause
exit /b 1
