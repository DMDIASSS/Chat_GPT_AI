@echo off
setlocal
cd /d "%~dp0"
py -3.11 extended_frozen_cli_patch.py
exit /b %errorlevel%
