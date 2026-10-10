@echo off
setlocal
cd /d "%~dp0"
py -3.11 fix_dll_build_guard.py
if errorlevel 1 (
 echo ERROR: Guard repair failed. Original files preserved. Send output.
 pause
 exit /b 1
)
echo DONE. Now run 4_SMOKE_NEXTO.bat; no recompile needed if DLL check passes.
pause
