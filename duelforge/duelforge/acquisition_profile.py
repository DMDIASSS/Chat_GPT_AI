"""No-training CPU collection/reward benchmark. No user checkpoint is opened."""
import time
import numpy as np
from .runtime import ROOT,config,batch,atomic_json
from .acquisition import stage_config,AcquisitionBatch

def profile(arenas=128,decisions=90):
    rows=[]
    for stage in ('native','contact','possession','trajectory'):
        c=config();c.update(n_envs=arenas,native_threads=2)
        c['predictive']={'enabled':False};c['rewards']['impulse']=0
        if stage!='native':c=stage_config(c,stage)
        env=batch(c,seed=9117)
        if stage!='native':env=AcquisitionBatch(env,c,9117)
        rng=np.random.default_rng(144);raw=env.observe()
        ac=np.zeros((arenas,2),np.int64);start=time.perf_counter()
        for _ in range(decisions):
            # Action generation is identical across cases and included in cost.
            u=rng.random(raw['mask'].shape);u[~raw['mask']]=-1;ac[:]=u.argmax(-1)
            raw=env.step(ac)
        elapsed=time.perf_counter()-start
        row={'stage':stage,'arenas':arenas,'decisions_per_arena':decisions,
             'seconds':elapsed,'player_decisions_per_second':2*arenas*decisions/elapsed,
             'scope':'CPU native simulation + feature/reward/reset collection; excludes neural inference/PPO. Not end-to-end learner SPS.'}
        rows.append(row);print('ACQUISITION_PROFILE:',row,flush=True)
    output=ROOT/'acquisition_profile.json';atomic_json(output,{'training_started':False,'checkpoints_opened':False,'results':rows})
    return rows
