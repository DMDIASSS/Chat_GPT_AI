"""Sequential resumable A/B pilot. Budget includes collection and local evals."""
import copy,json,time
from pathlib import Path
from .runtime import ROOT,config,atomic_json,load


def run_pilot(minutes=90,block_minutes=10,seeds=(41011,41017,41023)):
    from .train import train
    from .evaluate import evaluate
    from .report import report
    if not 0<minutes<=90 or not 0<block_minutes<=10:raise ValueError('Pilot budget is at most 90 minutes, blocks at most 10')
    base=ROOT/'experiments/pilot001';base.mkdir(parents=True,exist_ok=True);begin=time.perf_counter();completed=[]
    print('PILOT: six sequential 10-minute training blocks, paired seeds, impulse 0 vs .05. No parallel trainers. Ctrl+C stops this pilot; 2_PAUSE pauses its active run too.',flush=True)
    stopped=False
    try:
        for seed in seeds:
            for weight in (0.,.05):
                folder=ROOT/'runs'/f'pilot_{seed}_impulse_{int(weight*100):02d}';prior=load(folder/'latest.pt') if (folder/'latest.pt').exists() else None
                already=prior['training_wall_seconds']/60 if prior else 0;remaining=min(block_minutes-already,minutes-(time.perf_counter()-begin)/60)
                if remaining<=0:continue
                cfg=copy.deepcopy(config());cfg['seed']=seed;cfg['rewards']['impulse']=weight;cfg['auto_evaluate_every']=10**15
                atomic_json(base/'active.json',{'run':folder.name,'seed':seed,'impulse_weight':weight,'status':'training'})
                train(folder,cfg if prior is None else None,minutes=remaining)
                if (folder/'STOP').exists():stopped=True;break
                state=load(folder/'latest.pt');completed.append({'run':folder.name,'seed':seed,'impulse_weight':weight,'learning_transitions':state['learning_transitions'],'training_wall_seconds':state['training_wall_seconds']})
                atomic_json(base/'progress.json',{'completed':completed,'session_seconds':time.perf_counter()-begin,'scope':'Early learning A/B pilot, not a strength confirmation'})
                if time.perf_counter()-begin>minutes*60-30:stopped=True;break
                evaluate(folder,4,10,seed=0xD1000000+seed,contexts=['center','diagonal_left','open_play'],automatic=True);report(folder)
            if stopped:break
    except KeyboardInterrupt:print('PILOT_INTERRUPTED: completed checkpoints retained.',flush=True)
    finally:atomic_json(base/'active.json',{'status':'paused_or_complete'})
    print('PILOT_PAUSED_OR_COMPLETE:',base,'; models saved in runs/pilot_*; compare reports, not just training rewards.',flush=True)
