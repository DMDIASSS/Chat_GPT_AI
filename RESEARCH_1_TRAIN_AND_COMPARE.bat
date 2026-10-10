@echo off
cd /d "%~dp0"
echo WARNING: Run only after LEARN_ONE_CLICK and other training jobs have finished.
.venv\Scripts\python.exe afk_aggressive_research.py run --radical --eval-games 120
pause
