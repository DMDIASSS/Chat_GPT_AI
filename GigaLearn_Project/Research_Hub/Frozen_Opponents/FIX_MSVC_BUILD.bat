@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3.11 "%~dp0apply_msvc_hotfix.py"
) else (
  python "%~dp0apply_msvc_hotfix.py"
)
if errorlevel 1 (
 echo.
 echo FIX FAILED. No C++ build was attempted. Send the error above.
 pause
 exit /b 1
)
echo.
echo Hotfix applied. Re-run 2_BUILD.bat inside x64 Native Tools Command Prompt for VS 2022.
pause
