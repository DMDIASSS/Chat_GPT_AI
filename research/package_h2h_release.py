"""Package Windows-verified direct head-to-head evaluator and resumable controller."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,zipfile
root=Path.cwd();gf=root/'GigaForge';native=root/'verified-native';out=root/'downloads';out.mkdir(exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((native/'build.json').read_text(encoding='utf8'))
assert sha((native/'GigaForge.exe').read_bytes())==build['executable_sha256']
assert build['patch_sha256']==sha((gf/'tools/patch_upstream.py').read_bytes())
for name,digest in build['app_source_sha256'].items():assert sha((gf/name).read_bytes())==digest
verified=int(os.environ['NATIVE_VERIFIED_RUN']);workflow=int(os.environ['GITHUB_RUN_ID'])
validation=dict(source_commit=os.environ['GITHUB_SHA'],native_workflow=verified,package_workflow=workflow,evaluation_protocol='arena-rng-v4',head_to_head_protocol='direct-h2h-v1',cuda_hardware_verified=False,scope='Windows native feature/action/network parity, learning/resume regressions, full clone evaluation, direct round count, real H2H selection/resume/export parity and 100-second matches. Public fixture models only; no private candidate strength claim.')
(native/'h2h_validation.json').write_text(json.dumps(validation,indent=2))
sys.path.insert(0,str(gf/'tools'));import build_native
vendor=build_native.prepare();packed={}
for p in native.rglob('*'):
 if p.is_file():packed['native/'+p.relative_to(native).as_posix()]=p.read_bytes()
for p in vendor.rglob('*'):
 if p.is_file() and p.name.lower().startswith(('license','copying','notice')):packed['native/notices/'+p.relative_to(vendor).as_posix()]=p.read_bytes()
packed['native/ATTRIBUTION.txt']=('GigaLearnCPP/RLGymCPP/RocketSim by ZealanL and contributors. Pinned upstream '+build_native.COMMIT+'. Direct H2H evaluator and Python orchestration by NovaForge. Torch 2.9.1 installed separately. No teacher weights bundled.\n').encode()
temp=out/'_h2h_native.zip'
with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(packed.items()):z.writestr(n,b)
digest=sha(temp.read_bytes());bundle=temp.with_name('GigaForge-native-h2h-'+digest[:12]+'.zip');temp.rename(bundle)
(gf/'native_release.json').write_text(json.dumps(dict(url='https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/'+bundle.name,sha256=digest,executable_sha256=build['executable_sha256'],verified_workflow=verified,package_workflow=workflow,research_protocol='fixed-rollout-v1',evaluation_protocol='arena-rng-v4',head_to_head_protocol='direct-h2h-v1',cuda_hardware_verified=False),indent=2))
p=gf/'README.md';p.write_text(p.read_text(encoding='utf8')+'\n[200-game candidate versus original test](HEAD_TO_HEAD.md): run 20_WDL_BEST_VS_ORIGINAL_200x100.bat with training paused.\n',encoding='utf8')
project={};prefix='chat_gpt_ai/gigaforge/'
for n in subprocess.check_output(['git','ls-files','-z','GigaForge']).decode().split('\0'):
 if n and Path(n).is_file():
  b=Path(n).read_bytes()
  if n.endswith('.bat'):b=b.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
  project[prefix+n[len('GigaForge/'):]]=b
for n,b in packed.items():project[prefix+n]=b
project[prefix+'native_release.json']=(gf/'native_release.json').read_bytes()
project['chat_gpt_ai/novaforge/nova/forge_export.py']=(root/'NovaForge/nova/forge_export.py').read_bytes()
project['chat_gpt_ai/START_H2H_TEST.txt']=b'Close trainers and viewers. Merge this update into Chat_GPT_AI, including gigaforge/native and novaforge. Keep all runs and environments. Run gigaforge/9_VERIFY.bat then 20_WDL_BEST_VS_ORIGINAL_200x100.bat. Test only: 200 games, 100 simulated seconds each, 100 per color; no training or promotion. See gigaforge/HEAD_TO_HEAD.md.\r\n'
def manifest(content):return ''.join(sha(b)+'  '+n[len(prefix):]+'\n' for n,b in sorted(content.items()) if n.startswith(prefix) and n!=prefix+'MANIFEST.sha256').encode()
def package(path,content):
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in sorted(content.items()):z.writestr(n,b)
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None
  for line in z.read(prefix+'MANIFEST.sha256').decode().splitlines():
   digest,n=line.split('  ',1);assert sha(z.read(prefix+n))==digest
 return dict(path=path.name,bytes=path.stat().st_size,sha256=sha(path.read_bytes()))
project[prefix+'MANIFEST.sha256']=manifest(project)
release=dict(validation,executable_sha256=build['executable_sha256'],update=package(out/'GigaForge-200x100-WDL-Update.zip',project))
with zipfile.ZipFile(out/'NovaForge-GigaForge-Autonomous-Windows.zip') as z:full={n:z.read(n) for n in z.namelist() if not n.startswith(prefix)}
full.update(project);full[prefix+'MANIFEST.sha256']=manifest(full)
release['complete']=package(out/'NovaForge-GigaForge-200x100-WDL-Windows.zip',full)
(root/'research/GigaForge-h2h-release.json').write_text(json.dumps(release,indent=2))
(root/'GIGAFORGE_H2H_DOWNLOAD.md').write_text('# Frozen candidate versus original: 200 games, 100 seconds\n\n[Update ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-200x100-WDL-Update.zip) | [Complete ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-GigaForge-200x100-WDL-Windows.zip)\n\nClose trainers/viewers, merge the update including native, keep runs and environments. Run 9_VERIFY then 20_WDL_BEST_VS_ORIGINAL_200x100. Training stays paused. The best available positive confirmation-test candidate plays its own frozen original, 100 games per color. No extra baseline games or automatic promotion. [Details and direct command](GigaForge/HEAD_TO_HEAD.md). Results in runs/research02/latest_h2h.json.\n',encoding='utf8')
print('H2H_RELEASE',json.dumps(release))
