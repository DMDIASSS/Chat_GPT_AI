"""Package the verified research binary and current Python controller; no user data."""
from pathlib import Path
import hashlib,json,zipfile,sys,subprocess,os
root=Path.cwd();gf=root/'GigaForge';native=root/'verified-native'
sha=lambda data:hashlib.sha256(data).hexdigest()
build=json.loads((native/'build.json').read_text(encoding='utf8'))
assert sha((native/'GigaForge.exe').read_bytes())==build['executable_sha256']
assert build['patch_sha256']==sha((gf/'tools/patch_upstream.py').read_bytes())
for name,digest in build['app_source_sha256'].items():assert sha((gf/name).read_bytes())==digest
native_run=int(os.environ['NATIVE_VERIFIED_RUN']);package_run=int(os.environ['GITHUB_RUN_ID'])
validation=dict(native_workflow=native_run,package_workflow=package_run,source_commit=os.environ['GITHUB_SHA'],
 tests='Windows native parity, legacy resume, PBRS/GAE boundary tests, all-sample collection, 8 actual profile/family tests, controller rejection/promotion/protection and export parity',cuda_hardware_verified=False)
(native/'research_validation.json').write_text(json.dumps(validation,indent=2))
sys.path.insert(0,str(gf/'tools'));import build_native
vendor=build_native.prepare();notices={}
for p in vendor.rglob('*'):
 if p.is_file() and p.name.lower().startswith(('license','copying','notice')):notices['native/notices/'+p.relative_to(vendor).as_posix()]=p.read_bytes()
notices['native/ATTRIBUTION.txt']=('GigaLearnCPP/RLGymCPP/RocketSim: ZealanL and contributors. Pinned source '+build_native.COMMIT+'. Native research verification workflow '+str(native_run)+'. Torch 2.9.1 is supplied separately. See RESEARCH_PAPERS.md for research attribution. No teacher weights bundled.\n').encode()
packed={}
for p in native.rglob('*'):
 if p.is_file():packed['native/'+p.relative_to(native).as_posix()]=p.read_bytes()
packed.update(notices)
tmp=root/'downloads/_native_research_temp.zip'
with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(packed.items()):z.writestr(n,b)
digest=sha(tmp.read_bytes());nativezip=tmp.with_name('GigaForge-native-research-'+digest[:12]+'.zip');tmp.rename(nativezip)
meta=dict(url='https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/'+nativezip.name,sha256=digest,
 executable_sha256=build['executable_sha256'],verified_workflow=native_run,package_workflow=package_run,cuda_hardware_verified=False,research_protocol='fixed-rollout-v1')
(gf/'native_release.json').write_text(json.dumps(meta,indent=2))
(gf/'README.md').write_text('''# GigaForge reward research

This release keeps two independent actors: Chronos on Breakout and Galactus V2 on Octane. It adds all-sample bootstrapped rollouts, a small serial population of reward/learning-rate variants, bounded reward coefficient mutation, frozen/current/history opponents, teacher anchoring, resumable branches, W&B match metrics and protected exports.

[Start and resume instructions](RESEARCH_START.md) · [Paper-to-code mapping](RESEARCH_PAPERS.md) · [Pilot and validation](RESEARCH_VALIDATION.md) · [Dependency reuse](RUNTIME_UPDATE.md)

Merge the ZIP's chat_gpt_ai folders into your existing project. Preserve environments, assets, models, runs and exports. The new native executable is included. Run 9_VERIFY, then 3_START_OR_RESUME. If a runtime is missing, run 1_SETUP_GPU or 0_SETUP_CPU; compatible existing libraries are reused. The new run is research01; existing native01 remains separate and its halt is not erased. The coordinator runs for approximately five hours per session, or until paused/error. A rejected branch is retired automatically while the search continues.

Pause/report/watch/export target the active research run. Watch retained champions with 5/6, unverified candidates with 10/11, export two independent v5 actors with 7, and send diagnostics with 8. Exports contain complete TorchScript .lt/.pt actors, TOML/loadout and loaders; no training critic or reward program is needed in RLBot.

Prepared/collected data use reached 100% in the controlled checks and pilot. Actual optimizer sample-use counts are logged separately. This does not guarantee stronger play. The short public pilot found no confirmed winner and retained both starting parents. A new candidate needs positive paired screening and fresh confirmation before replacing its retained champion. Repeated statistical comparisons are approximate; no universal or lifetime strength guarantee is claimed.

The Windows CPU build and controller checks passed. The user's earlier CUDA runtime works; this new executable must still pass the target GPU verification before a long GPU run. No laptop SPS promise, model downsizing or reduced PPO epoch count is used.

Source build: Python 3.11 x64, Torch 2.9.1, Visual Studio 2022 C++ Build Tools, then python tools/build_native.py. The builder fetches a commit/SHA256-pinned GigaLearn archive, applies explicit reviewed changes and builds Release. The native simulator is RocketSim 2.1.1; Python viewing/live adapters use RocketSim 2.2.1. Exact physics equivalence and live playing strength are not established by feature parity.
''',encoding='utf8')
p=gf/'RUNTIME_UPDATE.md';text=p.read_text(encoding='utf8').replace('Open 3_START_OR_RESUME.bat. Every launcher now uses the same selected interpreter. Existing native01 checkpoints and W&B identity are preserved.', 'Open 3_START_OR_RESUME.bat for research01. Every launcher uses the same selected interpreter. Existing native01 checkpoints and W&B identity remain available in that separate legacy run.');p.write_text(text,encoding='utf8')
tracked=subprocess.check_output(['git','ls-files','-z','GigaForge']).decode().split('\0');project={}
for name in tracked:
 if name and Path(name).is_file():
  b=Path(name).read_bytes()
  if name.endswith('.bat'):b=b.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
  project['chat_gpt_ai/gigaforge/'+name[len('GigaForge/'):]]=b
project['chat_gpt_ai/gigaforge/native_release.json']=(gf/'native_release.json').read_bytes()
for name,b in packed.items():project['chat_gpt_ai/gigaforge/'+name]=b
prefix='chat_gpt_ai/gigaforge/'
project[prefix+'MANIFEST.sha256']=''.join(sha(b)+'  '+n[len(prefix):]+'\n' for n,b in sorted(project.items())).encode()
update=root/'downloads/GigaForge-Reward-Research-Update.zip'
with zipfile.ZipFile(update,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(project.items()):z.writestr(n,b)
base=root/'downloads/NovaForge-GigaForge-Windows.zip'
with zipfile.ZipFile(base) as z:full={n:z.read(n) for n in z.namelist() if not n.startswith(prefix)}
full.update(project);complete=root/'downloads/NovaForge-GigaForge-Research-Windows.zip'
with zipfile.ZipFile(complete,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(full.items()):z.writestr(n,b)
for p in (update,complete):
 with zipfile.ZipFile(p) as z:
  assert z.testzip() is None
  for line in z.read(prefix+'MANIFEST.sha256').decode().splitlines():
   digest,name=line.split('  ',1);assert sha(z.read(prefix+name))==digest
release=dict(source_commit=os.environ['GITHUB_SHA'],native_workflow=native_run,package_workflow=package_run,
 update=dict(path=update.name,size=update.stat().st_size,sha256=sha(update.read_bytes())),
 complete=dict(path=complete.name,size=complete.stat().st_size,sha256=sha(complete.read_bytes())),
 executable_sha256=build['executable_sha256'],strength='Not established by the short pilot; no universal improvement guarantee',prepared_data_use='100% in tested fixed rollouts',cuda_new_build_hardware_verified=False)
(root/'research/GigaForge-research-release.json').write_text(json.dumps(release,indent=2))
(root/'GIGAFORGE_RESEARCH_DOWNLOAD.md').write_text('''# GigaForge reward research Windows release

[Update an existing install](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-Reward-Research-Update.zip) · [Complete project ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-GigaForge-Research-Windows.zip)

Pause older trainers. Merge chat_gpt_ai/gigaforge into the existing folder, replacing program/native files while preserving models, runs, assets and environments. Run 9_VERIFY, then 3_START_OR_RESUME. Missing runtime: 1_SETUP_GPU or 0_SETUP_CPU. The coordinator creates research01 from protected starting actors and preserves the halted native01 experiment. It searches reward profiles automatically, retires bad branches, continues after rejections and exports only retained champions. Default session budget is approximately five hours. Pause with 4, report with 8, retained watch with 5/6, candidates with 10/11 and exports with 7.

[Full instructions](GigaForge/RESEARCH_START.md) · [Research papers and exact scope](GigaForge/RESEARCH_PAPERS.md) · [Controlled pilot and validation](GigaForge/RESEARCH_VALIDATION.md) · [Release hashes](research/GigaForge-research-release.json)

Windows CPU correctness checks passed, including real native rollouts, policy updates, optimizer resume, eight reward/family combinations, candidate rejection and protected export copies. The short pilot prepared all 65536 collected samples but did not establish a stronger model. This is an empirical improvement search, not a 100% strength guarantee. New-build CUDA verification still runs on the user's PC. No teacher weights, user reports or API keys are published.
''',encoding='utf8')
print('RESEARCH_RELEASE',json.dumps(release))
