"""Paired fixed-seed Soccar matches; never supplies training labels."""
import numpy as np
import torch
from replay_hybrid.env import World
from replay_hybrid.rollout import greedy,opponents


def paired_summary(rows,seconds):
    differences=np.array([(row['candidate_goal_difference']-row['source_goal_difference'])*60/seconds for row in rows],float)
    rng=np.random.default_rng(99173)
    means=differences[rng.integers(len(differences),size=(4096,len(differences)))].mean(1)
    return {'independent_seed_pairs':len(rows),'paired_goal_difference_per_minute':float(differences.mean()),
        'paired_bootstrap_95pct_interval':np.percentile(means,[2.5,97.5]).tolist(),
        'candidate_goal_difference':sum(row['candidate_goal_difference'] for row in rows),
        'source_goal_difference':sum(row['source_goal_difference'] for row in rows)}


@torch.inference_mode()
def evaluate(candidate,source,*,device='cpu',games=6,seconds=120,team_size=1,seed=800000,nexto=None,stop=None):
    if not 2<=games<=64 or not 1<=seconds<=600:raise ValueError('Invalid evaluation budget')
    candidate.eval();source.eval();worlds=[];labels=[]
    kinds=['source','chaser']+(['nexto'] if nexto is not None else [])
    for i in range(games):
        for label in ('source','candidate'):
            world=World(seed+i*7919,team_size,curriculum=False,episode_seconds=seconds+1,
                opponents=(kinds[i%len(kinds)],),fixed_orange=bool((i//len(kinds))%2))
            worlds.append(world);labels.append(label)
    scores=np.zeros(len(worlds),int);goals=np.zeros((len(worlds),2),int)
    rng_state=np.random.get_state() # World randomness is local; no actor sampling here.
    try:
        for step in range(round(seconds*120/8)):
            if stop is not None and stop():return {'interrupted':True,'scope':'Incomplete evaluation; no selection or strength metric produced'}
            views=[world.observe() for world in worlds]
            commands=opponents(worlds,views,{'source':source},device,nexto)
            for label,model in (('source',source),('candidate',candidate)):
                rows=[(i,aid,views[i][aid]) for i,world in enumerate(worlds) if labels[i]==label for aid in world.ours]
                chunks=greedy(model,[row[2] for row in rows],device)
                for (i,aid,_),chunk in zip(rows,chunks):commands[i][aid]=chunk[:8].copy()
            for i,(world,command) in enumerate(zip(worlds,commands)):
                _,done,_,_,info=world.step(command)
                if done:
                    scored=bool(info['goal']);scores[i]+=1 if scored else -1;goals[i,0 if scored else 1]+=1
            if step and step%900==0:print('HYBRID_EVAL:',step*8/120,'/',seconds,'simulated seconds',flush=True)
    finally:
        for world in worlds:world.close()
        np.random.set_state(rng_state)
    rows=[{'seed':seed+i*7919,'orange':bool((i//len(kinds))%2),'opponent':kinds[i%len(kinds)],
        'source_goal_difference':int(scores[2*i]),'candidate_goal_difference':int(scores[2*i+1]),
        'source_goals':goals[2*i].tolist(),'candidate_goals':goals[2*i+1].tolist()} for i in range(games)]
    return {'schema':'replay-hybrid-paired-evaluation-v1','seconds_per_match':seconds,'team_size':team_size,
        'rows':rows,**paired_summary(rows,seconds),
        'by_opponent':{kind:paired_summary([row for row in rows if row['opponent']==kind],seconds) for kind in kinds if any(row['opponent']==kind for row in rows)},
        'scope':'Instant simulation, greedy policy without search or scripted kickoff. No live latency or general strength claim.'}
