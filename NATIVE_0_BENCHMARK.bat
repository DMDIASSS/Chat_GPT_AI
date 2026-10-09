@echo off
cd /d "%~dp0"
echo BASELINE: Original Nexto model controlling Chat GPT AI against frozen Nexto.
echo Expected result: roughly balanced goal outcomes across sides.
.venv\Scripts\python.exe native_nexto.py --mode baseline --games 20 --eval-decisions 750 --device cpu
if errorlevel 1 (echo Native Nexto benchmark FAILED.) else (echo Benchmark complete. Review outcomes and normalized ball-touch rates.)
pause
