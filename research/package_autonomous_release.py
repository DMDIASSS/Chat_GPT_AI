"""Build a source-only updater and full package atop the pinned verified binary."""
from pathlib import Path
import argparse,hashlib,json,zipfile
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-commit',required=True);args=p.parse_args()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(args.base.read_bytes())=='9f5160873ee00d0b60b3ae798d80e985d6b72ca7196e28827b85e552c33eed4e'
names=['research.py','research_eval.py','run.py','3_START_OR_RESUME.bat','17_START_AUTONOMOUS_RESEARCH.bat','AUTONOMOUS_RESEARCH.md','VALIDATION_AUTONOMOUS.md','README.md','RESEARCH_START.md','tests/test_research.py','tests/test_research_eval.py','tests/check_research_native.py','tests/check_autonomous_native.py','native_access.py','16_CHECK_NATIVE_ACCESS.bat','NATIVE_ACCESS_FIX.md','tests/test_native_access.py']
prefix='chat_gpt_ai/gigaforge/'
project={}
for name in names:
 data=(args.root/'GigaForge'/name).read_bytes()
 if name.endswith('.bat'):data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
 project[prefix+name]=data
project['chat_gpt_ai/START_AUTONOMOUS_RESEARCH.txt']=b'''Pause older trainers and wait for their consoles to finish. Merge these folders into your existing Chat_GPT_AI folder, preserving environments, models, runs and exports. Open gigaforge/17_START_AUTONOMOUS_RESEARCH.bat once. It starts research02 with Chronos Breakout and Galactus V2 Octane. Button 3 then resumes the active research run; 4 pauses; 8 makes a report; 7 exports retained champions. Default session is approximately five hours. Send the first report after one hour. Read gigaforge/AUTONOMOUS_RESEARCH.md for exact behavior and limitations.\r\n'''
manifest=lambda mapping:''.join(sha(b)+'  '+n[len(prefix):]+'\n' for n,b in sorted(mapping.items()) if n.startswith(prefix) and n!=prefix+'MANIFEST.sha256').encode()
project[prefix+'MANIFEST.sha256']=manifest(project)
args.output.mkdir(parents=True,exist_ok=True)
update=args.output/'GigaForge-Autonomous-Research02-Update.zip'
def package(path,content):
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in sorted(content.items()):z.writestr(n,b)
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None
  for line in z.read(prefix+'MANIFEST.sha256').decode().splitlines():
   digest,name=line.split('  ',1);assert sha(z.read(prefix+name))==digest
  assert all(n.startswith('chat_gpt_ai/') for n in z.namelist())
 return dict(path=path.name,bytes=path.stat().st_size,sha256=sha(path.read_bytes()))
release=dict(source_commit=args.source_commit,update=package(update,project),native_changed=False,weights_bundled=False)
with zipfile.ZipFile(args.base) as z:full={n:z.read(n) for n in z.namelist()}
full.update(project);full[prefix+'MANIFEST.sha256']=manifest(full)
assert sha(full[prefix+'native/GigaForge.exe'])=='3fc3eaaa51af944d2a87773f9aebcbc82b12812778d53af9ed64a106fc46e128'
complete=args.output/'NovaForge-GigaForge-Autonomous-Windows.zip'
release['complete']=package(complete,full)
(args.output/'GigaForge-autonomous-release.json').write_text(json.dumps(release,indent=2))
print(json.dumps(release,indent=2))
