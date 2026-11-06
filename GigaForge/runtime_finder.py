"""Bounded local discovery of compatible Python/PyTorch runtimes. Stdlib only."""
from __future__ import annotations
import collections,ctypes,importlib.metadata,json,os,re,shutil,struct,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SKIP={'.git','node_modules','assets','runs','exports','reports','views','vendor','build','__pycache__','lib','lib64','site-packages','include','collision_meshes','windows','$recycle.bin','system volume information','wandb'}
MARK='GIGAFORGE_PROBE_JSON='

def clean_env():
 env=dict(os.environ)
 for key in ('PYTHONHOME','PYTHONPATH'):env.pop(key,None)
 return env

def requirements(nova):
 pins={}
 for name in ('requirements.txt','requirements-wandb.txt'):
  for line in (Path(nova)/name).read_text(encoding='utf8').splitlines():
   match=re.match(r'^([\w.-]+)(?:\[[^]]+\])?==([^\s;]+)',line)
   if match:pins[match[1]]=match[2]
 return pins

def likely_roots(project=ROOT):
 home=Path.home();roots=[Path(project).parent]
 roots.extend(Path(p).expanduser() for p in os.environ.get('GIGAFORGE_SEARCH_ROOTS','').split(os.pathsep) if p)
 roots.extend(home/name for name in ('Downloads','Desktop','Documents','Projects','projects','dev','work','.virtualenvs','Envs','miniconda3','anaconda3','.conda/envs'))
 local=os.environ.get('LOCALAPPDATA')
 if local:roots += [Path(local)/'Programs/Python',Path(local)/'uv/python']
 if os.name=='nt':
  mask=ctypes.windll.kernel32.GetLogicalDrives()
  for i in range(26):
   drive=Path(chr(65+i)+':/')
   if mask&(1<<i) and ctypes.windll.kernel32.GetDriveTypeW(str(drive))==3:
    roots.extend(drive/name for name in ('Downloads','Chat_GPT_AI','Projects','AI','GigaLearn'))
  for var in ('ProgramFiles','ProgramFiles(x86)'):
   if os.environ.get(var):roots.append(Path(os.environ[var])/'NVIDIA GPU Computing Toolkit/CUDA')
 seen=set();answer=[]
 for p in roots:
  key=os.path.normcase(str(p.absolute()))
  if key not in seen and p.is_dir():seen.add(key);answer.append(p)
 return answer

def discover(project=ROOT,*,roots=None,max_dirs=4000,max_seconds=8):
 """No drive-wide walk; inspect likely locations, environment markers and wheel names."""
 candidates=[];wheels=[];toolkits=[];seen=set();visited=set()
 def add(p):
  p=Path(p).absolute();key=os.path.normcase(str(p))
  if key not in seen and p.is_file():seen.add(key);candidates.append(str(p))
 for p in (os.environ.get('GIGAFORGE_PYTHON'),sys.executable,shutil.which('python'),shutil.which('python3.11')):
  if p:add(p)
 for var in ('VIRTUAL_ENV','CONDA_PREFIX'):
  if os.environ.get(var):
   for name in ('Scripts/python.exe','python.exe','bin/python'):add(Path(os.environ[var])/name)
 if os.name=='nt':
  import winreg
  for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
   try:
    with winreg.OpenKey(hive,r'SOFTWARE\Python\PythonCore') as key:
     for i in range(winreg.QueryInfoKey(key)[0]):
      try:
       with winreg.OpenKey(key,winreg.EnumKey(key,i)+r'\InstallPath') as install:
        add(Path(winreg.QueryValueEx(install,'')[0])/'python.exe')
      except OSError:pass
   except OSError:pass
  py=shutil.which('py')
  if py:
   try:
    r=subprocess.run([py,'-0p'],capture_output=True,text=True,timeout=5,env=clean_env())
    for path in re.findall(r'([A-Za-z]:\\[^\r\n]*python\.exe)',r.stdout+r.stderr):add(path.strip().strip('"'))
   except (OSError,subprocess.TimeoutExpired):pass
 roots=likely_roots(project) if roots is None else list(map(Path,roots))
 # Common environments first; scanning below still finds nested GigaLearn projects.
 for root in roots:
  for name in ('.venv_native','.venv_reused_cpu','.venv_reused_cuda','.venv_managed_cpu','.venv_managed_cuda','.venv','venv','novaforge/.venv','NovaForge/.venv'):
   for exe in ('Scripts/python.exe','bin/python'):add(root/name/exe)
 queue=collections.deque((p,0) for p in roots);started=time.monotonic();count=0
 while queue and count<max_dirs and time.monotonic()-started<max_seconds:
  directory,depth=queue.popleft();key=os.path.normcase(str(directory.absolute()))
  if key in visited:continue
  visited.add(key);count+=1
  try:
   entries=list(os.scandir(directory))
  except OSError:continue
  names={e.name.lower():e for e in entries}
  if 'pyvenv.cfg' in names or 'conda-meta' in names or directory.name.lower().startswith('python'):
   for exe in ('Scripts/python.exe','python.exe','bin/python'):add(directory/exe)
  if 'nvcc.exe' in names or (directory/'bin/nvcc.exe').is_file():toolkits.append(str(directory))
  for e in entries:
   try:
    if e.is_file(follow_symlinks=False) and e.name.lower().startswith('torch-2.9.1') and e.name.lower().endswith('.whl'):wheels.append(e.path)
    if depth<5 and e.name.lower() not in SKIP and e.is_dir(follow_symlinks=False):
     # Avoid Windows junctions, network redirects and repeated directory trees.
     if getattr(e.stat(follow_symlinks=False),'st_file_attributes',0)&0x400:continue
     queue.append((Path(e.path),depth+1))
   except OSError:continue
 return dict(candidates=candidates,wheels=sorted(set(wheels)),cuda_toolkits=sorted(set(toolkits)),directories_scanned=count,scan_limited=bool(queue))

META_CODE=r'''
import sys,json,struct,importlib.metadata as m,site
pins=json.loads(sys.argv[1]);versions={}
for name in list(pins)+['filelock']:
 try:versions[name]=m.version(name)
 except m.PackageNotFoundError:versions[name]=None
print('GIGAFORGE_PROBE_JSON='+json.dumps(dict(python=sys.executable,version=list(sys.version_info[:3]),bits=struct.calcsize('P')*8,packages=versions,sites=site.getsitepackages())))
'''
TORCH_CODE=r'''
import json,torch,sys
cuda=bool(torch.cuda.is_available());x=torch.ones(2,device='cuda' if sys.argv[1]=='cuda' else 'cpu');y=(x+x).sum().item()
print('GIGAFORGE_PROBE_JSON='+json.dumps(dict(torch=torch.__version__,cuda=cuda,torch_cuda=torch.version.cuda,torch_path=torch.__file__,gpu=torch.cuda.get_device_name(0) if cuda else None,tensor_check=y==4)))
'''

def child_json(python,code,args=(),timeout=30):
 r=subprocess.run([str(python),'-I','-c',code,*map(str,args)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=timeout,env=clean_env())
 if r.returncode:raise RuntimeError('Python/package probe failed (exit '+str(r.returncode)+')')
 lines=[line[len(MARK):] for line in r.stdout.splitlines() if line.startswith(MARK)]
 if not lines:raise RuntimeError('Python probe returned no result')
 return json.loads(lines[-1])

def probe(python,pins,mode='cuda'):
 result=dict(python=str(python),compatible=False)
 try:
  info=child_json(python,META_CODE,[json.dumps(pins)],timeout=12);result.update(info)
  if info['version'][:2]!=[3,11] or info['bits']!=64:raise ValueError('Requires Python 3.11 x64')
  if (info['packages'].get('torch') or '').split('+')[0]!='2.9.1':raise ValueError('Requires PyTorch 2.9.1 for the native ABI')
  result['missing']=[name for name,v in pins.items() if (info['packages'].get(name) or '').split('+')[0]!=v]
  filelock=(info['packages'].get('filelock') or '').split('.')
  if len(filelock)<2 or not (3,20)<=tuple(int(x) for x in filelock[:2])<(4,0):result['missing'].append('filelock')
  result.update(child_json(python,TORCH_CODE,[mode],timeout=60))
  result['compatible']=result['tensor_check'] and (mode=='cpu' or result['cuda'])
 except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
  result['reason']=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__
 return result

def inspect_runtimes(nova,mode='cuda',project=ROOT,**scan):
 pins=requirements(nova);found=discover(project,**scan);rows=[]
 for path in found['candidates']:
  print('Checking Python:',path,flush=True)
  r=probe(path,pins,mode);rows.append(r)
  if r['compatible']:print('  Reusable PyTorch',r['torch'],'; missing packages:',','.join(r['missing']) or 'none',flush=True)
  else:print('  Skipped:',r.get('reason','Requested CUDA device is not usable'),flush=True)
 found['runtimes']=rows;found['mode']=mode
 compatible=[r for r in rows if r['compatible']]
 compatible.sort(key=lambda r:(len(r['missing']),0 if Path(r['python']).parent.parent==Path(project) / '.venv_native' else 1))
 found['best']=compatible[0] if compatible else None
 return found

def compatible_wheel(path,mode):
 # Filename is not enough: verify the pinned metadata, Python ABI and platform.
 import zipfile
 try:
  with zipfile.ZipFile(path) as z:
   meta=next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))
   wheel=next(n for n in z.namelist() if n.endswith('.dist-info/WHEEL'))
   version=re.search(r'^Version: (.+)$',z.read(meta).decode(),re.M).group(1).strip()
   tags=z.read(wheel).decode()
   return version.split('+')[0]=='2.9.1' and 'cp311-cp311-win_amd64' in tags and (mode=='cpu' or '+cu' in version)
 except (OSError,ValueError,StopIteration,KeyError,zipfile.BadZipFile,AttributeError):return False
