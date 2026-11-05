@echo off
setlocal
cd /d "%~dp0"
echo TRIAD WATCH - random expert selection.
echo RLViser is found in Chat_GPT_AI or NovaForge and opens on the first frame.
echo Stop other watch consoles with Ctrl+C first.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py watch
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo TRIAD_WATCH_FAILED - keep the error above. Close other viewer sessions and retry.
pause
exit /b 1
