@echo off
setlocal
set "SCRIPT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CarSoccerModelImporter.vbs"
if exist "%SCRIPT%" (
  del "%SCRIPT%"
  echo Auto-start removed. A running importer will close at logoff.
) else (
  echo Auto-start entry was not installed.
)
pause
