"""Reproducible source build. Prebuilt Windows packages do not need a compiler."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tarfile,tempfile,urllib.request
ROOT=Path(__file__).resolve().parents[1]
COMMIT='86e11c3881a21225a43c36b14af40f0b3c87e7dd'
ARCHIVE_SHA256='3d78d9c8a3835074277f828ad14471b92b40fd3d714d4666d27dc59ea43422fb'
URL='https://codeload.github.com/ZealanL/GigaLearnCPP-Leak/tar.gz/'+COMMIT

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def prepare(archive=None):
 cache=ROOT/'cache';cache.mkdir(exist_ok=True)
 archive=Path(archive) if archive else cache/'gigalearn.tar.gz'
 if not archive.exists():
  with urllib.request.urlopen(URL,timeout=120) as response,archive.open('wb') as out:
   shutil.copyfileobj(response,out)
 if sha(archive)!=ARCHIVE_SHA256:raise ValueError('Pinned GigaLearn archive hash mismatch')
 vendor=ROOT/'vendor';stamp=vendor/'gigaforge-patch.json'
 expected=dict(upstream=COMMIT,archive_sha256=ARCHIVE_SHA256,patch_sha256=sha(Path(__file__).with_name('patch_upstream.py')))
 if stamp.exists() and json.loads(stamp.read_text())==expected:return vendor
 if vendor.exists():shutil.rmtree(vendor)
 with tempfile.TemporaryDirectory(dir=cache) as temp:
  temp=Path(temp)
  with tarfile.open(archive,'r:gz') as tar:
   for entry in tar.getmembers():
    destination=(temp/entry.name).resolve()
    if not destination.is_relative_to(temp.resolve()) or entry.issym() or entry.islnk():raise ValueError('Unsafe archive entry')
   tar.extractall(temp,filter='data')
  source=next(p for p in temp.iterdir() if p.is_dir());shutil.move(str(source),vendor)
 from patch_upstream import patch
 patch(vendor);stamp.write_text(json.dumps(expected,indent=2))
 return vendor

def build(archive=None):
 import torch
 if torch.__version__.split('+')[0]!='2.9.1':raise RuntimeError('Native build expects PyTorch 2.9.1')
 vendor=prepare(archive)
 tools=ROOT/'tools/runtime'
 cmake=shutil.which('cmake');ninja=shutil.which('ninja')
 if not cmake or not ninja:
  tools.mkdir(exist_ok=True)
  subprocess.run([sys.executable,'-m','pip','install','--target',str(tools),'cmake==3.31.6','ninja==1.11.1.4'],check=True)
  cmake=str(tools/'cmake/data/bin'/('cmake.exe' if os.name=='nt' else 'cmake'))
  ninja=next((p for p in (tools/'bin/ninja',tools/'Scripts/ninja.exe',tools/'bin/ninja.exe',tools/'ninja/data/bin/ninja.exe') if p.exists()),None)
  if ninja is None:raise FileNotFoundError('Ninja installation was not found')
 env=dict(os.environ)
 if os.name=='nt' and not shutil.which('cl'):
  vswhere=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
  if not vswhere.exists():raise RuntimeError('Source build requires Visual Studio 2022 C++ Build Tools. Use the prebuilt native package, or install Microsoft.VisualStudio.2022.BuildTools with VCTools.')
  result=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
  vcvars=Path(result)/'VC/Auxiliary/Build/vcvars64.bat'
  output=subprocess.check_output('cmd.exe /d /s /c ""'+str(vcvars)+'" >nul && set"',text=True)
  for line in output.splitlines():
   if '=' in line:
    key,value=line.split('=',1);env[key]=value
 build_dir=ROOT/'build'
 cmd=[str(cmake),'-S',str(ROOT),'-B',str(build_dir),'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
  '-DCMAKE_MAKE_PROGRAM='+str(ninja),'-DGGL_VENDOR='+str(vendor),'-DCMAKE_PREFIX_PATH='+torch.utils.cmake_prefix_path,
  '-DPython_EXECUTABLE='+sys.executable,'-DPYBIND11_FINDPYTHON=ON']
 subprocess.run(cmd,env=env,check=True)
 subprocess.run([str(cmake),'--build',str(build_dir),'--parallel','2'],env=env,check=True)
 native=ROOT/'native';native.mkdir(exist_ok=True)
 executable=build_dir/('GigaForge.exe' if os.name=='nt' else 'GigaForge')
 shutil.copy2(executable,native/executable.name)
 # Do not copy CPU torch DLLs beside the executable: the selected runtime's
 # matching CPU/CUDA wheel must supply them via PATH.
 (native/'build.json').write_text(json.dumps(dict(source=COMMIT,torch=torch.__version__,python=sys.version,executable_sha256=sha(native/executable.name)),indent=2))
 print('NATIVE_BUILD_READY:',native/executable.name)
 return native
if __name__=='__main__':build(sys.argv[1] if len(sys.argv)>1 else None)
