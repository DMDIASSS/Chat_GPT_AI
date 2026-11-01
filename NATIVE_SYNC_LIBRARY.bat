@echo off
cd /d "%~dp0"
echo Stop native training and evaluation before repairing the DLL.
.venv\Scripts\python.exe GigaLearn_Project\Native_Backend\native_setup.py sync-library
if errorlevel 1 goto failed
echo Native library verified. You can restart NATIVE_14_FOCUSED_CURRICULUM.bat.
pause
exit /b 0
:failed
echo Repair failed. Keep the error above and do not start training yet.
pause
exit /b 1
