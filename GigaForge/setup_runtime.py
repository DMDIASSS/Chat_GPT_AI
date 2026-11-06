"""Reuse working heavy libraries; isolate repairs; verify before selecting a runtime."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,shutil,tempfile,urllib.request,zipfile
from runtime_finder import inspect_runtimes,compatible_wheel,clean_env,probe,requirements
ROOT=Path(__file__).resolve().parent

def ensure_native():
 native=ROOT/'native/GigaForge.exe'
 if native.exists():return
 lock=ROOT/'native_release.json'
 if not lock.exists():raise RuntimeError('Native release metadata missing. Keep this patch beside the existing native folder.')
 spec=json.loads(lock.read_text(encoding='utf8'));url=spec['url']
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

def create_env(base,target):
 python=target/'Scripts/python.exe'
 if not python.exists():subprocess.run([str(base),'-m','venv',str(target)],check=True,env=clean_env())
 return python

def add_donor_paths(target,sites):
 # A child venv does not inherit its parent venv. Append plain .pth paths;
 # locally installed fixes take precedence and the donor stays read-only.
 site=target/('Lib/site-packages' if os.name=='nt' else 'lib/python3.11/site-packages');site.mkdir(parents=True,exist_ok=True)
 paths=[str(Path(p).absolute()) for p in sites if Path(p).is_dir() and Path(p).name.lower()=='site-packages']
 if any('\n' in p or '\r' in p for p in paths):raise ValueError('Invalid site-packages path')
 (site/'gigaforge_reused.pth').write_text('\n'.join(paths)+'\n',encoding='utf8')
 return paths

def install_plan(report,cpu):
 """Choose an existing complete environment, a read-only donor, or a fresh install."""
 best=report['best'];mode='cpu' if cpu else 'cuda'
 if best and not best['missing']:return dict(kind='existing',python=best['python'],mode=mode)
 if best:return dict(kind='overlay',python=best['python'],sites=best['sites'],mode=mode)
 wheels=[p for p in report['wheels'] if compatible_wheel(p,mode)]
 return dict(kind='wheel' if wheels else 'download',wheel=wheels[0] if wheels else None,mode=mode)

def setup(cpu=False):
 if sys.version_info[:2]!=(3,11):raise RuntimeError('Use Python 3.11 for the pinned native runtime')
 if os.name!='nt':raise RuntimeError('One-click discovery/setup targets Windows. Source builds on Linux remain available.')
 from runtime_bootstrap import nova_path,save_selection
 nova=nova_path();mode='cpu' if cpu else 'cuda'
 print('Looking for existing Python 3.11 / PyTorch 2.9.1 libraries first...',flush=True)
 report=inspect_runtimes(nova,mode,ROOT)
 (ROOT/'dependency_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 plan=install_plan(report,cpu)
 if plan['kind']=='existing':
  python=Path(plan['python']);print('REUSING_COMPLETE_RUNTIME:',python,'No packages will be installed.',flush=True)
 elif plan['kind']=='overlay':
  target=ROOT/('.venv_reused_'+mode);python=create_env(plan['python'],target)
  paths=add_donor_paths(target,plan['sites'])
  print('REUSING_TORCH_FROM:',plan['python'],'Repairing missing packages in',target,flush=True)
  (target/'gigaforge_donor.json').write_text(json.dumps(dict(python=plan['python'],sites=paths),indent=2),encoding='utf8')
 else:
  target=ROOT/('.venv_managed_'+mode);python=create_env(sys.executable,target)
  if plan['kind']=='wheel':
   print('REUSING_LOCAL_TORCH_WHEEL:',plan['wheel'],flush=True)
   subprocess.run([str(python),'-m','pip','install',plan['wheel']],check=True,env=clean_env())
  else:
   index='https://download.pytorch.org/whl/cpu' if cpu else 'https://download.pytorch.org/whl/cu126'
   print('No compatible installed Torch or local wheel found. pip will reuse its normal download cache when possible.',flush=True)
   subprocess.run([str(python),'-m','pip','install','torch==2.9.1+'+('cpu' if cpu else 'cu126'),'--index-url',index],check=True,env=clean_env())
 if plan['kind']!='existing':
  # Reused Torch satisfies the pinned requirement: do not request a new wheel.
  subprocess.run([str(python),'-m','pip','install','-r',str(nova/'requirements.txt'),'-r',str(nova/'requirements-wandb.txt')],check=True,env=clean_env())
 check=probe(python,requirements(nova),mode)
 if not check['compatible'] or check.get('missing'):raise RuntimeError('Runtime check failed: '+str(check.get('reason') or check.get('missing')))
 ensure_native()
 subprocess.run([str(python),'-u',str(ROOT/'run.py'),'verify','--device',mode],cwd=ROOT,check=True,env=clean_env())
 save_selection(python,mode,plan['kind'])
 print('NATIVE_SETUP_PASS: compatible runtime selected. Next: 2_BENCHMARK then 3_START_OR_RESUME.',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cpu',action='store_true');args=p.parse_args();setup(cpu=args.cpu)
