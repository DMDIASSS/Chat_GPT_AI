@echo off
setlocal
cd /d "%~dp0"
if not exist "data\nexto_student_v2.pt" (echo Missing new student weights. Run Step 2 first. & pause & exit /b 1)
echo BASELINE, old student, first-to-score episodes.
".venv\Scripts\python.exe" benchmark_vs_nexto.py --checkpoint data\nexto_student_policy.pt --games 20 --seed 123 --episode-decisions 750
if errorlevel 1 goto fail
echo.
echo NEW v2 student, SAME test settings.
".venv\Scripts\python.exe" benchmark_vs_nexto.py --checkpoint data\nexto_student_v2.pt --games 20 --seed 123 --episode-decisions 750
if errorlevel 1 goto fail
echo Compare student first goals and touches. Do not run a long PPO job until v2 improves.
pause
exit /b 0
:fail
echo Benchmark failed. Keep both weight files and share the error.
pause
exit /b 1
