@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing .venv & pause & exit /b 1)
.venv\Scripts\python.exe -m unittest -v test_replay_defense
if errorlevel 1 (echo UNIT TESTS FAILED & pause & exit /b 1)
pause
