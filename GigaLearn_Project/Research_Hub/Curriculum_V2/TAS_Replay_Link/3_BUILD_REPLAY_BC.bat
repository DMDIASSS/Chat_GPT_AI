@echo off
setlocal
where cl >nul 2>nul
if errorlevel 1 (echo Open in x64 Native Tools Command Prompt for VS 2022. & exit /b 1)
for %%I in ("%~dp0..\..\..") do set "PROJECT=%%~fI"
for %%I in ("%PROJECT%\..") do set "ROOT=%%~fI"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311"
set "CMAKE_PREFIX_PATH=%ROOT%\.venv\Lib\site-packages\torch"
cmake -S "%PROJECT%\upstream" -B "%PROJECT%\build_py311" -DCMAKE_PREFIX_PATH="%CMAKE_PREFIX_PATH%" -DPython_EXECUTABLE="%PY%\python.exe" -DPYTHON_EXECUTABLE="%PY%\python.exe" -DPYTHON_INCLUDE_DIR="%PY%\Include" -DPYTHON_LIBRARY="%PY%\libs\python311.lib"
if errorlevel 1 (echo CMake configure failed. & exit /b 1)
cmake --build "%PROJECT%\build_py311" --config Release --target GigaLearnReplayBC --parallel 4
if errorlevel 1 (echo Compiler failed. & exit /b 1)
echo SUCCESS: Rebuilt linked replay behavior-cloning binary.
