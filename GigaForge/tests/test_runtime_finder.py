"""Compatibility, bounded discovery, interpreter routing and read-only donor reuse."""
import importlib.util,json,os,sys,subprocess,zipfile,hashlib
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import runtime_finder as f
import setup_runtime as s
import runtime_bootstrap as b


def test_bounded_discovery_finds_nested_environments_skips_model_folders(tmp_path):
 project=tmp_path/'Chat GPT AI';env=project/'GigaLearn_Project/trainer/.venv'
 env.mkdir(parents=True);(env/'pyvenv.cfg').touch();(env/'Scripts').mkdir();(env/'Scripts/python.exe').touch()
 ignored=project/'runs/huge/.venv';ignored.mkdir(parents=True);(ignored/'pyvenv.cfg').touch();(ignored/'Scripts').mkdir();(ignored/'Scripts/python.exe').touch()
 wheel=project/'torch-2.9.1+cu126-cp311-cp311-win_amd64.whl';wheel.touch()
 report=f.discover(project,roots=[project],max_dirs=100,max_seconds=10)
 assert str(env/'Scripts/python.exe') in report['candidates']
 assert str(ignored/'Scripts/python.exe') not in report['candidates']
 assert str(wheel) in report['wheels']
 assert report['directories_scanned']<=100
 assert f.discover(project,roots=[project],max_dirs=1)['scan_limited']


def test_rejects_native_abi_mismatch_before_loading_torch(monkeypatch):
 calls=[]
 def child(*args,**kwargs):
  calls.append(args);return dict(version=[3,11,0],bits=64,packages={'torch':'2.8.0'})
 monkeypatch.setattr(f,'child_json',child)
 r=f.probe('python',{'torch':'2.9.1'})
 assert not r['compatible'] and 'ABI' in r['reason'] and len(calls)==1


def test_missing_wandb_detected_without_discarding_compatible_heavy_torch(monkeypatch):
 results=iter([dict(version=[3,11,9],bits=64,packages={'torch':'2.9.1+cu126','wandb':'0.24.0','filelock':'3.20.0'},sites=['/existing/site-packages']),dict(torch='2.9.1+cu126',cuda=True,tensor_check=True)])
 monkeypatch.setattr(f,'child_json',lambda *a,**k:next(results))
 r=f.probe('python',{'torch':'2.9.1','wandb':'0.31.0'})
 assert r['compatible'] and r['missing']==['wandb']
 plan=s.install_plan(dict(best=r,wheels=[]),False)
 assert plan['kind']=='overlay' and 'wheel' not in plan
 r['missing']=[]
 assert s.install_plan(dict(best=r,wheels=[]),False)['kind']=='existing'


def test_cpu_can_reuse_cuda_wheel_but_gpu_requires_actual_tensor_probe(monkeypatch):
 def child(python,code,args=(),**kwargs):
  if code==f.META_CODE:return dict(version=[3,11,9],bits=64,packages={'torch':'2.9.1+cu126','filelock':'3.20.0'},sites=[])
  if args==['cuda']:raise RuntimeError('Python/package probe failed')
  return dict(torch='2.9.1+cu126',cuda=False,tensor_check=True)
 monkeypatch.setattr(f,'child_json',child)
 assert f.probe('python',{'torch':'2.9.1'},'cpu')['compatible']
 assert not f.probe('python',{'torch':'2.9.1'},'cuda')['compatible']


def test_wheel_metadata_and_abi_are_checked(tmp_path):
 def wheel(name,version,tag):
  p=tmp_path/name
  with zipfile.ZipFile(p,'w') as z:
   z.writestr('torch-2.9.1.dist-info/METADATA','Name: torch\nVersion: '+version+'\n')
   z.writestr('torch-2.9.1.dist-info/WHEEL','Tag: '+tag+'\n')
  return p
 valid=wheel('valid.whl','2.9.1+cu126','cp311-cp311-win_amd64')
 assert f.compatible_wheel(valid,'cuda')
 assert not f.compatible_wheel(wheel('renamed.whl','2.8.0+cu126','cp311-cp311-win_amd64'),'cuda')
 assert not f.compatible_wheel(wheel('wrong-python.whl','2.9.1+cu126','cp312-cp312-win_amd64'),'cuda')
 assert not f.compatible_wheel(wheel('cpu.whl','2.9.1+cpu','cp311-cp311-win_amd64'),'cuda')


def test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin():
 root=Path(s.__file__).parent
 for p in root.glob('*.bat'):
  if p.name in ('_RUN.bat','COLLECT_SOURCE_AND_RESULTS.bat'):continue # stdlib-only collector needs no ML runtime
  text=p.read_text();assert '_RUN.bat' in text and '.venv_native\\Scripts' not in text
 assert 'wandb>=0.23' not in Path(s.__file__).read_text()


def test_selected_python_is_used_for_training_and_explicit_device_preserved(tmp_path,monkeypatch):
 monkeypatch.setattr(b,'ROOT',tmp_path)
 python=tmp_path/'python.exe';python.touch();b.save_selection(python,'cuda','test')
 captured=[];monkeypatch.setattr(b.subprocess,'call',lambda args,**kwargs:captured.append(args) or 0)
 b.run_command(['train','--device=cpu']);assert captured[0][0]==str(python) and '--device' not in captured[0]
 b.run_command(['train']);assert captured[1][-2:]==['--device','cuda']


def test_real_overlay_shadows_repair_without_modifying_donor(tmp_path):
 # Real Python/site/pip behavior, with a tiny local fixture wheel; no network.
 target=tmp_path/'local runtime';subprocess.run([sys.executable,'-m','venv',str(target)],check=True)
 python=target/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
 donor=tmp_path/'donor/site-packages';donor.mkdir(parents=True)
 name='gigaforge_fixture';file=donor/(name+'.py');file.write_text('VALUE=1\n')
 dist=donor/(name+'-1.0.dist-info');dist.mkdir();(dist/'METADATA').write_text('Metadata-Version: 2.1\nName: '+name+'\nVersion: 1.0\n')
 before=hashlib.sha256(file.read_bytes()).hexdigest()
 s.add_donor_paths(target,[str(donor)])
 def value():return subprocess.check_output([str(python),'-I','-c','import '+name+';print('+name+'.VALUE)'],text=True,env=f.clean_env()).strip()
 assert value()=='1'
 path=tmp_path/(name+'-2.0-py3-none-any.whl')
 with zipfile.ZipFile(path,'w') as z:
  z.writestr(name+'.py','VALUE=2\n')
  z.writestr(name+'-2.0.dist-info/METADATA','Metadata-Version: 2.1\nName: '+name+'\nVersion: 2.0\n')
  z.writestr(name+'-2.0.dist-info/WHEEL','Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
  z.writestr(name+'-2.0.dist-info/RECORD','')
 subprocess.run([str(python),'-m','pip','install','--no-index',str(path)],check=True,capture_output=True,text=True,env=f.clean_env())
 assert value()=='2' and hashlib.sha256(file.read_bytes()).hexdigest()==before
 assert (dist/'METADATA').is_file()


@pytest.mark.skipif(os.name!='nt',reason='Windows one-click setup')
@pytest.mark.parametrize('verify_fails',[False,True])
def test_complete_runtime_setup_never_installs_or_downloads_and_selects_only_after_verify(tmp_path,monkeypatch,verify_fails):
 root=tmp_path/'GigaForge';root.mkdir();nova=tmp_path/'novaforge';nova.mkdir()
 (nova/'requirements.txt').write_text('torch==2.9.1\n');(nova/'requirements-wandb.txt').write_text('wandb==0.31.0\n')
 monkeypatch.setattr(s,'ROOT',root);monkeypatch.setattr(b,'ROOT',root);monkeypatch.setattr(b,'nova_path',lambda:nova)
 existing=tmp_path/'existing/python.exe';existing.parent.mkdir();existing.touch()
 monkeypatch.setattr(s,'inspect_runtimes',lambda *a,**k:dict(best=dict(python=str(existing),missing=[])))
 monkeypatch.setattr(s,'probe',lambda *a,**k:dict(compatible=True,missing=[]))
 monkeypatch.setattr(s,'ensure_native',lambda:None)
 called=[]
 def invoke(args,**kwargs):
  called.append(args)
  if verify_fails:raise subprocess.CalledProcessError(1,args)
 monkeypatch.setattr(s.subprocess,'run',invoke)
 if verify_fails:
  with pytest.raises(subprocess.CalledProcessError):s.setup(cpu=False)
  assert not (root/'runtime_selection.json').exists()
 else:
  s.setup(cpu=False);assert json.loads((root/'runtime_selection.json').read_text())['python']==str(existing)
 assert len(called)==1 and 'verify' in called[0] and 'pip' not in called[0]
