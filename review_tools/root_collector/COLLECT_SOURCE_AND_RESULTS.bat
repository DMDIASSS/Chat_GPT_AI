@echo off
setlocal
cd /d "%~dp0"
echo Collect code and recent research results. No training or dependency installs.
if exist "%~dp0gigaforge\.venv_native\Scripts\python.exe" goto nested
if exist "%~dp0.venv_native\Scripts\python.exe" goto local
where py >nul 2>nul
if not errorlevel 1 goto launcher
python "%~dp0collect_review.py"
goto finished
:nested
"%~dp0gigaforge\.venv_native\Scripts\python.exe" "%~dp0collect_review.py"
goto finished
:local
"%~dp0.venv_native\Scripts\python.exe" "%~dp0collect_review.py"
goto finished
:launcher
py -3 "%~dp0collect_review.py"
:finished
if errorlevel 1 goto failed
echo Upload the REVIEW_ZIP printed above. Output is in Chat_GPT_AI\review_uploads.
pause
exit /b 0
:failed
echo Collection failed. Keep this output. No training was started.
pause
exit /b 1
