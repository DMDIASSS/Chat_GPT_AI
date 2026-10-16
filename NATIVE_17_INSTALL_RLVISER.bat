@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m pip install --no-deps rlviser-py==0.6.14
echo Open the RLViser desktop application before running NATIVE_17_WATCH_RLVISER.bat.
echo Viewer releases: https://github.com/VirxEC/rlviser/releases/latest
pause
