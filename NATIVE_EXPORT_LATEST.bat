@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe export_rlbot_v4.py --checkpoint "E:\Downloads\Chat_GPT_AI\data\isolated\native_quality\parity\73c0c8b8e1db376fc9ca0ccd\source\22784256" --name Latest_Scripted --scripted-kickoff
if errorlevel 1 goto done
.venv\Scripts\python.exe export_rlbot_v4.py --checkpoint "E:\Downloads\Chat_GPT_AI\data\isolated\native_quality\parity\73c0c8b8e1db376fc9ca0ccd\source\22784256" --name Latest_Learned
:done
pause
