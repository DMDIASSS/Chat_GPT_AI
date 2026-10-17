@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_team_campaign.py check-current %*
set "SLATER_TEAM_EXIT=%errorlevel%"
pause
exit /b %SLATER_TEAM_EXIT%
