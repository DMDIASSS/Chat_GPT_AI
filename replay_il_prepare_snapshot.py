"""Resume a fixed input set without changing fingerprinted parser/trainer code."""
from pathlib import Path
import argparse
import json
import sys
import traceback
from replay_il.launch import Tee
from slater_v041_core import atomic_json,read_json,sha256


def freeze_inputs(dataset,roots,*,max_replays=None,max_samples=None):
    dataset=Path(dataset);snapshot=dataset/'input_snapshot.json'
    saved=read_json(snapshot) if snapshot.exists() else None
    # Existing datasets retain the exact budgets that made their saved shards.
    # Fresh datasets discover all files up to the parser's supported safety cap.
    all_replays=max_replays is None
    automatic_samples=max_samples is None
    max_replays=max_replays if max_replays is not None else saved['max_replays'] if saved else 100000
    max_samples=max_samples if max_samples is not None else saved['max_samples'] if saved else 500000
    if type(max_replays) is not int or not 1<=max_replays<=100000 or type(max_samples) is not int or not 100<=max_samples<=2000000:
        raise ValueError('Invalid replay/sample budget')
    if saved is not None:
        if (saved['max_replays'],saved['max_samples'])!=(max_replays,max_samples):
            raise ValueError('Dataset input/sample budget is frozen. Use a new --dataset to change it.')
        for entry in saved['files']:
            path=Path(entry['path'])
            if not path.is_file():raise ValueError('Frozen input is missing: '+str(path))
            stat=path.stat()
            if [stat.st_size,stat.st_mtime_ns]!=entry['signature'] and sha256(path)!=entry['sha256']:
                raise ValueError('Frozen replay changed: '+str(path)+'. Preserve the dataset and use a new path for changed data.')
        return saved
    paths=[]
    for root in roots:
        path=Path(root);paths.extend(path.rglob('*.replay') if path.is_dir() else [path])
    paths=sorted({p.resolve() for p in paths if p.is_file() and p.suffix.lower()=='.replay'})
    if all_replays and len(paths)>max_replays:raise ValueError('More than 100000 replays found; use explicitly versioned datasets.')
    if len(paths)>max_replays:print('EXPLICIT REPLAY LIMIT:',max_replays,'of',len(paths),'files selected',flush=True)
    paths=paths[:max_replays]
    if not paths:raise ValueError('No replay inputs found. Finish downloading the intended replay batch first.')
    # The legacy parser has a minimum 16-row per-match reservoir. Ensure its
    # global sample stop cannot silently skip the tail of a fresh input list.
    required=16*len(paths)
    if automatic_samples:max_samples=max(max_samples,required)
    if max_samples<required:raise ValueError('Sample budget cannot cover every selected replay. Increase --max-samples or explicitly limit --max-replays.')
    files=[]
    for path in paths:
        stat=path.stat();files.append({'path':str(path),'signature':[stat.st_size,stat.st_mtime_ns],'sha256':sha256(path)})
    saved={'schema':'replay-il-input-snapshot-v1','max_replays':max_replays,'max_samples':max_samples,'files':files}
    dataset.mkdir(parents=True,exist_ok=True);atomic_json(snapshot,saved);return saved


class ClosingSafeTee(Tee):
    """Late console cleanup may keep a reference after the logfile closes."""
    def write(self,text):
        self.screen.write(text)
        if not self.log.closed:self.log.write(text)
        self.flush()
    def flush(self):
        self.screen.flush()
        if not self.log.closed:self.log.flush()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dataset',type=Path,required=True)
    args=parser.parse_args(argv);snapshot=read_json(args.dataset/'input_snapshot.json')
    log=Path(__file__).resolve().parent/'data/isolated/replay_imitation/launcher.log';log.parent.mkdir(parents=True,exist_ok=True)
    original_stdout,original_stderr=sys.stdout,sys.stderr
    with log.open('a',encoding='utf8') as stream:
        sys.stdout=ClosingSafeTee(original_stdout,stream);sys.stderr=ClosingSafeTee(original_stderr,stream)
        try:
            print('FROZEN REPLAY INPUTS:',len(snapshot['files']),'| completed shards are reused when valid',flush=True)
            from replay_il.data import prepare
            prepare([entry['path'] for entry in snapshot['files']],args.dataset,
                max_replays=snapshot['max_replays'],max_samples=snapshot['max_samples'])
            return 0
        except Exception:traceback.print_exc();return 1
        finally:sys.stdout,sys.stderr=original_stdout,original_stderr


if __name__=='__main__':raise SystemExit(main())
