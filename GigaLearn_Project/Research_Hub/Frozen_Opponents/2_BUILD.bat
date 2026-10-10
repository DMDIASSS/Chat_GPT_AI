@echo off
setlocal
cd /d "%~dp0"
set "BUILD=%~dp0..\..\build_py311"
if not exist "%BUILD%\CMakeCache.txt" (
 echo ERROR: Existing build_py311 configuration not found at %BUILD%
 echo Do not reconfigure blindly. Send this error.
 pause
 exit /b 1
)
cmake --build "%BUILD%" --config Release --target GigaLearnBot --parallel 4
if errorlevel 1 (
 echo BUILD FAILED. Please send the FIRST C++ error, not just the final summary.
 pause
 exit /b 1
)
echo SUCCESS: New GigaLearnBot.exe built. Run 0_PREFLIGHT.bat before training.
pause
