"""Bounded real RocketSim/Nexto PPO validation without private league checkpoints.

Only writes a create-only JSON report. The trained actor is discarded; this
demonstrates integration and policy changes, not improved competitive skill.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

from afk_team_research import TeamObserver
from nexto_teacher import nexto_actions
from slater_ppo import trust_region_update
from slater_v041_core import NEXTO_SHA, sha256
from slater_v041_worker import ScriptedPoolEnv, run_episode
import slater_cycle9_native_ppo_v025 as base
import slater_v040_multirival as rollout


def validate(root, steps, seed,training_reset='mixed_ground',rlbot_delay=True,replay_starts=None):
    vendor=root/'vendor/nexto/nexto-model.pt'
    digest=sha256(vendor)
    if digest!=NEXTO_SHA:raise RuntimeError('Original Nexto SHA mismatch')
    torch.set_num_threads(2)
    torch.manual_seed(seed);np.random.seed(seed);random.seed(seed)
    actor=torch.jit.load(str(vendor),map_location='cpu').eval()
    teacher=torch.jit.load(str(vendor),map_location='cpu').eval()
    for p in teacher.parameters():p.requires_grad_(False)
    fixed={k:v.detach().clone() for k,v in teacher.state_dict().items()}
    before={k:v.detach().clone() for k,v in actor.state_dict().items()}
    critic=base.ValueNet()
    actions=nexto_actions()
    pool={'p_nexto':teacher}
    bank=None;replay_sha=None
    if replay_starts is not None:
        from slater_replay_starts import ReplayStartBank
        bank=ReplayStartBank(root/replay_starts)
        replay_sha=sha256(bank.path)
    env=ScriptedPoolEnv(actions,TeamObserver(),(teacher,teacher),teacher,
        max_steps=120,device='cpu',pool=pool,modes=('p_nexto',),
        training_reset=training_reset,rlbot_delay=rlbot_delay,
        replay_bank=bank,replay_probability=.5 if bank else .2)
    started=time.perf_counter()
    try:
        obs=env.reset(seed)
        rows,finished,_,_,trunc=rollout.collect_continuous(
            actor,critic,env,obs,seed,steps)
        if not np.isfinite(rows['reward']).all():raise FloatingPointError('Nonfinite rewards')
        metrics=trust_region_update(actor,teacher,critic,
            torch.optim.Adam(actor.parameters(),lr=2e-6),
            torch.optim.Adam(critic.parameters(),lr=1e-4),
            rows,2,64,.3,seed,target_kl=.02)
    finally:env.close()
    change=sum(float((v-before[k]).double().square().sum()) for k,v in actor.state_dict().items())
    if change<=0 or metrics['accepted_actor_epochs']==0:
        raise RuntimeError('No actor training executed successfully')
    if not all(torch.equal(v,fixed[k]) for k,v in teacher.state_dict().items()):
        raise RuntimeError('Frozen teacher was changed')
    if not all(torch.isfinite(p).all() for p in critic.parameters()):
        raise FloatingPointError('Critic became nonfinite')
    records=[]
    for episode_seed in (seed+10000,seed+10997):
        for side in ('blue','orange'):
            pair={}
            for name,policy in (('candidate',actor),('original_nexto',teacher)):
                pair[name]=run_episode(policy,'p_nexto',side,episode_seed,180,
                                       actions,teacher,teacher,teacher,pool,rlbot_delay=rlbot_delay)
            records.append({'seed':episode_seed,'side':side,**pair})
    if sha256(vendor)!=digest:raise RuntimeError('Original model changed on disk')
    if bank is not None and sha256(bank.path)!=replay_sha:raise RuntimeError('Replay bank changed')
    return {'status':'INTEGRATION_PASS_NOT_SKILL_EVIDENCE',
        'nexto_sha256':digest,'rollout_decisions':len(rows['action']),
        'completed_training_episodes':len(finished),'timeout_bootstraps':trunc,
        'replay_episodes_finished':sum(x['reset_source']=='replay' for x in finished),
        'replay_starts_sha256':replay_sha,
        'actor_squared_change':change,'metrics':metrics,'evaluation_pairs':records,
        'training_reset':training_reset,'rlbot_delay':rlbot_delay,
        'elapsed_seconds':time.perf_counter()-started,
        'scope':'CPU 1v1, scripted simulator rival; no V60/V70 validation or promotion.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    parser.add_argument('--steps',type=int,default=256)
    parser.add_argument('--seed',type=int,default=20261012)
    parser.add_argument('--training-reset',choices=('kickoff','mixed_ground'),default='mixed_ground')
    parser.add_argument('--rlbot-delay',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--replay-starts',help='Optional prepared rlgym-tools ReplayFrame bank')
    args=parser.parse_args(argv)
    if not 128<=args.steps<=4096 or not 1<=args.seed<2**31-20000:
        parser.error('Invalid bounded validation settings')
    root=Path(__file__).resolve().parent
    out=base.check_output(root/args.out,root,'.json')
    result=validate(root,args.steps,args.seed,args.training_reset,args.rlbot_delay,args.replay_starts)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,sort_keys=True,allow_nan=False)
    print('V041_INTEGRATION_PASS',out,flush=True)


if __name__=='__main__':main()
