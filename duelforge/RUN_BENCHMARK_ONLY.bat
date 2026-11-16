@echo off
cd /d "%~dp0"
py -3.11 tools\preflight.py
if errorlevel 1 echo BENCHMARK_FAILED - keep the error. No models or environments were changed.
pause
