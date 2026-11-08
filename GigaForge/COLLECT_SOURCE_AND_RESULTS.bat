@echo off
setlocal
cd /d "%~dp0"
echo Collect project code and evaluation results into a NEW ZIP. No training or installs.
if exist ".venv_native\Scripts\python.exe" goto selected
where py >nul 2>nul
if not errorlevel 1 goto launcher
python "%~dp0collect_review.py"
goto finished
:selected
".venv_native\Scripts\python.exe" "%~dp0collect_review.py"
goto finished
:launcher
py -3.11 "%~dp0collect_review.py"
:finished
if errorlevel 1 goto failed
echo Upload the REVIEW_ZIP printed above. It is in gigaforge\review_uploads.
pause
exit /b 0
:failed
echo Collection failed. Keep this output. No training was started.
pause
exit /b 1
