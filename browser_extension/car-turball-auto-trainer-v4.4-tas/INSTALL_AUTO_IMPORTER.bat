@echo off
setlocal
cd /d "%~dp0"
call "%~dp0START_MODEL_IMPORT.bat" --check
if errorlevel 1 (
  echo Auto-start NOT installed: fix the Python environment shown above first.
  pause
  exit /b 1
)
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%STARTUP%" (
  echo Windows Startup folder was not found. Cannot install auto-start.
  pause
  exit /b 1
)
set "SCRIPT=%STARTUP%\CarSoccerModelImporter.vbs"
> "%SCRIPT%" echo Set runner = CreateObject("WScript.Shell")
>> "%SCRIPT%" echo runner.Run Chr(34) ^& "%~dp0START_MODEL_IMPORT.bat" ^& Chr(34), 0, False
if not exist "%SCRIPT%" (
  echo Could not create Startup entry.
  pause
  exit /b 1
)
echo Installed Windows user-login auto-start for the local model converter.
echo Its window runs hidden and the server only listens on 127.0.0.1:8765.
echo Starting the converter now...
start "" wscript.exe "%SCRIPT%"
echo.
echo Now open your Chrome extension and press Upload a model.
echo Python with torch must already be available to START_MODEL_IMPORT.bat.
echo To uninstall auto-start, run REMOVE_AUTO_IMPORTER.bat.
pause
