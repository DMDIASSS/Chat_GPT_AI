@echo off
cd /d "%~dp0"
rem The VBS launcher uses pythonw: the persistent training console stays hidden.
rem For absolutely no CMD flash, launch AFK_IMPROVED_DESKTOP.vbs directly.
start "" wscript.exe "%~dp0AFK_IMPROVED_DESKTOP.vbs"
exit /b 0
