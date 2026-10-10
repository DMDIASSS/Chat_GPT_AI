@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m unittest -v test_teamplay_v2.py
if errorlevel 1 echo UNIT TESTS FAILED. Send the traceback; do not train.
pause
