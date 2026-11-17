@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt (
echo RUNTIME_MISSING - use your existing DuelForge setup to select Python first.
pause
exit /b 1
)
set /p DF_MESH_PYTHON=<runtime_python.txt
"%DF_MESH_PYTHON%" -u tools\restore_collision_meshes.py
if errorlevel 1 echo MESH_RECOVERY_FAILED - keep the output above. Existing runs were preserved.
pause
