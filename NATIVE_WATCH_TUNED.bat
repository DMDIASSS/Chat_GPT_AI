@echo off
cd /d "%~dp0"
echo Watching experimentally fine-tuned original Nexto policy versus frozen Nexto.
.venv\Scripts\python.exe native_nexto.py --mode eval --checkpoint data\native_nexto\last.pt --render --games 1 --eval-decisions 750 --device cpu
pause
