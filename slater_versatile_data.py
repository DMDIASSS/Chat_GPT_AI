"""Cached, replay-grouped native demonstrations and physics-checked TAS captures.

rlgym-tools supplies parsing, inverse aerial controls and feasible action labels.
Actor observations use only current state and previous controls, never outcomes.
"""
from __future__ import annotations
import argparse
from collections import Counter, OrderedDict
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from afk_team_research import TeamObserver
from nexto_teacher import nexto_actions
from slater_v041_core import atomic_json,read_json,sha256,process_lock

ROOT=Path(__file__).resolve().parent
BUCKETS=('general','close_control','defense','aerial','attack','low_boost')

def native_observation(obs):
    # The bundled traced attention adds its mask directly to logits. A positive
    # boolean-style 1 boosts placeholder players rather than hiding them.
    q,kv,mask=obs
    return q,kv,np.where(mask>0,-10000.,mask).astype(np.float32)

def partition(digest):
    n=int(digest[:8],16)%100
    return 'train' if n<70 else 'validation' if n<85 else 'test'

def valid_state(state):
    if state.goal_scored or not 2<=len(state.cars)<=6:return False
    teams=[c.team_num for c in state.cars.values()]
    if teams.count(0)!=teams.count(1):return False
    if not np.allclose([state.config.gravity,state.config.boost_consumption,state.config.dodge_deadzone],[1,1,.5]):return False
    if not np.isfinite(state.boost_pad_timers).all() or np.any(state.boost_pad_timers<0):return False
    for p in [state.ball]+[c.physics for c in state.cars.values()]:
        if not all(np.isfinite(x).all() for x in (p.position,p.linear_velocity,p.angular_velocity,p.rotation_mtx)):return False
        if not np.allclose(p.rotation_mtx.T@p.rotation_mtx,np.eye(3),atol=.02):return False
        if np.linalg.det(p.rotation_mtx)<.98:return False
        if abs(p.position[0])>4100 or abs(p.position[1])>5120 or not 0<p.position[2]<2045:return False
    return all(not c.is_demoed and np.isfinite(c.boost_amount) and 0<=c.boost_amount<=100 for c in state.cars.values())

def label(car,controls,max_cost=.55):
    from rlgym_tools.rocket_league.replays.pick_action import get_best_action_options
    table=nexto_actions();controls=np.asarray(controls,dtype=np.float32)
    if controls.shape!=(8,) or not np.isfinite(controls).all() or np.any(np.abs(controls)>1.001):return None
    if not np.all(np.isclose(controls[5:],0,atol=.001)|np.isclose(controls[5:],1,atol=.001)):return None
    probs=get_best_action_options(car,controls,table,greedy=True)
    if probs.shape!=(90,) or not np.isfinite(probs).all() or probs.sum()<=0:return None
    # Do not penalize irrelevant ground rotation / airborne steering fields.
    weights=np.array([1,1,1,1,1,6,6,2],dtype=np.float32)
    if car.on_ground and not controls[5]:weights[2:5]=0
    else:weights[1]=0;weights[7]=0
    if car.boost_amount<=0:weights[6]=0
    if not (car.on_ground or car.is_jumping or car.has_flip):weights[5]=0
    cost=float(np.min(np.sum((table[probs>0]-controls)**2*weights,axis=1)))
    if cost>max_cost:return None
    return probs.astype(np.float32),float(np.exp(-cost/.35))

def capture_frames(path):
    """Exact capture: state at each 8-tick decision plus controls for every car.

    Legacy TAS .data has no matched states and is deliberately not accepted.
    """
    from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state
    from rlgym.rocket_league.sim import RocketSimEngine
    with np.load(path,allow_pickle=False) as z:
        states=z['states'];controls=z['controls'];skip=int(z['tick_skip'])
    if skip!=8 or len(states)!=len(controls)+1:raise ValueError('Capture requires N+1 states, N controls, tick_skip=8')
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        for i,raw in enumerate(controls):
            state=deserialize_game_state(states[i].copy());after=deserialize_game_state(states[i+1].copy())
            ids=sorted(state.cars)
            if raw.shape!=(len(ids),8) or set(after.cars)!=set(ids):raise ValueError('Capture roster/control mismatch')
            if after.tick_count-state.tick_count!=8:raise ValueError('Capture timing is not eight physics ticks')
            if not valid_state(state) or not np.isfinite(raw).all() or np.any(np.abs(raw)>1.001):continue
            engine.set_state(state,{})
            predicted=engine.step({aid:np.repeat(raw[j][None],8,axis=0) for j,aid in enumerate(ids)},{})
            ps=[predicted.ball]+[predicted.cars[k].physics for k in ids]
            ts=[after.ball]+[after.cars[k].physics for k in ids]
            pos=max(float(np.linalg.norm(p.position-t.position)) for p,t in zip(ps,ts))
            vel=max(float(np.linalg.norm(p.linear_velocity-t.linear_velocity)) for p,t in zip(ps,ts))
            rot=max(float(np.linalg.norm(p.rotation_mtx-t.rotation_mtx)) for p,t in zip(ps,ts))
            if pos>3 or vel>20 or rot>.06:continue
            yield state,{aid:raw[j] for j,aid in enumerate(ids)},dict.fromkeys(ids,0.)
    finally:engine.close()

def replay_frames(path,info=None):
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    replay=ParsedReplay.load(path)
    if info is not None:
        match_id=replay.metadata.get('game',{}).get('id')
        if match_id:info['group']=hashlib.sha256(('replay:'+str(match_id)).encode()).hexdigest()
    for frame in replay_to_rlgym(replay):
        # Pauses/terminal/future scoreboard fields are neither labels nor inputs.
        if frame.scoreboard.go_to_kickoff or frame.scoreboard.is_over or frame.scoreboard.kickoff_timer_seconds>0:continue
        yield frame.state,frame.actions,frame.update_age

def parse_one(job):
    path,digest,out,cfg=job
    path=Path(path);out=Path(out)
    if out.exists():
        with np.load(out,allow_pickle=False) as z:group=str(z['group']);original_sha=str(z['original_replay_sha'])
        return {'path':str(out),'sha256':sha256(out),'source_sha':digest,'group':group,'original_replay_sha':original_sha,'cached':True}
    info={'group':digest,'original_replay_sha':digest}
    if path.suffix=='.npz':
        with np.load(path,allow_pickle=False) as z:
            if 'source_group' in z:info['group']=hashlib.sha256(('capture:'+str(z['source_group'])).encode()).hexdigest()

    from afk_replay_tas_learning import replay_bucket
    from rlgym_tools.rocket_league.misc.serialize import serialize_game_state
    observer=TeamObserver();rng=np.random.default_rng(int(digest[:12],16))
    # Reservoirs span the entire match rather than only its first 500 frames.
    pools=[[] for _ in BUCKETS];seen=Counter();stats=Counter();past={};last_tick=None;roster=None
    cap=max(8,cfg['per_replay']//len(BUCKETS))
    if path.suffix=='.parquet':
        from slater_replicar import frames as replicar_frames
        frames=replicar_frames(path,info)
    else:frames=capture_frames(path) if path.suffix=='.npz' else replay_frames(path,info)
    for index,(state,actions,ages) in enumerate(frames):
        current={k:np.asarray(v,dtype=np.float32).copy() for k,v in actions.items()}
        if last_tick is not None and state.tick_count<last_tick:past={}
        last_tick=state.tick_count
        if index%cfg['every'] or not valid_state(state):past=current;continue
        if roster is None:roster=len(state.cars)
        if len(state.cars)!=roster:past=current;continue
        observations=observer.observe(state,past)
        for aid,car in state.cars.items():
            age=float(ages.get(aid,999))
            if aid not in current or not np.isfinite(age) or not 0<=age<=cfg['max_age']:stats['stale_or_missing']+=1;continue
            result=label(car,current[aid],cfg['max_cost'])
            if result is None:stats['uncertain']+=1;continue
            target,weight=result;bucket=BUCKETS.index(replay_bucket(state,car))
            q,kv,mask=native_observation(observations[aid])
            if not all(np.isfinite(a).all() for a in (q,kv,mask)):stats['invalid_obs']+=1;continue
            row=(q,kv,mask,target,weight,bucket,serialize_game_state(state))
            seen[bucket]+=1;pool=pools[bucket]
            if len(pool)<cap:pool.append(row)
            else:
                slot=int(rng.integers(seen[bucket]))
                if slot<cap:pool[slot]=row
        past=current
    rows=[r for pool in pools for r in pool]
    if not rows:raise ValueError('No usable active gameplay/state-aligned action samples')
    out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_suffix('.partial')
    with tmp.open('wb') as f:
        np.savez_compressed(f,group=info['group'],original_replay_sha=info['original_replay_sha'],**{k:np.asarray([row[j] for row in rows],dtype=dtype) for j,(k,dtype) in
            enumerate([('q',np.float32),('kv',np.float32),('mask',np.float32),('target',np.float32),
                       ('weight',np.float32),('bucket',np.uint8),('states',np.float32)])})
    tmp.replace(out)
    return {'path':str(out),'sha256':sha256(out),'source_sha':digest,'group':info['group'],'original_replay_sha':info['original_replay_sha'],'samples':len(rows),'cached':False,
            'buckets':dict(Counter(BUCKETS[r[5]] for r in rows)),'filtered':dict(stats),
            'kind':'verified_simulator_capture' if path.suffix=='.npz' else 'replicar_reconstructed_controls' if path.suffix=='.parquet' else 'inferred_replay_controls',
            'replicar_provenance':info.get('replicar_header'),'control_provenance':dict(info.get('control_provenance',{}))}

def prepare(inputs,out,*,workers=2,per_replay=1024,max_replays=100,max_samples=100000,every=4):
    from afk_replay_tas_learning import expand_files
    out=Path(out).resolve()
    if not out.is_relative_to(ROOT/'data/isolated'):raise ValueError('Dataset output must be under data/isolated')
    if not 1<=workers<=8 or not 48<=per_replay<=10000 or not 1<=every<=30 or not 1<=max_replays<=10000 or not 100<=max_samples<=2000000:raise ValueError('Invalid preparation limits')
    files=expand_files(inputs,'.replay')+expand_files(inputs,'.npz')+expand_files(inputs,'.parquet')
    files=[p for p in files if p.name!='index.parquet']
    if not files:raise ValueError('No .replay or aligned capture .npz files found. Raw TAS .data requires a matched state capture.')
    unique={}
    for f in files:unique.setdefault(sha256(f),f)
    sources=list(unique.items())[:max_replays]
    cfg={'per_replay':per_replay,'max_age':.05,'max_cost':.55,'every':every,
         'parser_version':version('rlgym-tools'),'code_sha':sha256(__file__),
         'runtime':{n:version(n) for n in ('rlgym-rocket-league','rocketsim','numpy','pandas','pyarrow')},
         'replicar_adapter_sha':sha256(ROOT/'slater_replicar.py')}
    identity=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()
    protocol={'config':cfg,'sources':[d for d,_ in sources],'max_samples':max_samples}
    out.mkdir(parents=True,exist_ok=True)
    with process_lock(out/'prepare.lock'):
        existing=read_json(out/'manifest.json')
        if existing:
            if existing['protocol']!=protocol:raise ValueError('Dataset inputs/settings changed; choose a new --out folder')
            DemoDataset(out);print('VERSATILE_DATASET_REUSED',out,flush=True);return existing
        jobs=[(str(f),d,str(out/'shards'/(d+'_'+identity[:12]+'.npz')),cfg) for d,f in sources]
        records=[];errors=[];started=time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(parse_one,j) for j in jobs]
            for n,(future,(digest,source)) in enumerate(zip(futures,sources),1):
                try:
                    record=future.result();record.update(partition=partition(record['group']),source=str(source))
                    records.append(record)
                except Exception as e:errors.append({'source':str(source),'error':str(e)})
                atomic_json(out/'parse_progress.json',{'completed':n,'total':len(jobs),'records':records,'errors':errors})
                print('VERSATILE_PARSE',n,'/',len(jobs),'usable',len(records),'errors',len(errors),
                      'seconds',round(time.perf_counter()-started,1),flush=True)
        # Raw replay plus its converted Parquet must never enter separate splits.
        canonical={r['original_replay_sha']:r['group'] for r in records if r['source'].endswith('.replay')}
        unique_records={}
        for r in sorted(records,key=lambda r:(not r['source'].endswith('.parquet'),r['source_sha'])):
            original=r['original_replay_sha'];r['group']=canonical.get(original,r['group']);r['partition']=partition(r['group'])
            unique_records.setdefault(original,r)
        records=sorted(unique_records.values(),key=lambda r:r['source_sha']);sizes=[];remaining=max_samples
        for r in records:
            with np.load(r['path'],allow_pickle=False) as z:r['samples']=len(z['weight'])
            take=min(r['samples'],remaining);sizes.append(take);remaining-=take
        if sum(sizes)<100:raise ValueError('Fewer than 100 usable examples; see parse_progress.json')
        split_counts=Counter();split_groups={name:set() for name in ('train','validation','test')}
        for r,n in zip(records,sizes):
            if n:split_counts[r['partition']]+=1;split_groups[r['partition']].add(r['group'])
        if len(split_groups['train'])<2 or not split_groups['validation'] or not split_groups['test']:
            raise ValueError('Need at least 2 train, 1 validation, 1 untouched test source; add independent replays/captures')
        shapes={'q':(1,32),'kv':(41,24),'mask':(41,),'target':(90,),'weight':(),'bucket':(),'split':(),'source_id':()}
        total=sum(sizes);maps={}
        for key,shape in shapes.items():
            dtype=np.int32 if key=='source_id' else np.uint8 if key in ('bucket','split') else np.float32
            maps[key]=np.lib.format.open_memmap(out/(key+'.npy'),mode='w+',dtype=dtype,shape=(total,*shape))
        offset=0;group_ids={group:i for i,group in enumerate(sorted({r['group'] for r in records}))}
        for source_id,(record,count) in enumerate(zip(records,sizes)):
            if not count:continue
            with np.load(record['path'],allow_pickle=False) as z:
                indices=np.linspace(0,len(z['weight'])-1,count,dtype=int)
                for key in ('q','kv','mask','target','weight','bucket'):maps[key][offset:offset+count]=z[key][indices]
            maps['split'][offset:offset+count]={'train':0,'validation':1,'test':2}[record['partition']]
            maps['source_id'][offset:offset+count]=group_ids[record['group']];offset+=count
        for array in maps.values():array.flush()
        hashes={k:sha256(out/(k+'.npy')) for k in maps}
        manifest={'protocol':protocol,'samples':total,'sources':records,'errors':errors,'arrays':hashes,
                  'source_partitions':dict(split_counts),'label_warning':'Replay controls are inferred, not exact human inputs. No rank certification.'}
        atomic_json(out/'manifest.json',manifest);DemoDataset(out)
        print('VERSATILE_DATASET_READY',out,'samples',total,dict(split_counts),flush=True);return manifest

class DemoDataset:
    def __init__(self,path):
        self.path=Path(path);self.manifest=read_json(self.path/'manifest.json')
        if not self.manifest:raise ValueError('Missing prepared dataset manifest')
        self.arrays={}
        for key,digest in self.manifest['arrays'].items():
            f=self.path/(key+'.npy')
            if sha256(f)!=digest:raise ValueError('Dataset array changed: '+key)
            self.arrays[key]=np.load(f,mmap_mode='r',allow_pickle=False)
        a=self.arrays;n=self.manifest['samples']
        for key,shape in {'q':(n,1,32),'kv':(n,41,24),'mask':(n,41),'target':(n,90),'weight':(n,),
                          'bucket':(n,),'split':(n,),'source_id':(n,)}.items():
            if a[key].shape!=shape:raise ValueError('Invalid '+key+' shape')
            if not np.isfinite(a[key]).all():raise ValueError('Nonfinite '+key)
        if np.any(a['weight']<=0) or np.any(a['weight']>1):raise ValueError('Invalid confidence')
        if np.any(a['target']<0) or not np.allclose(a['target'].sum(-1),1,atol=1e-5):raise ValueError('Invalid action targets')
        self.indices={name:np.flatnonzero(a['split']==i) for i,name in enumerate(('train','validation','test'))}
        if any(not len(ix) for ix in self.indices.values()):raise ValueError('Missing train/validation/test partition')
        groups=[set(a['source_id'][ids]) for ids in self.indices.values()]
        if any(groups[i]&groups[j] for i in range(3) for j in range(i)):raise ValueError('Source leakage')
        if np.any(a['bucket']>=len(BUCKETS)):raise ValueError('Invalid category')
        self.cache=OrderedDict()
        train=self.indices['train'];self.groups={}
        for bucket in np.unique(a['bucket'][train]):
            ids=train[a['bucket'][train]==bucket]
            self.groups[int(bucket)]=[ids[a['source_id'][ids]==source] for source in np.unique(a['source_id'][ids])]

    def batch(self,rng,size):
        # Choose category first; then source and row. Long matches cannot dominate.
        chosen=[]
        for bucket in rng.choice(list(self.groups),size):
            sources=self.groups[int(bucket)];pool=sources[int(rng.integers(len(sources)))]
            chosen.append(int(rng.choice(pool)))
        return self.take(np.asarray(chosen))

    def take(self,ids):
        result={k:np.asarray(v[ids]).copy() for k,v in self.arrays.items() if k not in ('split','source_id')}
        result['mask']=np.where(result['mask']>0,-10000.,result['mask']).astype(np.float32)
        return result
    def reset_state(self,rng,team_size=None):
        from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state
        records=[r for r in self.manifest['sources'] if r['partition']=='train']
        rng.shuffle(records)
        for r in records:
            key=r['path']
            if key not in self.cache:
                if sha256(key)!=r['sha256']:raise RuntimeError('Reset shard changed')
                with np.load(key,allow_pickle=False) as z:self.cache[key]=z['states']
                if len(self.cache)>4:self.cache.popitem(last=False)
            states=self.cache[key];state=deserialize_game_state(states[int(rng.integers(len(states)))].copy())
            if (team_size is None or len(state.cars)==2*team_size) and valid_state(state):
                mapping={aid:('orange-' if car.is_orange else 'blue-')+str(j) for j,(aid,car) in enumerate(sorted(state.cars.items()))}
                # Canonical side-local numbering permits blue-0/orange-0 learner.
                for team in (0,1):
                    for j,aid in enumerate(k for k,c in state.cars.items() if c.team_num==team):mapping[aid]=('orange-' if team else 'blue-')+str(j)
                for car in state.cars.values():car.bump_victim_id=mapping.get(car.bump_victim_id);car.ball_touches=0
                state.cars={mapping[k]:v for k,v in state.cars.items()};state.tick_count=0
                return state
        raise ValueError('No valid training reset for requested team size')
