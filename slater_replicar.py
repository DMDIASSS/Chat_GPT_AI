"""Replicar v2 Parquet -> current native demonstration/reset pipeline.

Only current physics, controls and freshness are used. Future/final outcomes
are deliberately not consulted. Control provenance remains in the report.
"""
from collections import Counter
import hashlib
import numpy as np


def frames(path,info=None):
    import replicar
    import replicar.rlgym
    f=replicar.read(path)
    required={'state','game','updates'}
    if not required.issubset(f.groups):raise ValueError('Replicar input needs state, game and updates groups')
    a=f.arrays();counts=Counter();players=f.players
    if not 2<=len(players)<=6 or sorted(p['index'] for p in players)!=list(range(len(players))):raise ValueError('Unsupported Replicar roster')
    controls_names=('throttle','steer','pitch','yaw','roll','jump','boost','handbrake')
    for key in ['clock_phase','sim_tick','car_air_controls_source','car_ground_controls_source']+[f'car_controls_{name}' for name in controls_names]:
        if key not in a:raise ValueError('Replicar input lacks '+key)
    if info is not None:
        replay_sha=f.header.get('replay_sha256')
        if not replay_sha:raise ValueError('Missing original replay SHA provenance')
        info['original_replay_sha']=replay_sha
        info['group']=hashlib.sha256(('original_replay:'+replay_sha).encode()).hexdigest()
        info['replicar_header']={k:f.header.get(k) for k in ('format_version','rows','tick_step','platform','replay_sha256')}
        info['control_provenance']=counts
    ages=a.get('car_seconds_since_update')
    if ages is None and 'car_ticks_since_update' in a:ages=a['car_ticks_since_update']/120.
    if ages is None:raise ValueError('No car update-age provenance')
    for row in range(len(a['sim_tick'])):
        if a['clock_phase'][row] not in ('running','expired'):continue
        state=replicar.rlgym.game_state(f,row)
        controls={};update_age={}
        for p in players:
            aid=p['index']
            if aid not in state.cars:continue
            car=state.cars[aid]
            air=str(a['car_air_controls_source'][row,aid]);ground=str(a['car_ground_controls_source'][row,aid])
            counts['air_'+air]+=1;counts['ground_'+ground]+=1
            if ground not in ('network','schedule','dodge'):continue
            if not car.on_ground and air in ('none','', 'None'):continue
            raw=np.array([a[f'car_controls_{name}'][row,aid] for name in controls_names],np.float32)
            if not np.isfinite(raw).all():continue
            controls[aid]=raw;update_age[aid]=float(ages[row,aid])
        yield state,controls,update_age


def audit(path):
    info={};rows=players=0
    for state,controls,ages in frames(path,info):rows+=1;players+=len(controls)
    return {**info,'active_rows':rows,'players_with_controls':players,'warning':'Fitted aerial controls are reconstructed, not authentic recorded stick inputs.'}
