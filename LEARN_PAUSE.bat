@echo off
cd /d "%~dp0"
if not exist "data\afk_improved\learning" mkdir "data\afk_improved\learning"
echo pause requested > "data\afk_improved\learning\learning.pause"
echo Requested pause at next replay boundary or completed training epoch.
echo Keep the learner window open until it stops.
pause
