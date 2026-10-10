@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -c "import zipfile,pathlib;root=pathlib.Path('data/afk_improved/learning'); z=zipfile.ZipFile('REPLAY_TAS_UPLOAD_THIS.zip','w',zipfile.ZIP_DEFLATED); names=['dataset_manifest.json','tas_audit.json','training_report.json','verification_last.json']; [z.write(root/n,n) for n in names if (root/n).is_file()]; [z.write(p,'reports/'+p.name) for p in (root/'reports').glob('*.json')] if (root/'reports').exists() else None; z.close(); print('Wrote REPLAY_TAS_UPLOAD_THIS.zip (no weights or raw replays)')"
pause
