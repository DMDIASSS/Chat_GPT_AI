"""Offline replay inventory. No labels inferred; no model changes and no token access."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def audit(root:Path):
    files=list(root.rglob('*.replay')) if root.exists() else []
    seen={};extensions=Counter();bad=[];total_bytes=0
    for path in files:
        try:
            size=path.stat().st_size
            if not 128 <= size <= 30*1024*1024:
                bad.append({'path':str(path.relative_to(root)),'reason':f'unexpected size {size}'})
                continue
            # Detect duplicates even when UUID filenames differ; avoid reading whole data folder into memory.
            h=hashlib.sha256()
            with path.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            digest=h.hexdigest();total_bytes+=size
            if digest in seen:bad.append({'path':str(path.relative_to(root)),'reason':f'duplicate content of {seen[digest]}'})
            else:seen[digest]=str(path.relative_to(root))
            extensions[path.parent.name]+=1
        except OSError as exc:bad.append({'path':str(path),'reason':str(exc)})
    return {'created_utc':datetime.now(timezone.utc).isoformat(),'file_count':len(files),
            'unique_binary_hashes':len(seen),'bytes_examined':total_bytes,
            'directories':dict(extensions),'issues':bad[:200],
            'training_ready':False,
            'caveat':'Binary size/hash inventory ONLY. No verified gameplay labels or native Nexto behavior-cloning conversion.'}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=ROOT/'data'/'replays')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'afk_improved'/'reports'/'replay_inventory.json')
    args=p.parse_args(argv)
    result=audit(args.root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='issues'},indent=2))
    print('Report saved:',args.output)
    return 0
if __name__=='__main__':raise SystemExit(main())
