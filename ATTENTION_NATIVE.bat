@echo off
setlocal
set "ATTENTION_EXIT=0"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missingpython
if "%~1"=="" goto usage
if /i not "%~1"=="build" goto launch
where cl >nul 2>&1
if not errorlevel 1 goto launch
set "ATTENTION_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%ATTENTION_VSWHERE%" goto missingcompiler
for /f "usebackq tokens=*" %%i in (`"%ATTENTION_VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "ATTENTION_VSROOT=%%i"
if not defined ATTENTION_VSROOT goto missingcompiler
call "%ATTENTION_VSROOT%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 (
set "ATTENTION_EXIT=1"
goto done
)
:launch
.venv\Scripts\python.exe -u slater_native_attention.py %*
set "ATTENTION_EXIT=%ERRORLEVEL%"
if not "%ATTENTION_EXIT%"=="0" echo Native attention command failed. Read the traceback and the preserved run log.
goto done
:usage
echo Native attention: continuation of your actual update180, in a separate build and run.
echo.
echo ATTENTION_NATIVE.bat build
echo ATTENTION_NATIVE.bat parity --run attention_parity01
echo ATTENTION_NATIVE.bat smoke
echo ATTENTION_NATIVE.bat train --run update180_attention01 --updates 100
echo ATTENTION_NATIVE.bat pause --run update180_attention01
echo ATTENTION_NATIVE.bat resume --run update180_attention01 --updates 100
echo ATTENTION_NATIVE.bat status --run update180_attention01
echo ATTENTION_NATIVE.bat eval --run update180_attention01 --eval-seeds 8 --seconds 60
echo ATTENTION_NATIVE.bat benchmark --run attention_benchmark01 --device cpu --updates 3
echo ATTENTION_NATIVE.bat export --run update180_attention01
echo.
echo Instructions: docs\NATIVE_ATTENTION_README.md
goto done
:missingpython
set "ATTENTION_EXIT=1"
echo Existing project .venv is missing. Restore the project Python environment first.
goto done
:missingcompiler
set "ATTENTION_EXIT=1"
echo Install Visual Studio 2022 Build Tools with Desktop development with C++.
:done
pause
endlocal & exit /b %ATTENTION_EXIT%
