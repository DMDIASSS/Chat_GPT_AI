"""Verify cached replay shards and report the accepted 1v1/2v2/3v3 coverage."""
from collections import Counter
from pathlib import Path
import argparse
import numpy as np
from replay_il.train import Dataset
from slater_v041_core import atomic_json,sha256


def audit(folder,*,require_3v3=True):
    folder=Path(folder);data=Dataset(folder);matches={s:Counter() for s in data.rows};samples={s:Counter() for s in data.rows}
    for record in data.records:
        with np.load(record['shard'],allow_pickle=False) as shard:players=shard['players']
        if players.shape!=(record['samples'],) or not np.isin(players,[2,4,6]).all():
            raise ValueError('Replay shard has invalid player counts')
        for count in np.unique(players):
            name=f'{count//2}v{count//2}';split=record['split']
            matches[split][name]+=1;samples[split][name]+=int(np.count_nonzero(players==count))
    missing=[split for split in data.rows if matches[split]['3v3']<2]
    report={'schema':'replay-il-format-audit-v1','dataset_sha256':sha256(folder/'manifest.json'),
        'matches_by_split_and_format':{s:dict(v) for s,v in matches.items()},
        'samples_by_split_and_format':{s:dict(v) for s,v in samples.items()},
        'cached_shards_verified':len(data.records),'cached_samples_verified':data.sample_count,
        'require_3v3':bool(require_3v3),'allowed_formats':['1v1','2v2','3v3'],
        'verified_3v3_coverage':not missing,'insufficient_3v3_splits':missing,
        'note':'Accepted reconstructed samples and independent matches; not verification of player rank or hitbox.'}
    atomic_json(folder/'format_audit.json',report)
    if require_3v3 and missing:raise ValueError('Mixed training requires at least two accepted 3v3 matches in each split. Missing: '+', '.join(missing)+'. See format_audit.json; add real replays to a new dataset path.')
    print('CACHE_VERIFIED:',len(data.records),'saved shards |',data.sample_count,'saved samples | no replay reconstruction',flush=True)
    print('FORMAT_AUDIT:',report['matches_by_split_and_format'],flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--allow-no-3v3',action='store_true',help='Report coverage without requiring 3v3 matches')
    args=parser.parse_args()
    try:audit(args.dataset,require_3v3=not args.allow_no_3v3)
    except (ValueError,RuntimeError,OSError) as error:print('STOPPED:',str(error),flush=True);raise SystemExit(1)
