@echo off
setlocal
cd /d "%~dp0..\.."
where cl >nul 2>&1
if errorlevel 1 (echo ERROR: Run from x64 Native Tools Command Prompt for VS 2022 & pause & exit /b 1)
if not exist build_py311\CMakeCache.txt (echo ERROR: Existing build_py311 config missing & pause & exit /b 2)
cmake -S upstream -B build_py311 -G "Visual Studio 17 2022" -A x64
if errorlevel 1 (echo ERROR: CMake config failed & pause & exit /b 3)
cmake --build build_py311 --config Release --target GigaLearnWatchTeacher --parallel 4
if errorlevel 1 (echo ERROR: Teacher viewer build failed & pause & exit /b 4)
if not exist build_py311\Release\GigaLearnWatchTeacher.exe (echo ERROR: Missing expected viewer EXE & pause & exit /b 5)
echo SUCCESS: GigaLearnWatchTeacher.exe built
pause
