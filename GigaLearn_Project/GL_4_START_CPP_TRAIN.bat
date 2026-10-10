@echo off
setlocal
cd /d "%~dp0"
if "%GIGALEARN_MESHES%"=="" (
 echo Configure GIGALEARN_MESHES to your local RocketSim collision_meshes folder.
 echo This variable must reference valid collision meshes. No training started.
 pause
 exit /b 3
)
if not exist "%GIGALEARN_MESHES%" (echo Collision mesh directory not found & pause & exit /b 3)
if not exist build\Release\GigaLearnBot.exe (echo Build first with GL_3_BUILD.bat & pause & exit /b 2)
if not exist checkpoints mkdir checkpoints
if not exist reports mkdir reports
cd /d "%~dp0checkpoints"
echo Starting experimental GigaLearn C++ policy from scratch. It is NOT Cycle 9.
"%~dp0build\Release\GigaLearnBot.exe" >> "%~dp0reports\cpp_training.log" 2>&1
echo Exit code %errorlevel%. See reports\cpp_training.log.
pause
