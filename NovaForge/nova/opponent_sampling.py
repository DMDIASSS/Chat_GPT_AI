"""Optional, checkpointed concession-rate sampling for selector06 training.

This changes training opponents, never evaluation schedules or model promotion.
"""
from __future__ import annotations
from collections import deque
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from filelock import FileLock
from .core import atomic_json,sha256

POLICY=dict(schema='opponent-sampling-policy-v1',method='concessions-per-minute-v1',
    enabled=True,window_per_opponent=128,update_every_episodes=64,prior_seconds=120.,
    focus_fraction=.5,weight_update_fraction=.25,min_probability=.05,max_probability=.30)


def fingerprint(policy):
    return hashlib.sha256(json.dumps({k:v for k,v in policy.items() if k!='enabled'},sort_keys=True).encode()).hexdigest()


def policy_for(run,names):
    path=Path(run)/'opponent_sampling_policy.json'
    if not path.exists():return None
    policy=json.loads(path.read_text())
    if set(policy)!=set(POLICY) or policy['schema']!=POLICY['schema'] or policy['method']!=POLICY['method']:
        raise ValueError('Unsupported opponent-sampling policy')
    if not isinstance(policy['enabled'],bool):raise ValueError('Sampling enabled must be boolean')
    for key in ('window_per_opponent','update_every_episodes'):
        if type(policy[key]) is not int or not 1<=policy[key]<=10000:raise ValueError('Invalid sampling window/cadence')
    for key in ('prior_seconds','focus_fraction','weight_update_fraction','min_probability','max_probability'):
        if not isinstance(policy[key],(int,float)) or not np.isfinite(policy[key]):raise ValueError('Invalid sampling setting')
    if policy['prior_seconds']<=0 or not 0<=policy['focus_fraction']<=1 or not 0<policy['weight_update_fraction']<=1:
        raise ValueError('Invalid sampling smoothing')
    low=policy['min_probability'];high=policy['max_probability'];n=len(names)
    if not 0<=low<=high<=1 or n*low>1 or n*high<1:raise ValueError('Infeasible sampling probability bounds')
    return policy


def bounded_probabilities(values,low,high):
    """Proportional water-filling with explicit floor/cap and unit sum."""
    x=np.asarray(values,dtype=np.float64)
    if x.ndim!=1 or not len(x) or not np.isfinite(x).all() or (x<0).any() or x.sum()<=0:
        raise ValueError('Invalid sampling weights')
    if len(x)*low>1 or len(x)*high<1:raise ValueError('Infeasible sampling bounds')
    # Clipping scaled positive weights gives a monotone sum; solve for scale.
    x=np.maximum(x,1e-15);left=0.;right=1.
    while np.clip(right*x,low,high).sum()<1:right*=2
    for _ in range(80):
        middle=(left+right)/2
        if np.clip(middle*x,low,high).sum()<1:left=middle
        else:right=middle
    out=np.clip((left+right)/2*x,low,high)
    if not np.isclose(out.sum(),1,atol=1e-12):raise ValueError('Sampling normalization failed')
    return out


class ConcessionSampler:
    def __init__(self,base,policy,state=None):
        self.names=tuple(base);self.policy=copy.deepcopy(policy);self.identity=fingerprint(policy)
        x=np.array(list(base.values()),np.float64)
        self.base=bounded_probabilities(x/x.sum(),policy['min_probability'],policy['max_probability'])
        self.weights=self.base.copy();self.records={n:deque(maxlen=policy['window_per_opponent']) for n in self.names}
        self.episodes=0;self.updates=0
        if state is not None:
            if state.get('schema')!='concession-sampler-state-v1' or state.get('policy_sha256')!=self.identity or state.get('opponents')!=list(self.names):
                raise ValueError('Checkpoint sampling state does not match this policy/opponent pool')
            weights=np.array([state['weights'][n] for n in self.names],np.float64)
            if not np.isfinite(weights).all() or not np.isclose(weights.sum(),1,atol=1e-10) or (weights<policy['min_probability']-1e-12).any() or (weights>policy['max_probability']+1e-12).any():
                raise ValueError('Invalid checkpoint sampling probabilities')
            self.weights=weights;self.episodes=int(state['episodes']);self.updates=int(state['updates'])
            if self.episodes<0 or self.updates<0:raise ValueError('Invalid checkpoint sampling counters')
            for name in self.names:
                records=state['records'][name]
                if len(records)>policy['window_per_opponent']:raise ValueError('Sampling history exceeds its window')
                for goals,seconds in records:
                    if goals not in (0,1) or not np.isfinite(seconds) or seconds<=0:raise ValueError('Invalid checkpoint episode exposure')
                    self.records[name].append((int(goals),float(seconds)))

    def probabilities(self):return dict(zip(self.names,map(float,self.weights)))

    def rates(self):
        goals=np.array([sum(r[0] for r in self.records[n]) for n in self.names],np.float64)
        seconds=np.array([sum(r[1] for r in self.records[n]) for n in self.names],np.float64)
        global_rate=goals.sum()/seconds.sum() if seconds.sum()>0 else 0.
        prior=self.policy['prior_seconds']
        return (goals+prior*global_rate)/(seconds+prior)*60

    def observe(self,info):
        if 'outcome' not in info:return False
        name=info['opponent'].split(':')[0]
        if name not in self.records:raise ValueError('Episode opponent is outside the configured sampling pool')
        seconds=float(info['seconds'])
        if not np.isfinite(seconds) or seconds<=0:raise ValueError('Sampling requires positive simulated episode duration')
        # Training episodes terminate at their first goal; each loss is one concession.
        self.records[name].append((int(info['outcome']<0),seconds));self.episodes+=1
        if self.episodes%self.policy['update_every_episodes']:return False
        rates=self.rates();focus=rates/rates.sum() if rates.sum()>0 else self.base
        fraction=self.policy['focus_fraction'];target=(1-fraction)*self.base+fraction*focus
        target=bounded_probabilities(target,self.policy['min_probability'],self.policy['max_probability'])
        alpha=self.policy['weight_update_fraction'];self.weights=(1-alpha)*self.weights+alpha*target
        self.weights=bounded_probabilities(self.weights,self.policy['min_probability'],self.policy['max_probability'])
        self.updates+=1;return True

    def summary(self):
        return dict(enabled=True,method=self.policy['method'],policy_sha256=self.identity,episodes=self.episodes,updates=self.updates,
            weights=self.probabilities(),estimated_concessions_per_minute=dict(zip(self.names,map(float,self.rates()))),
            window_episodes={n:len(self.records[n]) for n in self.names},
            note='Training first-goal episodes; duration-normalized and shrunk toward pooled rate. Includes curriculum resets. Not an unbiased match-strength ranking.')

    def state(self):
        return dict(schema='concession-sampler-state-v1',policy_sha256=self.identity,opponents=list(self.names),
            episodes=self.episodes,updates=self.updates,weights=self.probabilities(),records={n:[list(r) for r in self.records[n]] for n in self.names})

    def metrics(self):
        result={'sampling/episodes':self.episodes,'sampling/updates':self.updates}
        for name,rate in zip(self.names,self.rates()):
            result['sampling/'+name+'_probability']=self.probabilities()[name]
            result['sampling/'+name+'_concessions_per_minute']=float(rate)
        return result


def save_state(model,sampler,run):
    model.opponent_sampling_state=sampler.state() if sampler is not None else None
    if sampler is not None:atomic_json(Path(run)/'opponent_sampling.json',dict(sampler.summary(),timesteps=int(model.num_timesteps)))
    elif (Path(run)/'opponent_sampling_policy.json').exists():atomic_json(Path(run)/'opponent_sampling.json',dict(enabled=False,timesteps=int(model.num_timesteps)))


def configure(run_name='selector06',enabled=True):
    from .research import run_path,stamp
    from .triad_selector import SIX_NAMES
    run=run_path(run_name)
    if not (run/'full.zip').exists():raise FileNotFoundError('Save the existing selector06 before enabling adaptive opponents')
    with FileLock(str(run/'train.lock'),timeout=0):
        cfg=json.loads((run/'config.json').read_text())
        if tuple(cfg.get('selector_experts',()))!=SIX_NAMES:raise ValueError('This sampler is enabled for the six-expert selector workflow')
        path=run/'opponent_sampling_policy.json';policy=policy_for(run,cfg['selector_opponents']) or copy.deepcopy(POLICY)
        policy['enabled']=bool(enabled)
        if path.exists() and json.loads(path.read_text())==policy:
            print('OPPONENT_SAMPLING_ALREADY', 'ENABLED' if enabled else 'DISABLED',flush=True);return
        record=dict(schema='sampling-policy-change-v1',policy=policy,source_checkpoint_sha256=sha256(run/'full.zip'))
        atomic_json(run/'research/sampling_changes'/f'{stamp()}.json',record);atomic_json(path,policy)
    print('OPPONENT_SAMPLING_'+('ENABLED' if enabled else 'DISABLED')+': resume with 27. Existing model and champion are unchanged.',flush=True)
