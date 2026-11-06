"""Isolated Windows runtime; keeps the existing NovaForge environment intact."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,urllib.request,zipfile
ROOT=Path(__file__).resolve().parent

def setup(cpu=False):
 if os.name!='nt':raise RuntimeError('The one-click runtime is for Windows. Linux: use tools/build_native.py with the existing Python environment.')
 native=ROOT/'native/GigaForge.exe'
 if not native.exists():
  lock=ROOT/'native_release.json'
  if not lock.exists():raise RuntimeError('Prebuilt native release metadata missing. Source build: python tools/build_native.py')
  spec=json.loads(lock.read_text());url=spec['url']
  if not url.startswith('https://github.com/DMDIASSS/Chat_GPT_AI/raw/'):raise ValueError('Unapproved native archive location')
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'native.zip'
   with urllib.request.urlopen(url,timeout=120) as response,path.open('wb') as f:shutil.copyfileobj(response,f)
   if hashlib.sha256(path.read_bytes()).hexdigest()!=spec['sha256']:raise ValueError('Native archive hash mismatch')
   with zipfile.ZipFile(path) as z:
    for name in z.namelist():
     target=(ROOT/name).resolve()
     if not target.is_relative_to(ROOT.resolve()) or not name.startswith('native/'):raise ValueError('Unsafe native archive path')
    z.extractall(ROOT)
 env=ROOT/'.venv_native';python=env/'Scripts/python.exe'
 if not python.exists():subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
 cuda=False
 if not cpu:
  smi=shutil.which('nvidia-smi')
  if not smi:raise RuntimeError('NVIDIA driver tools were not found. Install/update your NVIDIA driver, or run 0_SETUP_CPU.bat for CPU mode.')
  subprocess.run([smi,'--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],check=True)
  cuda=True
 index='https://download.pytorch.org/whl/cu126' if cuda else 'https://download.pytorch.org/whl/cpu'
 subprocess.run([str(python),'-m','pip','install','--upgrade','torch==2.9.1+'+('cu126' if cuda else 'cpu'),'--index-url',index],check=True)
 nova=ROOT.parent/'novaforge'
 if not nova.exists():nova=ROOT.parent/'NovaForge'
 subprocess.run([str(python),'-m','pip','install','-r',str(nova/'requirements.txt'),'wandb>=0.23,<0.25'],check=True)
 result=subprocess.run([str(python),'-c','import torch; print("Torch",torch.__version__); print("CUDA",torch.cuda.is_available()); print("GPU",torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"); raise SystemExit(0 if '+('torch.cuda.is_available()' if cuda else 'True')+' else 1)'],check=True)
 subprocess.run([str(python),'-u',str(ROOT/'run.py'),'verify','--device','cuda' if cuda else 'cpu'],cwd=ROOT,check=True)
 print('NATIVE_SETUP_PASS: run 2_BENCHMARK then 3_START_OR_RESUME. Existing NovaForge/ForgeLeague runs were not modified.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cpu',action='store_true');a=p.parse_args();setup(a.cpu)
