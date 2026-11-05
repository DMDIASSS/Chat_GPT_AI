@echo off
setlocal
cd /d "%~dp0"
py -3.11 -c "import sys; assert sys.maxsize > 2**32; print(sys.version)"
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install "torch==2.9.1" --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --only-binary=:all: --no-deps -r requirements-viewer.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py doctor
if errorlevel 1 goto failed
echo INSTALL_PASS - Next run 1_CHECK.bat
pause
exit /b 0
:failed
echo INSTALL_FAILED - Install Python 3.11 64-bit with the Windows Python Launcher, then retry.
echo Keep the error text above for diagnosis. See START_HERE.md.
pause
exit /b 1
