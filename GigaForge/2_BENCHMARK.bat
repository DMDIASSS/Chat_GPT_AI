@echo off
setlocal
cd /d "%~dp0"
echo Benchmark complete learning throughput. Close other trainers.
call "%~dp0_RUN.bat" run benchmark
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
