@echo off
setlocal
cd /d "%~dp0.."
echo == GigaLearn Research Hub: Rebuild build_py311 ==
echo Run this batch in x64 Native Tools Command Prompt for VS 2022.
where cl >nul 2>&1
if errorlevel 1 (
 echo ERROR: cl not found. Open x64 Native Tools Command Prompt for VS 2022.
 pause
 exit /b 2
)
if not exist "build_py311\CMakeCache.txt" (
 echo ERROR: build_py311 not configured. Use the working Python 3.11 CMake setup.
 pause
 exit /b 3
)
cmake --build build_py311 --config Release --parallel 4
if errorlevel 1 (echo ERROR: C++ build failed & pause & exit /b 4)
echo SUCCESS: build_py311\Release\GigaLearnBot.exe compiled.
echo Research Hub is ready for an isolated experiment; use safe stop to save.
pause
