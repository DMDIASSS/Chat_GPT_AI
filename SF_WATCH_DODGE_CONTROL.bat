@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Extract into your Chat_GPT_AI project folder.& pause& exit /b 1)
echo Showing a known immediate dodge (NOT a valid wavedash). Compare it with the best search attempt.
".venv\Scripts\python.exe" -u skillforge_watch.py --mode dodge --speed 0.5 --repeat 4
if errorlevel 1 echo Viewer failed. Read the error above.
pause
