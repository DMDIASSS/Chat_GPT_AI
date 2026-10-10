@echo off
setlocal
cd /d "%~dp0..\.."
where cl >nul 2>&1
if errorlevel 1 (echo ERROR: run in "x64 Native Tools Command Prompt for VS 2022" & pause & exit /b 1)
if not exist build_py311\CMakeCache.txt (echo ERROR: existing build_py311 configuration missing & pause & exit /b 2)
cmake -S upstream -B build_py311 -G "Visual Studio 17 2022" -A x64
if errorlevel 1 (echo ERROR: configuration failed & pause & exit /b 3)
cmake --build build_py311 --config Release --target GigaLearnWatch --parallel 4
if errorlevel 1 (echo ERROR: native viewer build failed & pause & exit /b 4)
if not exist build_py311\Release\GigaLearnWatch.exe (echo ERROR: expected exe missing & pause & exit /b 5)
echo SUCCESS: build_py311\Release\GigaLearnWatch.exe
pause
