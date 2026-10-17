@echo off
cd /d "%~dp0"
where cl >nul 2>&1
if not errorlevel 1 goto probe
set "ATTENTION_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%ATTENTION_VSWHERE%" goto missing
for /f "usebackq tokens=*" %%i in (`"%ATTENTION_VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "ATTENTION_VSROOT=%%i"
if not defined ATTENTION_VSROOT goto missing
call "%ATTENTION_VSROOT%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 goto failed
:probe
.venv\Scripts\python.exe slater_attention_native_probe.py %*
set "ATTENTION_PROBE_EXIT=%errorlevel%"
goto done
:missing
echo Install Visual Studio 2022 Build Tools with Desktop development with C++, then rerun.
:failed
set "ATTENTION_PROBE_EXIT=1"
:done
pause
exit /b %ATTENTION_PROBE_EXIT%
