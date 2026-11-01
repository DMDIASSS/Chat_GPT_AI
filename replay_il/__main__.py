r"""Run from the project root: .venv\Scripts\python.exe -m replay_il ..."""
import argparse,json,sys
from pathlib import Path
from replay_il.data import ROOT
from slater_v041_core import atomic_json,read_json

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['preflight','prepare','train','resume','run','test','pause','status','download-duos','planner-benchmark','tas-audit'])
    p.add_argument('--tas',type=Path,default=ROOT/'data/tas')
    p.add_argument('--inputs',nargs='+',default=[str(ROOT/'data/replays/ranked-duels'),str(ROOT/'data/replays/ranked-doubles')])
    p.add_argument('--dataset',type=Path,default=ROOT/'data/isolated/replay_imitation/dataset01')
    p.add_argument('--run',default='replay_scratch01');p.add_argument('--epochs',type=int,default=10)
    p.add_argument('--batch-size',type=int,default=64);p.add_argument('--lr',type=float,default=2e-4)
    p.add_argument('--device',choices=['auto','cpu','cuda'],default='auto')
    p.add_argument('--wandb-mode',choices=['online','offline','disabled'],default='online')
    p.add_argument('--wandb-project',default='slater-replay-imitation');p.add_argument('--wandb-entity',default='')
    p.add_argument('--max-replays',type=int,default=3000);p.add_argument('--max-samples',type=int,default=500000)
    p.add_argument('--download-count',type=int,default=100);p.add_argument('--candidates',type=int,default=64)
    a=p.parse_args(argv)
    if a.command=='tas-audit':
        from replay_il.tas import audit
        audit(a.tas,ROOT/'data/isolated/replay_imitation/tas_audit.json');return
    if not a.run or len(a.run)>50 or not a.run.replace('_','').replace('-','').isalnum():p.error('Invalid run name')
    folder=ROOT/'data/isolated/replay_imitation/runs'/a.run
    if a.command=='pause':
        if folder.exists():(folder/'pause.flag').touch()
        if a.dataset.exists():(a.dataset/'pause.flag').touch()
        if not folder.exists() and not a.dataset.exists():raise ValueError('No such run/dataset')
        print('Pause requested. Preparation finishes the current replay; training saves at a safe boundary.');return
    if a.command=='status':print(json.dumps(read_json(folder/'progress.json',{}),indent=2));return
    if a.command=='download-duos':
        from replay_il.fetch import download
        print(json.dumps(download(ROOT/'data/replays/ranked-doubles',count=a.download_count),indent=2));return
    if a.command in ('preflight','run'):
        import importlib.util,torch,shutil
        from replay_il.model import ChunkPolicy
        required=['torch','numpy','RocketSim','rlgym','rlgym_tools','pyarrow']
        missing=[key for key in required if importlib.util.find_spec(key) is None]
        if missing:raise RuntimeError('Install replay_il/requirements.txt in the project .venv. Missing: '+', '.join(missing))
        print('INITIALIZATION: fresh random weights; no pretrained models loaded')
        print('MODEL:',json.dumps(ChunkPolicy().describe()))
        print('CUDA:',torch.cuda.is_available(),'free disk GiB:',round(shutil.disk_usage(ROOT).free/1024**3,1))
        for path in a.inputs:
            files=list(Path(path).rglob('*.replay'));print('REPLAYS:',path,len(files))
        if a.command=='preflight':return
    if a.command in ('prepare','run'):
        from replay_il.data import prepare
        if (a.dataset/'manifest.json').exists():
            from replay_il.train import Dataset
            Dataset(a.dataset);print('Reusing verified dataset. Use a new --dataset path to add/change replay inputs.')
        else:prepare(a.inputs,a.dataset,max_replays=a.max_replays,max_samples=a.max_samples)
        if a.command=='prepare':return
    if a.command in ('train','resume','run'):
        from replay_il.train import train
        resume=a.command=='resume' or a.command=='run' and (folder/'latest.pt').exists()
        if resume:
            saved=read_json(folder/'protocol.json',{})
            a.batch_size=saved.get('batch_size',a.batch_size);a.lr=saved.get('lr',a.lr)
        train(a.dataset,folder,epochs=a.epochs,batch_size=a.batch_size,lr=a.lr,device=a.device,resume=resume,
            wandb={'mode':a.wandb_mode,'project':a.wandb_project,'entity':a.wandb_entity});return
    if a.command=='test':
        from replay_il.train import Dataset,evaluate
        from replay_il.planner import load
        from slater_v041_core import sha256
        report=folder/'heldout_test.json'
        identity={'checkpoint_sha256':sha256(folder/'best.pt'),'dataset_sha256':sha256(a.dataset/'manifest.json')}
        if report.exists():
            prior=read_json(report)
            if prior['identity']==identity:print(json.dumps(prior,indent=2));return
            raise ValueError('Held-out test was already used by another checkpoint. Do not repeatedly tune on this test split.')
        model,book=load(folder);data=Dataset(a.dataset,book)
        result={'identity':identity,'metrics':evaluate(model,data,'test','cpu',a.batch_size),'competitive_improvement_verified':False}
        atomic_json(report,result);print(json.dumps(result,indent=2));return
    if a.command=='planner-benchmark':
        import numpy as np
        from replay_il.planner import load,Planner
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
        model,book=load(folder);engine=RocketSimEngine(rlbot_delay=False)
        try:
            state=engine.create_base_state();FixedTeamSizeMutator(1,1).apply(state,{});KickoffMutator().apply(state,{})
            state=engine.set_state(state,{})
            planner=Planner(model,book,candidates=a.candidates)
            try:_,result=planner.choose(state,{k:np.zeros(8,np.float32) for k in state.cars},next(iter(state.cars)))
            finally:planner.close()
        finally:engine.close()
        atomic_json(folder/'planner_benchmark.json',result);print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,FileNotFoundError,FileExistsError) as error:
        print('STOPPED:',str(error),file=sys.stderr);sys.exit(1)
