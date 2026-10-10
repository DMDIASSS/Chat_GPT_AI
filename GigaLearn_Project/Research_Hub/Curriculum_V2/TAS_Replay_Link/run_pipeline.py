"""Windows front-end for native TAS-cadence/replay-context GigaLearn BC.
Does not change current model, does not promote models, does not run PPO."""
from __future__ import annotations
import argparse,datetime,json,pathlib,sys,uuid
from tas_replay_link import build
from install_reader import SRC, MARK

HERE=pathlib.Path(__file__).resolve().parent
CUR=HERE.parent
HUB=CUR.parent
PROJECT=HUB.parent
ROOT=PROJECT.parent

def find_replays():
    d=CUR/'run_data'
    candidates=sorted((p for p in d.iterdir() if p.is_dir() and (p/'replay_train.txt').is_file()
                       and (p/'replay_val.txt').is_file()),key=lambda p:p.stat().st_mtime,reverse=True) if d.exists() else []
    if not candidates:raise FileNotFoundError('No extracted replay dataset found under Curriculum_V2\\run_data. Run replay extraction first.')
    return candidates[0]

def find_linked():
    d=HERE/'linked_replays'
    c=sorted((p for p in d.iterdir() if p.is_dir() and (p/'manifest.json').is_file()),key=lambda p:p.stat().st_mtime,reverse=True) if d.exists() else []
    if not c:raise FileNotFoundError('No linked dataset; run 1_BUILD_LINKED_DATASET.bat')
    return c[0]

def find_seed():
    d=HUB/'experiments'/'replay_foundation_01'/'checkpoints'
    c=[p for p in d.iterdir() if p.is_dir() and p.name.isdecimal() and (p/'RUNNING_STATS.json').is_file()] if d.exists() else []
    if not c:raise FileNotFoundError('Cannot find replay_foundation_01 checkpoint: '+str(d))
    return max(c,key=lambda p:int(p.name))

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('link');b.add_argument('--dataset');b.add_argument('--tas');b.add_argument('--output');b.add_argument('--stride',type=int,default=8)
    t=sub.add_parser('train');t.add_argument('--dataset');t.add_argument('--seed');t.add_argument('--epochs',type=int,default=3)
    a=p.parse_args()
    if a.command=='link':
        name=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6]
        source=pathlib.Path(a.dataset) if a.dataset else find_replays()
        destination=pathlib.Path(a.output) if a.output else HERE/'linked_replays'/('linked_'+name)
        r=build(a.tas or ROOT/'data/tas',source,destination,stride=a.stride)
        print(json.dumps({k:r[k] for k in ('folder','replay_train_rows','replay_val_rows','tas_unique_files','tas_replay_cadence_matching_rows','matched_percent','mean_weight','max_weight')},indent=2))
        print('Validation replay file was copied UNMODIFIED. Do not edit it.')
    else:
        if not SRC.exists() or MARK not in SRC.read_text(encoding='utf8'):
            raise RuntimeError('C++ replay reader not patched. Run 2_INSTALL_READER.bat then 3_BUILD_REPLAY_BC.bat.')
        binary=PROJECT/'build_py311'/'Release'/'GigaLearnReplayBC.exe'
        if not binary.exists():raise FileNotFoundError('Missing compiled GigaLearnReplayBC.exe. Run build BAT.')
        if binary.stat().st_mtime<SRC.stat().st_mtime:raise RuntimeError('C++ reader changed after EXE was built; rebuild GigaLearnReplayBC first.')
        sys.path.insert(0,str(CUR))
        from curriculum_core import run_replay_bc
        ds=pathlib.Path(a.dataset) if a.dataset else find_linked()
        seed=pathlib.Path(a.seed) if a.seed else find_seed()
        # Fine tune conservatively from the replay model; lower LR than initial BC
        print('Fine-tuning from:',seed,flush=True)
        print('Using linked replay examples:',ds,flush=True)
        report=run_replay_bc(ds,seed_checkpoint=seed,epochs=a.epochs,lr=2e-5)
        print(json.dumps(report,indent=2))
        print('EXPERIMENTAL ONLY: compare in RocketSim before manually creating any Hub branch.')
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('LINKED TAS/REPLAY ERROR:',exc,file=sys.stderr)
        sys.exit(1)
