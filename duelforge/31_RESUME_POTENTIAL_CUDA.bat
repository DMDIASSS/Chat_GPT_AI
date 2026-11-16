@echo off
setlocal
cd /d "%~dp0"
rem Setup reuses existing Torch runtimes and prefers a CUDA-capable Python.
py -3.11 tools\setup_project.py --python "%~dp0..\gigaforge\.venv_native\Scripts\python.exe" --require-cuda
if errorlevel 1 goto failed
set /p DF_CUDA_PYTHON=<runtime_python.txt
"%DF_CUDA_PYTHON%" -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable in selected runtime: run 30_DIAGNOSE_CUDA.bat'; x=torch.ones(16,device='cuda'); print('CUDA_READY:',torch.cuda.get_device_name()); torch.cuda.synchronize()"
if errorlevel 1 goto failed
set "DUELFORGE_DEVICE=cuda"
call _RUN.bat learn-potential --minutes 60
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo CUDA_RESUME_FAILED - no CPU fallback was requested. Models were preserved.
echo Run 30_DIAGNOSE_CUDA.bat and share runtime_probe_report.json and cuda_diagnostic.json if CUDA remains unavailable.
pause
exit /b 1
