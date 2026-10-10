@echo off
cd /d "%~dp0"
"C:\Users\almas\AppData\Local\Programs\Python\Python311\python.exe" hub_eval_cpp.py
if errorlevel 1 (echo ERROR: C++ patch failed & pause & exit /b 1)
"C:\Users\almas\AppData\Local\Programs\Python\Python311\python.exe" INSTALL_GAMEPLAY_EVAL.py
if errorlevel 1 (echo ERROR: UI patch failed & pause & exit /b 2)
echo SUCCESS: Rebuild the new evaluator executable using EVAL_2_BUILD.bat in x64 VS 2022 Developer Prompt.
pause
