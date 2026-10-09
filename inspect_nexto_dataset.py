"""Check Nexto teacher dataset quality before distillation."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
from nexto_teacher import nexto_actions


def inspect(path: Path):
    files=sorted(path.glob('nexto_rollout_*.npz')) if path.is_dir() else [path]
    if not files or not all(f.is_file() for f in files):
        raise FileNotFoundError('Dataset missing; run COLLECT_NEXTO_ROLLOUTS.bat first')
    table=nexto_actions()
    counts=np.zeros(90,dtype=np.int64)
    total=0
    groups=set()
    mean_entropy=0.
    for f in files:
        with np.load(f,allow_pickle=False) as data:
            obs=data['obs']; p=np.asarray(data['teacher_probs'],dtype=np.float32)
            labels=np.asarray(data['actions'],dtype=np.int64)
            ids=data['replay_ids']
            if obs.ndim!=2 or obs.shape[1]!=92 or p.shape!=(len(obs),90) or labels.shape!=(len(obs),) or ids.shape!=(len(obs),):
                raise ValueError(f'Invalid data shape in {f}')
            if not np.isfinite(obs).all() or not np.isfinite(p).all() or np.any(p<0):
                raise ValueError(f'Invalid values in {f}')
            if not np.allclose(p.sum(axis=1),1,atol=3e-3):
                raise ValueError(f'Probabilities not normalized in {f}')
            if labels.min()<0 or labels.max()>=90:
                raise ValueError(f'Invalid action in {f}')
            counts += np.bincount(labels,minlength=90)
            groups.update(np.unique(ids).tolist())
            mean_entropy += float((-(p*np.log(np.clip(p,1e-10,None))).sum(axis=1)).sum())
            total += len(obs)
    if total==0:
        raise ValueError('Dataset is empty')
    actions=table[np.repeat(np.arange(90),counts)]
    print(f'Files: {len(files)} | Rows: {total:,} | Independent episodes: {len(groups):,}')
    print(f'Teacher soft-target mean entropy: {mean_entropy/total:.3f}')
    print('Teacher top-action frequencies:')
    print(f'  Jump: {100*(actions[:,5]>0).mean():.1f}%')
    print(f'  Boost: {100*(actions[:,6]>0).mean():.1f}%')
    print(f'  Forward throttle: {100*(actions[:,0]>0).mean():.1f}%')
    print(f'  Handbrake: {100*(actions[:,7]>0).mean():.1f}%')
    print('Most common actions: '+', '.join(f'{i} ({counts[i]/total:.1%})' for i in np.argsort(counts)[::-1][:5]))
    if len(groups)<2:
        raise ValueError('Need 2+ independent episodes so validation can hold out whole episodes')
    print('Dataset checks passed')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',type=Path,default=Path(__file__).resolve().parent/'data/datasets/nexto_rollouts')
    a=p.parse_args()
    inspect(a.dataset)
