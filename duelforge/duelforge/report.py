import hashlib,json,platform,time,zipfile
from pathlib import Path
import torch
from .runtime import ROOT,sha,source_hashes

def report(folder):
    folder=Path(folder)
    if not folder.is_dir():raise FileNotFoundError('Run has not been created: '+str(folder))
    target=ROOT/f'DuelForge_report_{folder.name}_{time.time_ns()}.zip';included=[];omitted=[];size=0;cap=24*1024*1024
    paths=[p for p in folder.glob('*.json') if p.name not in ('wandb-settings.json',)]+list(folder.glob('*.jsonl'))
    for clip in sorted((folder/'watch').glob('*'),reverse=True)[:2]:paths+=list(clip.glob('metadata.json'))+list(clip.glob('frames.npz'))
    sources=list((ROOT/'duelforge').glob('*.py'))+list((ROOT/'native').glob('*.cpp'))+[ROOT/'config.json',ROOT/'PROTOTYPE_GUIDE.md',ROOT/'VALIDATION.json']
    manifest={'run':folder.name,'generated_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'python':platform.python_version(),'torch':torch.__version__,'cuda':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name() if torch.cuda.is_available() else None,'latest_checkpoint_sha256':sha(folder/'latest.pt') if (folder/'latest.pt').is_file() else None,'source_hashes':source_hashes(),'scope':'No model weights, W&B directory, API keys, netrc, process environment or installed packages included. Last two watch recordings may be included within 24 MiB raw cap.'}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in dict.fromkeys(paths):
            name='run/'+str(p.relative_to(folder))
            if size+p.stat().st_size>cap:omitted.append(name);continue
            z.write(p,name);included.append(name);size+=p.stat().st_size
        for p in sources:
            if p.is_file():z.write(p,'source/'+str(p.relative_to(ROOT)))
        manifest.update(included=included,omitted=omitted);z.writestr('manifest.json',json.dumps(manifest,indent=2))
    print('REPORT_READY:',target,'; send this ZIP for diagnosis.',flush=True);return target
