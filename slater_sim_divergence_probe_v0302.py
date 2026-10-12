"""Diagnose RocketSim reproducibility: same kickoff and fixed/greedy inputs.

No training or writes. Uses fresh arena each repeat. If fixed-action physics
itself diverges on the same state, do not trust paired RocketSim eval yet.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
from pathlib import Path
import numpy as np
import torch

import slater_fullmatch_eval_v0302 as fm
import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_paired_eval_v026_fixed as paired


def observation_hash(obs):
    h=hashlib.sha256()
    for x in obs:
        a=np.ascontiguousarray(x,dtype='<f4')
        h.update(a.tobytes())
    return h.hexdigest()[:16]


def trace(side,actor,nexto,actions,seed,steps,mode):
    env=fm.IsolatedKickoffEnv(side,actions,nexto,max_steps=steps)
    try:
        obs,_=fm.seeded_reset(env,seed)
        start=fm.detailed_kickoff_signature(env)
        rows=[]
        for step in range(steps):
            a=0 if mode=='fixed_action_0' else paired.greedy_action(actor,obs,'cpu')
            before=observation_hash(obs)
            obs,_,done,info=env.step(a)
            rows.append({'step':step,'student_action':a,
                         'opponent_controls_hash':hashlib.sha256(
                            np.ascontiguousarray(env.previous[
                                'orange-0' if side=='blue' else 'blue-0'],
                                dtype='<f4').tobytes()).hexdigest()[:16],
                         'before_obs_hash':before,
                         'state_hash':fm.detailed_kickoff_signature(env),
                         'touches':int(info['student_touches']),
                         'opp_touches':int(info['opponent_touches']),
                         'outcome':int(info['outcome'])})
            if done:break
        return start,rows
    finally:env.close()


def first_difference(a,b):
    if a[0]!=b[0]:return {'kind':'start','first':a[0],'repeat':b[0]}
    for i,(x,y) in enumerate(zip(a[1],b[1])):
        if x!=y:
            diff={k:{'first':x.get(k),'repeat':y.get(k)} for k in x if x.get(k)!=y.get(k)}
            return {'kind':'step','step':i,'diff':diff}
    if len(a[1])!=len(b[1]):return {'kind':'length','first':len(a[1]),'repeat':len(b[1])}
    return None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--steps',type=int,default=300)
    p.add_argument('--seed',type=int,default=1876359103)
    args=p.parse_args()
    if not(5<=args.steps<=1200 and 1<=args.seed<2**31):p.error('invalid steps or seed')
    from slater_research.checkpoint import CYCLE9,CYCLE9_SHA,cycle9_pair
    from nexto_teacher import nexto_actions
    root=Path.cwd().resolve()
    source=root/CYCLE9
    teacher_source=root/'vendor'/'nexto'/'nexto-model.pt'
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(teacher_source)!=fm.NEXTOSHA:
        raise RuntimeError('protected model checksums mismatch')
    torch.set_num_threads(2)
    _,actor=cycle9_pair(root)
    actor.eval()
    nexto=torch.jit.load(str(teacher_source),map_location='cpu')
    nexto.eval()
    actions=np.stack([np.asarray(nexto_actions()[i],dtype=np.float32).reshape(8) for i in range(90)])
    for side in ('blue','orange'):
        for mode in ('fixed_action_0','greedy'):
            a=trace(side,actor,nexto,actions,args.seed,args.steps,mode)
            b=trace(side,actor,nexto,actions,args.seed,args.steps,mode)
            diff=first_difference(a,b)
            print('PROBE',json.dumps({'side':side,'mode':mode,'deterministic':diff is None,
                    'first_divergence':diff,'run_lengths':[len(a[1]),len(b[1])],
                    'start_hashes':[a[0],b[0]]}),flush=True)
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(teacher_source)!=fm.NEXTOSHA:
        raise RuntimeError('PROTECTED_MODEL_CHANGED')
    print('PROBE_COMPLETE NO_CHECKPOINT_WRITES',flush=True)


if __name__=='__main__':main()
