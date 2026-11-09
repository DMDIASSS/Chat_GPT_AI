"""All BAT files use the same saved interpreter. No third-party imports here."""
from pathlib import Path
import argparse,json,os,subprocess,sys
from runtime_finder import clean_env,inspect_runtimes
ROOT=Path(__file__).resolve().parent

def nova_path():
 for name in ('novaforge','NovaForge'):
  p=ROOT.parent/name
  if (p/'requirements.txt').is_file():return p
 raise FileNotFoundError('Keep gigaforge beside your existing novaforge folder')

def save_selection(python,mode,source):
 path=ROOT/'runtime_selection.json';temp=path.with_suffix('.tmp')
 temp.write_text(json.dumps(dict(python=str(Path(python).absolute()),device=mode,source=source),indent=2),encoding='utf8');temp.replace(path)

def selected_python():
 path=ROOT/'runtime_selection.json'
 if path.exists():
  data=json.loads(path.read_text(encoding='utf8'))
  if Path(data['python']).is_file():return data
  print('Saved Python moved. Searching for an existing working runtime.',flush=True)
 report=inspect_runtimes(nova_path(),mode='cpu',project=ROOT)
 if not report['best']:
  raise RuntimeError('No compatible runtime found. Run 1_SETUP_GPU.bat or 0_SETUP_CPU.bat; these now reuse existing libraries first.')
 r=report['best']
 # Do not silently run an online trainer against an incompatible dashboard SDK.
 if r['missing']:raise RuntimeError('Found reusable PyTorch. Run 1_SETUP_GPU.bat / 0_SETUP_CPU.bat once to repair only missing packages.')
 mode='cuda' if r['cuda'] else 'cpu';save_selection(r['python'],mode,'automatically found existing environment')
 return json.loads(path.read_text(encoding='utf8'))

def run_command(args):
 data=selected_python();python=data['python'];args=list(args)
 if not any(a=='--device' or a.startswith('--device=') for a in args):args.extend(['--device',data['device']])
 print('GIGAFORGE_PYTHON:',python,'Device:',data['device'],flush=True)
 return subprocess.call([python,'-u',str(ROOT/'run.py'),*args],cwd=ROOT,env=clean_env())

def find(mode):
 report=inspect_runtimes(nova_path(),mode,ROOT)
 path=ROOT/'dependency_report.json';path.write_text(json.dumps(report,indent=2),encoding='utf8')
 print('DEPENDENCY_REPORT:',path,flush=True)
 for p in report['cuda_toolkits']:print('CUDA toolkit found:',p)
 for p in report['wheels']:print('Local torch wheel:',p)
 print('Best reusable Python:',report['best']['python'] if report['best'] else 'none; installer will check local wheels and normal pip cache')
 print('Nothing was installed or deleted. CPU mode can reuse a working CUDA wheel.')

def repair_wandb():
 data=selected_or_existing()
 # Repair only GigaForge-owned environments; otherwise setup makes an overlay.
 python=Path(data['python'])
 if not python.is_relative_to(ROOT):
  from setup_runtime import setup
  setup(cpu=data['device']=='cpu');python=Path(selected_python()['python'])
 else:
  subprocess.run([str(python),'-m','pip','install','--upgrade','-r',str(nova_path()/'requirements-wandb.txt')],check=True,env=clean_env())
 code='import sys;sys.path.insert(0,'+repr(str(nova_path()))+');from nova.tracking import check_login;check_login()'
 return subprocess.call([str(python),'-c',code],env=clean_env())

def selected_or_existing():
 p=ROOT/'runtime_selection.json'
 if p.exists():return json.loads(p.read_text(encoding='utf8'))
 # W&B repair must also work before the old SDK can pass preflight.
 for p in (ROOT/'.venv_native/Scripts/python.exe',nova_path()/'.venv/Scripts/python.exe'):
  if p.is_file():return dict(python=str(p),device='cuda')
 return selected_python()

if __name__=='__main__':
 command,*args=sys.argv[1:]
 if command=='setup':
  from setup_runtime import setup
  setup(cpu='--cpu' in args)
 elif command=='find':find('cpu' if '--cpu' in args else 'cuda')
 elif command=='native-check':
  data=selected_or_existing()
  raise SystemExit(subprocess.call([data['python'],'-u',str(ROOT/'native_access.py'),'--repair'],cwd=ROOT,env=clean_env()))
 elif command=='repair-wandb':raise SystemExit(repair_wandb())
 elif command=='pilot':
  data=selected_python();args=list(args)
  if not any(a=='--device' or a.startswith('--device=') for a in args):args.extend(['--device',data['device']])
  print('GIGAFORGE_PYTHON:',data['python'],'Device:',data['device'],flush=True)
  raise SystemExit(subprocess.call([data['python'],'-u',str(ROOT/'stationary_pilot.py'),*args],cwd=ROOT,env=clean_env()))
 elif command=='run':raise SystemExit(run_command(args))
 else:raise ValueError('Unknown bootstrap command: '+command)
