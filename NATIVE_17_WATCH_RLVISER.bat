@echo off
cd /d "%~dp0"
echo Start the RLViser desktop application first. Learner kickoff script OFF, rival ON.
.venv\Scripts\python.exe -u slater_native_inspect.py watch --seconds 120
pause
