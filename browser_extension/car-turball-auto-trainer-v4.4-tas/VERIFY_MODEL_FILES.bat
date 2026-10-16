@echo off
setlocal
cd /d "%~dp0"
echo Car Soccer AI Trainer - Built-in Model Check
if exist "nexto-weights.bin" (
  echo [OK] nexto-weights.bin exists.
) else (
  echo [MISSING] nexto-weights.bin - Original Nexto WILL NOT work until you restore it.
)
if exist "g9-weights.bin" (
  echo [OK] g9-weights.bin exists.
) else (
  echo [MISSING] g9-weights.bin - G9 WILL NOT work until you restore it.
)
echo.
echo This patch ZIP does not include the model weights.
echo Extract over the ORIGINAL extension folder, not into an empty folder.
echo You may also use Upload a model to import a compatible .bin file as a new AI.
pause
