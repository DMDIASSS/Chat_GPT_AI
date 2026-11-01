@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missingpython
".venv\Scripts\python.exe" -c "import json,sys; import slater_training_studio as s; sys.exit('Pause the active Studio job safely and close Studio before installing.') if s.ProcessManager().active else None; d=s.validate_settings(json.load(open('STUDIO_CAMPAIGN_U271_FORMAT_TARGETS.json',encoding='utf-8'))); [s.source_file(p) for p in [d['source'],*d['campaign']['rivals'].values()]]"
if errorlevel 1 goto failed
call ATTENTION_NATIVE.bat build
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import json,shutil,time; import slater_training_studio as s; p=s.BASE/'settings.json'; p.exists() and shutil.copy2(p,p.with_name('settings.before_u271_'+str(time.time_ns())+'.json')); d=s.validate_settings(json.load(open('STUDIO_CAMPAIGN_U271_FORMAT_TARGETS.json',encoding='utf-8'))); s.atomic_json(p,d); print('Loaded campaign u271_targets01: source 271, per-format rivals, scripted kickoff ON.')"
if errorlevel 1 goto failed
start "" "%~dp0TRAINING_STUDIO.vbs"
exit /b 0
:missingpython
echo Existing project .venv is missing.
:failed
echo Setup failed. Read the error above; models and prior campaigns are preserved.
pause
exit /b 1
