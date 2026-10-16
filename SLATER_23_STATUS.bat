@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_team_campaign.py status %*
set "SLATER_TEAM_EXIT=%errorlevel%"
pause
exit /b %SLATER_TEAM_EXIT%
