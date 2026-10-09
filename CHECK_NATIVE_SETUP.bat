@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo ERROR: Extract this add-on into your existing Chat_GPT_AI project, alongside train.py.
  pause
  exit /b 1
)
if not exist vendor\nexto\nexto-model.pt (
  echo ERROR: Missing vendor\nexto\nexto-model.pt. Re-install the earlier Nexto Fast Track add-on.
  pause
  exit /b 1
)
if not exist nexto_teacher.py (
  echo ERROR: Missing nexto_teacher.py. Re-install the earlier Nexto Fast Track add-on.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -c "import torch; import native_nexto; from nexto_teacher import NextoTeacher; t=NextoTeacher('cpu'); print('Native Nexto pretrained model OK; CUDA available:', torch.cuda.is_available())"
if errorlevel 1 (
  echo Preflight failed; do not begin training.
  pause
  exit /b 1
)
echo Setup checks passed.
pause
