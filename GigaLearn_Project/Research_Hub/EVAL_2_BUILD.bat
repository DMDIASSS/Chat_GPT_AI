@echo off
setlocal
cd /d "%~dp0.."
where cl >nul 2>&1
if errorlevel 1 (echo ERROR: Open x64 Native Tools Command Prompt for VS 2022 & pause & exit /b 1)
if not exist build_py311\CMakeCache.txt (echo ERROR: build_py311 missing & pause & exit /b 2)
cmake -S upstream -B build_py311 -G "Visual Studio 17 2022" -A x64
if errorlevel 1 (echo ERROR: CMake configure failed & pause & exit /b 3)
cmake --build build_py311 --config Release --target GigaLearnEval --parallel 4
if errorlevel 1 (echo ERROR: evaluator build failed & pause & exit /b 4)
if not exist build_py311\Release\GigaLearnEval.exe (echo ERROR: executable not found & pause & exit /b 5)
echo SUCCESS: build_py311\Release\GigaLearnEval.exe
pause
