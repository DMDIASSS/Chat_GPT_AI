"""Four complete PPO updates per arm on disposable models, no user weights."""
import json,copy,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from duelforge.runtime import ROOT,config,load,atomic_json
from duelforge.train import train

def run():
    c=config(ROOT/'config_potential.json');parent=ROOT/'runs/duel02/latest.pt'
    if parent.is_file():
        old=load(parent)['config']
        for k in ('n_envs','native_threads','torch_threads','width'):c[k]=old[k]
        c['ppo']['steps']=old['ppo']['steps']
    c['wandb']['enabled']=False;c['auto_evaluate_every']=10**12;c['league']['snapshot_every']=10**12;c['league']['history_fraction']=0;c['league']['nexto_fraction']=0
    base=ROOT/'benchmarks'/('potential_cost_'+str(time.time_ns()));rows=[]
    for enabled in (False,True):
        cfg=copy.deepcopy(c);cfg['predictive']['enabled']=enabled;folder=base/('predictive' if enabled else 'legacy')
        train(folder,cfg,minutes=1,max_updates=4)
        if (folder/'STOP').exists():raise KeyboardInterrupt('Reward benchmark cancelled; original runs preserved')
        metrics=[json.loads(v) for v in (folder/'metrics.jsonl').read_text().splitlines()]
        if len(metrics)<4:raise RuntimeError('Benchmark did not complete four updates; inspect time/memory guard output. Original runs preserved.')
        rows.append({'predictive':enabled,'completed_updates':len(metrics),'median_learner_sps':float(np.median([v['speed/learner_transitions_per_second'] for v in metrics[1:]]))})
    result={'rows':rows,'scope':'Disposable fresh models; same hardware/network/arenas/epochs. Per-update processing rate excludes initialization/saving. This measures reward cost, not learning benefit.'};atomic_json(ROOT/'results/potential_cost_local.json',result);print(json.dumps(result,indent=2));return result
if __name__=='__main__':run()
