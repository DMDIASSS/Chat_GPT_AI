@echo off
cd /d "%~dp0"
echo Stop the older native campaign before starting this isolated recovery run.
.venv\Scripts\python.exe -u slater_native_focus_curriculum.py run --run focused_teacher01 --guided-teacher --source-current --skip-bc
pause
