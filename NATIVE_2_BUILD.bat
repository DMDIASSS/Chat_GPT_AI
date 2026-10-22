@echo off
cd /d "%~dp0"
where cl >nul 2>&1
if not errorlevel 1 goto build
set "NATIVE_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%NATIVE_VSWHERE%" goto missing
for /f "usebackq tokens=*" %%i in (`"%NATIVE_VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "NATIVE_VSROOT=%%i"
if not defined NATIVE_VSROOT goto missing
call "%NATIVE_VSROOT%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 goto done
:build
.venv\Scripts\python.exe GigaLearn_Project\Native_Backend\native_setup.py build --jobs 2
goto done
:missing
echo Install Visual Studio 2022 Build Tools with Desktop development with C++, then rerun.
:done
pause
