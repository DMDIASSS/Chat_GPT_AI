"""Publish a Windows-tested pilot update; no private models or historical runs."""
from pathlib import Path
import hashlib,json,os,sys,zipfile
root=Path.cwd();gf=root/'GigaForge';native=root/'verified-native';out=root/'downloads';out.mkdir(exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((native/'build.json').read_text(encoding='utf8'))
assert sha((native/'GigaForge.exe').read_bytes())==build['executable_sha256']
assert build['patch_sha256']==sha((gf/'tools/patch_upstream.py').read_bytes())
for name,digest in build['app_source_sha256'].items():assert sha((gf/name).read_bytes())==digest
run=int(os.environ['GITHUB_RUN_ID'])
validation=dict(source_commit=os.environ['GITHUB_SHA'],verified_workflow=run,
 evaluation_protocol='arena-rng-v4',head_to_head_protocol='direct-h2h-v1',stationary_protocol='stationary-pilot-v1',
 cuda_hardware_verified=False,playing_strength_verified=False,
 scope='Windows native feature/action parity, actual updates/resume, fixed-rollout accounting, full identical-model matches, stationary reward/counter regression, exact cached evaluations, paused-study isolation, export logits and real runtime BAT routing. CPU/public-model fixtures only. No live RLBot game claim.')
(native/'stationary_validation.json').write_text(json.dumps(validation,indent=2))
sys.path.insert(0,str(gf/'tools'));import build_native
vendor=build_native.prepare();packed={}
for p in native.rglob('*'):
 if p.is_file():packed['native/'+p.relative_to(native).as_posix()]=p.read_bytes()
for p in vendor.rglob('*'):
 if p.is_file() and p.name.lower().startswith(('license','copying','notice')):packed['native/notices/'+p.relative_to(vendor).as_posix()]=p.read_bytes()
packed['native/ATTRIBUTION.txt']=('GigaLearnCPP/RLGymCPP/RocketSim by ZealanL and contributors, pinned '+build_native.COMMIT+'. Stationary pilot and verification by NovaForge. PyTorch 2.9.1 runtime installed separately. No teacher weights bundled.\n').encode()
temp=out/'_stationary_native.zip'
with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(packed.items()):z.writestr(n,b)
digest=sha(temp.read_bytes());bundle=temp.with_name('GigaForge-native-stationary-'+digest[:12]+'.zip');temp.rename(bundle)
release_meta=dict(url='https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/'+bundle.name,
 sha256=digest,executable_sha256=build['executable_sha256'],verified_workflow=run,package_workflow=run,
 research_protocol='fixed-rollout-v1',evaluation_protocol='arena-rng-v4',head_to_head_protocol='direct-h2h-v1',stationary_protocol='stationary-pilot-v1',cuda_hardware_verified=False)
(gf/'native_release.json').write_text(json.dumps(release_meta,indent=2))
names=['stationary_pilot.py','stationary_jobs.py','runtime_bootstrap.py','_RUN.bat','STATIONARY_PILOT.md','CMakeLists.txt',
 'tools/build_native.py','tools/patch_upstream.py','tests/test_stationary_jobs.py','tests/check_stationary_pilot.py','tests/check_stationary_contract.py']
names += [p.relative_to(gf).as_posix() for p in (gf/'src').glob('*') if p.is_file()]
names += [p.name for p in gf.glob('*STATIONARY*.bat')]
project={};prefix='chat_gpt_ai/gigaforge/'
for name in names:
 b=(gf/name).read_bytes()
 if name.endswith('.bat'):b=b.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
 project[prefix+name]=b
for n,b in packed.items():project[prefix+n]=b
project[prefix+'native_release.json']=(gf/'native_release.json').read_bytes()
project['chat_gpt_ai/START_STATIONARY_PILOT.txt']=b'Close trainers/viewers. Merge this folder into Chat_GPT_AI, including gigaforge/native. Keep runs/environments. Run gigaforge/9_VERIFY.bat then 36_START_STATIONARY_PILOT.bat. This creates/resumes stationary01 only, with a 30-minute invocation budget. Use 37 to pause, 38 to watch the completed preview, 39 to report, 40 to export. Do not use 3 or 17 for this pilot. No stronger model is bundled or claimed. See gigaforge/STATIONARY_PILOT.md.\r\n'
project[prefix+'STATIONARY_MANIFEST.sha256']=''.join(sha(b)+'  '+n[len(prefix):]+'\n' for n,b in sorted(project.items()) if n.startswith(prefix)).encode()
archive=out/'GigaForge-Stationary-Pilot-Update.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(project.items()):z.writestr(n,b)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for line in z.read(prefix+'STATIONARY_MANIFEST.sha256').decode().splitlines():
  h,n=line.split('  ',1);assert sha(z.read(prefix+n))==h
record=dict(validation,executable_sha256=build['executable_sha256'],update=dict(path=archive.name,bytes=archive.stat().st_size,sha256=sha(archive.read_bytes())),
 reward_evidence=dict(blue_goals_in_native_regression=100,legacy_reported_win_rate=.5),
 changes=['Reject invalid legacy winrate objective','Stationary goal-only vs bounded PBRS matched controls','GPU minibatch 256 without removing epochs/samples','Identity checked caches and signed seed guards','Separate resumable study and fixed final test'])
(root/'research/GigaForge-stationary-pilot-release.json').write_text(json.dumps(record,indent=2))
(root/'GIGAFORGE_STATIONARY_DOWNLOAD.md').write_text('# Stationary Chronos pilot\n\n[Download update](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-Stationary-Pilot-Update.zip)\n\nMerge into Chat_GPT_AI including native, keep runs/environments. Verify, then run 36_START_STATIONARY_PILOT. Use 37 to pause, 38 to watch after completion, 39 to report and 40 to export. This is a new stationary01 experiment, not a proven stronger model. [Exact protocol](GigaForge/STATIONARY_PILOT.md).\n',encoding='utf8')
print('STATIONARY_RELEASE',json.dumps(record))
