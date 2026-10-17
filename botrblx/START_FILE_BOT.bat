@echo off
call "%~dp0START_BOT.bat" --transport files --choose-workspace %*
exit /b %errorlevel%
