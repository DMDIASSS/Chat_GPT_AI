"""Package the Windows-verified per-arena RNG repair, preserving all user runs."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,zipfile
root=Path.cwd();gf=root/'GigaForge';native=root/'verified-native';out=root/'downloads';out.mkdir(exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((native/'build.json').read_text(encoding='utf8'))
assert sha((native/'GigaForge.exe').read_bytes())==build['executable_sha256']
assert build['patch_sha256']==sha((gf/'tools/patch_upstream.py').read_bytes())
for name,digest in build['app_source_sha256'].items():assert sha((gf/name).read_bytes())==digest
verified=int(os.environ['NATIVE_VERIFIED_RUN']);workflow=int(os.environ['GITHUB_RUN_ID'])
validation=dict(source_commit=os.environ['GITHUB_SHA'],native_workflow=verified,package_workflow=workflow,
 evaluation_protocol='arena-rng-v4',cuda_hardware_verified=False,
 scope='Windows feature/action/network parity, real training/resume, all-sample accounting, statistical/pacing checks and identical-actor 60-second evaluation checks; not playing-strength evidence')
(native/'paired_validation.json').write_text(json.dumps(validation,indent=2))
sys.path.insert(0,str(gf/'tools'));import build_native
vendor=build_native.prepare();packed={}
for p in native.rglob('*'):
 if p.is_file():packed['native/'+p.relative_to(native).as_posix()]=p.read_bytes()
for p in vendor.rglob('*'):
 if p.is_file() and p.name.lower().startswith(('license','copying','notice')):packed['native/notices/'+p.relative_to(vendor).as_posix()]=p.read_bytes()
packed['native/ATTRIBUTION.txt']=('GigaLearnCPP/RLGymCPP/RocketSim by ZealanL and contributors. Pinned upstream '+build_native.COMMIT+'. Per-arena evaluation RNG repair and Python orchestration by NovaForge. Torch 2.9.1 is installed separately. No teacher weights bundled.\n').encode()
temp=out/'_paired_native.zip'
with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
 for name,data in sorted(packed.items()):z.writestr(name,data)
digest=sha(temp.read_bytes());bundle=temp.with_name('GigaForge-native-paired-'+digest[:12]+'.zip');temp.rename(bundle)
(gf/'native_release.json').write_text(json.dumps(dict(url='https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/'+bundle.name,
 sha256=digest,executable_sha256=build['executable_sha256'],verified_workflow=verified,package_workflow=workflow,
 research_protocol='fixed-rollout-v1',evaluation_protocol='arena-rng-v4',cuda_hardware_verified=False),indent=2))
p=gf/'README.md';text=p.read_text(encoding='utf8');text=text.replace('earlier runs, exports and the working fixed-rollout-v1 native binary.','earlier runs and exports. Install the NEW paired-evaluation native binary.');p.write_text(text+'\nCurrent update: [paired evaluation repair and automatic training focus](PAIRED_REPAIR.md). Existing research02: pause with 4, install this update, run 9_VERIFY, then 3 to resume the same checkpoints.\n',encoding='utf8')
p=gf/'VALIDATION_AUTONOMOUS.md';p.write_text('Current evaluator: [PAIRED_REPAIR.md](PAIRED_REPAIR.md). The binary hash and timings below describe the earlier autonomous release; the current executable/hash is in native_release.json.\n\n'+p.read_text(encoding='utf8'),encoding='utf8')
project={};prefix='chat_gpt_ai/gigaforge/'
for name in subprocess.check_output(['git','ls-files','-z','GigaForge']).decode().split('\0'):
 if name and Path(name).is_file():
  data=Path(name).read_bytes()
  if name.endswith('.bat'):data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
  project[prefix+name[len('GigaForge/'):]]=data
for name,data in packed.items():project[prefix+name]=data
project[prefix+'native_release.json']=(gf/'native_release.json').read_bytes()
project['chat_gpt_ai/START_PAIRED_REPAIR.txt']=b'Pause existing training with 4 and wait for it to stop. Merge this folder into Chat_GPT_AI, including gigaforge/native. Keep runs, models, environments and exports. Run gigaforge/9_VERIFY.bat then gigaforge/3_START_OR_RESUME.bat. This continues the same research02 optimizer checkpoints. No new CUDA download or local compiler is required. See gigaforge/PAIRED_REPAIR.md.\r\n'
def manifest(content):return ''.join(sha(b)+'  '+n[len(prefix):]+'\n' for n,b in sorted(content.items()) if n.startswith(prefix) and n!=prefix+'MANIFEST.sha256').encode()
def package(path,content):
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in sorted(content.items()):z.writestr(n,b)
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None
  for line in z.read(prefix+'MANIFEST.sha256').decode().splitlines():
   digest,name=line.split('  ',1);assert sha(z.read(prefix+name))==digest
 return dict(path=path.name,bytes=path.stat().st_size,sha256=sha(path.read_bytes()))
project[prefix+'MANIFEST.sha256']=manifest(project)
release=dict(validation,executable_sha256=build['executable_sha256'],strength='No confirmed playing-strength improvement from research02; retained starting actors are preserved',
 update=package(out/'GigaForge-Paired-Eval-Training-Focus-Update.zip',project))
with zipfile.ZipFile(out/'NovaForge-GigaForge-Autonomous-Windows.zip') as z:full={n:z.read(n) for n in z.namelist() if not n.startswith(prefix)}
full.update(project);full[prefix+'MANIFEST.sha256']=manifest(full)
release['complete']=package(out/'NovaForge-GigaForge-Paired-Eval-Windows.zip',full)
(root/'research/GigaForge-paired-eval-release.json').write_text(json.dumps(release,indent=2))
(root/'GIGAFORGE_PAIRED_REPAIR_DOWNLOAD.md').write_text('''# Paired evaluation repair and training-focus update

[Update ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-Paired-Eval-Training-Focus-Update.zip) | [Complete project ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-GigaForge-Paired-Eval-Windows.zip)

Existing research02: run 4_PAUSE and wait for the console to finish. Merge chat_gpt_ai into the existing Chat_GPT_AI folder, including gigaforge/native. Keep runs, models, environments and exports. Run 9_VERIFY, then 3_START_OR_RESUME. This resumes existing optimizer checkpoints and automatically records a training-focus policy when the measured run is spending too much on evaluation without accepted gains. No CUDA download or local compiler is required. A fresh installation needs 1_SETUP_GPU or 0_SETUP_CPU before verification, and 17 starts research02.

The native repair gives each evaluation arena its own random-engine state and orders car updates by stable car IDs, fixing thread-dependent respawns and pointer-dependent update order. The before/after Linux check changed from five unequal identical-model comparisons out of 64 to zero; the Windows full-length check also passed. For the uploaded stalled study, training focus changes full blocks from 65,536 to 262,144 decisions and branch caps from 524,288 to 2,097,152, concentrating on control and the best measured alternative with regular exploration. Reward formulas, original actors/hitboxes, epochs and promotion requirements are preserved. W&B status now refreshes completed progress.

[Detailed behavior](GigaForge/PAIRED_REPAIR.md) | [Release validation and hashes](research/GigaForge-paired-eval-release.json)

No stronger policy is bundled or claimed. The report had no confirmed improvement after 30 trials and six confirmations. These fixes improve measurement and learning allocation; a longer run must establish playing-strength gains. Send 8_REPORT after another hour.
''',encoding='utf8')
print('PAIRED_RELEASE',json.dumps(release))
