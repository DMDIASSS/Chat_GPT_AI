"""Reuse a verified existing CPython 3.11 Torch runtime. No Torch/CUDA install."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.preflight import candidates

def setup(explicit=None):
    choices=[];selected=None
    probe="import sys,struct,json,torch,numpy;print(json.dumps({'python':sys.version.split()[0],'bits':struct.calcsize('P')*8,'torch':torch.__version__,'cuda':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name() if torch.cuda.is_available() else None}))"
    for exe in candidates(explicit or os.environ.get('DUELFORGE_PYTHON')):
        try:
            r=subprocess.run([str(exe),'-c',probe],capture_output=True,text=True,timeout=15)
            if r.returncode:continue
            d=json.loads(r.stdout.strip().splitlines()[-1])
            if not d['python'].startswith('3.11.') or d['bits']!=64:continue
            choices.append((exe,d))
            if d['cuda']:selected=(exe,d);break
        except (OSError,ValueError,subprocess.TimeoutExpired):continue
    selected=selected or (choices[0] if choices else None)
    if selected is None:raise RuntimeError('No existing 64-bit Python 3.11 with Torch/NumPy found. Pass --python E:/.../python.exe; no packages were installed.')
    exe,d=selected
    print('DUELFORGE_PYTHON:',exe,'DEVICE:','cuda' if d['cuda'] else 'cpu','GPU:',d['gpu'],flush=True)
    subprocess.run([str(exe),str(ROOT/'run.py'),'verify'],cwd=ROOT,check=True)
    (ROOT/'runtime_python.txt').write_text(str(exe.resolve())+'\n',encoding='utf8')
    (ROOT/'runtime_selection.json').write_text(json.dumps({'selected':str(exe),'runtime':d,'scope':'Existing runtime reused; no libraries moved or installed'},indent=2))
    print('SETUP_PASS: verification passed. Open DUELFORGE.bat and choose 1. No training was started.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--python');a=p.parse_args();setup(a.python)
