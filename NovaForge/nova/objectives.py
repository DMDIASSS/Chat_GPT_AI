"""Versioned, bounded objectives for controlled selector experiments.

Only quantities already exposed by the simulator are used. Changing an
objective requires a separate run; the default exactly preserves v1.8.1.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math

REGISTRY = {
    'current': dict(version='goal-potential-v1', goal=10., field=.35, distance=.1),
    'field_only': dict(version='goal-potential-v1', goal=10., field=.35, distance=0.),
    'goals_only': dict(version='goal-potential-v1', goal=10., field=0., distance=0.),
}


def objective(cfg):
    spec=copy.deepcopy(cfg.get('objective',REGISTRY['current']))
    if set(spec)!={'version','goal','field','distance'} or spec['version']!='goal-potential-v1':
        raise ValueError('Unknown objective definition/version')
    for key in ('goal','field','distance'):
        value=spec[key]
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<0:
            raise ValueError('Objective coefficients must be finite nonnegative numbers')
        spec[key]=float(value)
    if not 0<spec['goal']<=100 or max(spec['field'],spec['distance'])>10:
        raise ValueError('Objective coefficients exceed the research bounds')
    if cfg.get('rewards')=='sparse':spec.update(field=0.,distance=0.)
    return spec


def definition(cfg):
    spec=objective(cfg)
    result=dict(spec=spec, gamma=cfg['ppo']['gamma'], decision_ticks=8,
        equation='goal*outcome + gamma*Phi(next) - Phi(old)',
        potential='field*team_relative_ball_y/5120 - distance*min(car_ball_distance,12000)/6000',
        terminal_potential=0, timeout_potential='retained for value bootstrap')
    result['sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result
