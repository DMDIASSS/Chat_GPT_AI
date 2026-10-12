"""Read-only audit of extracted v0.3.1 kickoff files/manifest and replay split integrity.

No deletes or modifications. Reports unique replay SHA, duplicates, split leakage and
starting car/ball pose quality. Manifest failed replays are NOT necessarily corrupt.
"""
from __future__ import annotations
import argparse,json
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np


def audit(root: Path) -> dict:
    root=Path(root)
    if not root.is_dir():raise ValueError(f'No kickoff directory: {root}')
    report={'by_split':{},'cross_split_sha_leakage':[],
            'duplicate_scenario_keys':[], 'bad_poses':[], 'manifest_errors':{}}
    seen=defaultdict(set);keys=set()
    for split in ('train','validation','test'):
        paths=sorted((root/split).glob('*_kickoff*.npz'))
        shas=[]
        for path in paths:
            with np.load(path,allow_pickle=False) as rec:
                sha=str(rec['replay_sha'])
                key=(sha,int(rec['source_period']))
                if key in keys:report['duplicate_scenario_keys'].append(str(path))
                keys.add(key)
                shas.append(sha);seen[sha].add(split)
                if str(rec['split'])!=split:report['bad_poses'].append(str(path)+':split')
                for k in ('blue_position','orange_position','ball_position'):
                    if not np.isfinite(np.asarray(rec[k],dtype=float)).all():report['bad_poses'].append(str(path)+':'+k)
        report['by_split'][split]={'scenarios':len(paths),'unique_source_replays':len(set(shas))}
    report['cross_split_sha_leakage']=[sha for sha,splits in seen.items() if len(splits)>1]
    mf=root/'manifest_v031.json'
    if mf.exists():
        rows=json.loads(mf.read_text(encoding='utf8'))
        errors=[x for x in rows if x.get('error')]
        report['manifest_errors']={'count':len(errors),
            'filename_collision':sum('FileExistsError' in x.get('error','') for x in errors),
            'other':sum('FileExistsError' not in x.get('error','') for x in errors)}
    report['safe_for_heldout']=not (report['cross_split_sha_leakage'] or report['duplicate_scenario_keys'] or report['bad_poses'])
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenarios',default='data/kickoffs_v031')
    a=p.parse_args()
    d=audit(Path(a.scenarios))
    print('KICKOFF_DATASET_AUDIT',json.dumps(d,sort_keys=True))
    if not d['safe_for_heldout']:raise SystemExit('Dataset integrity failure: do not benchmark')

if __name__=='__main__':main()
