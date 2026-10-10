@echo off
setlocal
cd /d "%~dp0..\.."
set "CHATROOT=%CD%\.."
set "CMAKE_PREFIX_PATH=%CHATROOT%\.venv\Lib\site-packages\torch"
set "PY311=%LOCALAPPDATA%\Programs\Python\Python311"
if not exist "%PY311%\python.exe" (
 echo Python 3.11 missing. Use your installed standard Python 3.11 path.
 exit /b 1
)
where cl >nul 2>nul
if errorlevel 1 (
 echo Open this BAT inside the x64 Native Tools Command Prompt for VS 2022.
 exit /b 1
)
cmake -S upstream -B build_py311 -DCMAKE_PREFIX_PATH="%CMAKE_PREFIX_PATH%" -DPython_EXECUTABLE="%PY311%\python.exe" -DPYTHON_EXECUTABLE="%PY311%\python.exe" -DPYTHON_INCLUDE_DIR="%PY311%\Include" -DPYTHON_LIBRARY="%PY311%\libs\python311.lib"
if errorlevel 1 (echo CMake configure failed. & exit /b 1)
cmake --build build_py311 --config Release --target GigaLearnReplayBC --parallel 4
if errorlevel 1 (echo New BC target did not compile. Do not start curriculum. & exit /b 1)
echo SUCCESS: build_py311\Release\GigaLearnReplayBC.exe
