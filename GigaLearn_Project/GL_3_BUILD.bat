@echo off
setlocal
cd /d "%~dp0"
if not exist upstream\CMakeLists.txt (echo First run GL_1_GET_SOURCE.bat & exit /b 2)
where cmake >nul 2>&1 || (echo Install CMake first & exit /b 2)
if not exist cache\ExampleMain.original.cpp (echo First run GL_2_PATCH_EXAMPLE.bat & exit /b 2)
cmake -S upstream -B build -G "Visual Studio 17 2022" -A x64
if errorlevel 1 (echo CMake configure failed & exit /b 1)
cmake --build build --config Release --parallel 4
if errorlevel 1 (echo Build failed; see CMake/Visual Studio errors & exit /b 1)
echo Build completed. It has NOT started training.
pause
