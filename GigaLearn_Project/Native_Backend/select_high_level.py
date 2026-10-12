"""Select a bounded local sample of Rolv-Arild's downloaded curated dataset."""
import argparse,heapq,json,shutil,sys,math
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from slater_v041_core import atomic_json,sha256


def select(folder,out,limit=100,player_cap=8):
    folder=Path(folder).resolve();out=Path(out).resolve()
    if not out.is_relative_to(ROOT/'data/isolated'):raise ValueError('Output must be under data/isolated')
    if not 10<=limit<=1000:raise ValueError('Select 10..1000 replays')
    meta=folder/'metadata.json'
    if not meta.is_file():raise ValueError('Choose a curated mode folder containing JSONL metadata.json and .replay files')
    heap=[];seen=0;seen_ids=set()
    with meta.open(encoding='utf8') as f:
        for line in f:
            if not line.strip():continue
            row=json.loads(line);rid=row.get('id');score=float(row.get('score',0));duration=float(row.get('gameplay_duration',0))
            if not rid or rid in seen_ids or not math.isfinite(score):continue
            seen_ids.add(rid)
            path=folder/(str(rid)+'.replay')
            if not path.is_file() or duration<60:continue
            seen+=1;item=(score,str(rid),row)
            if len(heap)<limit*20:heapq.heappush(heap,item)
            elif item[:2]>heap[0][:2]:heapq.heapreplace(heap,item)
    chosen=[];players=Counter();hashes=set()
    for score,rid,row in sorted(heap,reverse=True):
        ids=[str(v) for v in row.get('players',[])]
        if player_cap and any(players[i]>=player_cap for i in ids):continue
        path=folder/(rid+'.replay');digest=sha256(path)
        if digest in hashes:continue
        hashes.add(digest);chosen.append({'id':rid,'score':score,'sha256':digest,'file':path.name})
        players.update(ids)
        if len(chosen)==limit:break
    if len(chosen)<10:raise ValueError('Fewer than ten usable matches after selection')
    out.mkdir(parents=True,exist_ok=True)
    if (out/'selection.json').exists():raise FileExistsError('Selection exists; choose a new output folder')
    for row in chosen:
        target=out/row['file']
        if target.exists() and sha256(target)!=row['sha256']:raise ValueError('Existing replay differs')
        if not target.exists():shutil.copy2(folder/row['file'],target)
    result={'source':str(folder),'metadata_sha':sha256(meta),'available':seen,'selected':chosen,
            'quality_claim':'Scores/curation are supplied by upstream; no independently verified rank is inferred here.'}
    atomic_json(out/'selection.json',result);print('HIGH_LEVEL_SAMPLE_READY',out,len(chosen));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
    p.add_argument('--limit',type=int,default=100);p.add_argument('--player-cap',type=int,default=8)
    a=p.parse_args();select(a.input,a.out,a.limit,a.player_cap)
