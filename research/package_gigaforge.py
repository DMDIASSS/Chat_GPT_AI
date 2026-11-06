"""Package an already verified Windows artifact; never compile or promote models."""
from pathlib import Path
import hashlib,json,zipfile,sys,subprocess,importlib.util
root=Path.cwd();gf=root/'GigaForge';native=root/'verified-native'
sha=lambda b:hashlib.sha256(b).hexdigest()
info=json.loads((native/'build.json').read_text())
assert sha((native/'GigaForge.exe').read_bytes())==info['executable_sha256']
# Fetch only the pinned source for original notices, with the builder's archive hash check.
sys.path.insert(0,str(gf/'tools'))
import build_native
vendor=build_native.prepare()
notices={}
for p in vendor.rglob('*'):
 if p.is_file() and (p.name.lower().startswith(('license','copying','notice'))):notices['native/notices/'+p.relative_to(vendor).as_posix()]=p.read_bytes()
notices['native/ATTRIBUTION.txt']=b'GigaLearnCPP, RLGymCPP and RocketSim: ZealanL and contributors. Original source 86e11c3881a21225a43c36b14af40f0b3c87e7dd. Native Windows CPU verification workflow 42277845367, source 982541980b487d89bd14e3e42d8110691f69fe6a. Torch 2.9.1 runtime supplied separately. CPU verified; actual CUDA hardware verification required. No weights bundled.\n'
archive=root/'downloads/GigaForge-native-windows.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in native.rglob('*'):
  if p.is_file():z.writestr('native/'+p.relative_to(native).as_posix(),p.read_bytes())
 for name,b in sorted(notices.items()):z.writestr(name,b)
digest=sha(archive.read_bytes());named=archive.with_name('GigaForge-native-windows-'+digest[:12]+'.zip');archive.rename(named)
meta=dict(url='https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/'+named.name,sha256=digest,executable_sha256=info['executable_sha256'],verified_workflow=42277845367,cuda_hardware_verified=False)
(gf/'native_release.json').write_text(json.dumps(meta,indent=2))
p=gf/'README.md';s=p.read_text();a=s.index('Status:');b=s.index('\n\n## Source build',a)
s=s[:a]+'''Status: Windows CPU executable included and verified by workflow 42277845367: native feature/mask/action-table/network parity, actual cross training, actor warmup, optimizer resume and paired timed WDL. Linux CPU verification passed too. CUDA on the user's GPU remains unverified.

On Windows, pause existing trainers and merge this ZIP's chat_gpt_ai folders into your existing Chat_GPT_AI. Preserve .venv, assets, runs and exports. Open gigaforge/0_SETUP_CPU.bat for the verified CPU runtime, or 1_SETUP_GPU.bat to install the isolated CUDA runtime and test the actual GPU path. If GPU verification fails, retain the error and use the CPU setup; do not start a long GPU run. Existing Python 3.11 NovaForge environment is required to bootstrap setup. Then run 9_VERIFY, 2_BENCHMARK, and 3_START_OR_RESUME. Benchmarking may take several minutes. Pause with 4_PAUSE, watch protected champions with 5/6, export with 7, and send reports from 8. No compiler is required for the included executable. Start with one short block and inspect WDL before an unattended session.''' +s[b:]
p.write_text(s)
preview=root/'downloads/NovaForge-GigaForge-native-preview.zip'
with zipfile.ZipFile(preview) as z:data={n:z.read(n) for n in z.namelist() if not n.startswith('chat_gpt_ai/gigaforge/') and not n.endswith('MANIFEST.sha256')}
tracked=subprocess.check_output(['git','ls-files','-z','GigaForge']).decode().split('\0')
for name in tracked:
 if name and Path(name).is_file():data['chat_gpt_ai/gigaforge/'+name[len('GigaForge/'):]]=Path(name).read_bytes()
data['chat_gpt_ai/gigaforge/native_release.json']=(gf/'native_release.json').read_bytes()
with zipfile.ZipFile(named) as z:
 for n in z.namelist():data['chat_gpt_ai/gigaforge/'+n]=z.read(n)
for project in ('novaforge','triadbot','forgeleague','gigaforge'):
 prefix='chat_gpt_ai/'+project+'/'
 data[prefix+'MANIFEST.sha256']=''.join(sha(b)+'  '+n[len(prefix):]+'\n' for n,b in sorted(data.items()) if n.startswith(prefix)).encode()
output=root/'downloads/NovaForge-GigaForge-Windows.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
 for name,b in sorted(data.items()):z.writestr(name,b)
assert zipfile.ZipFile(output).testzip() is None
(root/'GIGAFORGE_PREVIEW.md').write_text('# GigaForge Windows CPU-verified release\n\n[Download complete ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-GigaForge-Windows.zip)\n\nContains chat_gpt_ai/novaforge, triadbot, forgeleague and gigaforge, including the verified Windows CPU executable. Read [setup and commands](GigaForge/README.md). CPU native training/resume/parity passed on Windows and Linux; the full existing Python Windows workflow passed too. GPU hardware verification remains necessary on the target PC. No strength gain or laptop SPS promise. Existing models/runs are preserved.\n\nZIP SHA256: '+sha(output.read_bytes())+'\n')
print('WINDOWS_PACKAGE',output.stat().st_size,sha(output.read_bytes()))
