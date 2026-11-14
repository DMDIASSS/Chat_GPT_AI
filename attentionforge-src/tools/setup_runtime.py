"""Reuse a known local Python/CUDA stack. Never reinstall a working PyTorch."""
from pathlib import Path
import json,os,subprocess,sys,venv
ROOT=Path(__file__).resolve().parents[1]

def probe(exe):
    if not Path(exe).is_file():return None
    try:
        code='import sys,json,struct; import torch,numpy; print(json.dumps(dict(version=list(sys.version_info[:2]),bits=struct.calcsize("P")*8,cuda=torch.cuda.is_available(),torch=torch.__version__)))'
        r=subprocess.run([str(exe),'-c',code],capture_output=True,text=True,timeout=40)
        data=json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode==0 else None
        if data and data['version']==[3,11] and data['bits']==64:return data
    except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):pass
    return None

def main():
    candidates=[]
    if os.environ.get('ATTENTIONFORGE_PYTHON'):candidates.append(Path(os.environ['ATTENTIONFORGE_PYTHON']))
    for parent in (ROOT.parent,ROOT.parent.parent):
        for p in ('gigaforge/.venv_native/Scripts/python.exe','RocketHive_Replicar_v2/.venv/Scripts/python.exe','novaforge/.venv/Scripts/python.exe','NovaForge/.venv/Scripts/python.exe'):
            candidates.append(parent/p)
    candidates+=[ROOT/'.venv/Scripts/python.exe',Path(sys.executable)]
    working=[]
    for exe in dict.fromkeys(candidates):
        d=probe(exe)
        if d:working.append((exe,d));print('FOUND_RUNTIME:',exe,'CUDA:',d['cuda'],'Torch:',d['torch'],flush=True)
    if working:
        exe,details=max(working,key=lambda p:p[1]['cuda'])
    else:
        if sys.version_info[:2]!=(3,11):raise RuntimeError('Install Python 3.11 x64, or set ATTENTIONFORGE_PYTHON to an existing 3.11 Torch environment.')
        target=ROOT/'.venv';venv.EnvBuilder(with_pip=True).create(target);exe=target/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        # First-time fallback only. Existing CUDA installations are never replaced.
        subprocess.run([str(exe),'-m','pip','install','torch==2.9.1','numpy>=1.26,<3'],check=True)
        details=probe(exe)
        if details is None:raise RuntimeError('New Python runtime failed its Torch/NumPy check')
    # Optional W&B stays optional; training and reports work without it.
    print('SELECTED_RUNTIME:',exe,flush=True)
    (ROOT/'runtime_python.txt').write_text(str(exe.resolve())+'\n',encoding='utf8')
    r=subprocess.run([str(exe),'-u','-m','attentionforge.cli','verify'],cwd=ROOT)
    if r.returncode:raise RuntimeError('Runtime selected, but verification failed. Keep the error above; no old project was changed.')
    print('SETUP_READY. Next run BENCHMARK.bat, then START_OR_RESUME.bat. W&B uses your existing saved login if installed.',flush=True)
if __name__=='__main__':main()
