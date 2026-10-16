"""Cache replay reconstruction, causal histories and future-only value labels."""
from collections import Counter,deque
from pathlib import Path
import copy,hashlib,json,math
import numpy as np
from afk_team_research import TeamObserver
from slater_versatile_data import native_observation,valid_state
from slater_v041_core import atomic_json,read_json,sha256,process_lock

ROOT=Path(__file__).resolve().parents[1]
def replay_frames(replay):
    """Advance repeated physics updates and hidden car state between observations.

    Raw replay car updates repeat across frames. The converter's ``none`` mode
    freezes those poses and does not advance jump/flip/contact timers. Its
    RocketSim mode predicts between updates, then reapplies observed physics.
    make_rows still rejects stale frames and checks transitions/full chunks.
    """
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    return replay_to_rlgym(replay,interpolation='rocketsim',predict_pyr=True)

def split(group):
    value=int(hashlib.sha256(('replay-il-v1:'+group).encode()).hexdigest()[:8],16)%100
    return 'train' if value<80 else 'validation' if value<90 else 'test'

def transition_errors(predicted,observed):
    pairs=[(predicted.ball,observed.ball)]+[(predicted.cars[k].physics,observed.cars[k].physics) for k in observed.cars]
    return {'position':max(float(np.linalg.norm(a.position-b.position)) for a,b in pairs),
            'velocity':max(float(np.linalg.norm(a.linear_velocity-b.linear_velocity)) for a,b in pairs),
            'rotation':max(float(np.linalg.norm(a.rotation_mtx-b.rotation_mtx)) for a,b in pairs)}

def simulate(engine,state,controls,ticks):
    engine.set_state(state,{})
    return engine.step({k:np.repeat(v[None],ticks,axis=0) for k,v in controls.items()},{})

def fit_transition(engine,before,after,controls,ticks,limits):
    controls={k:np.asarray(v,np.float32).copy() for k,v in controls.items()}
    def error(raw):
        state=simulate(engine,before,raw,ticks);errors=transition_errors(state,after)
        return max(errors[k]/limits[k] for k in limits),errors
    score,errors=error(controls);attempts=1
    if score>1:
        # The converter estimates missing pitch/yaw/roll. Refine only those
        # unknown aerial axes against observed motion, rather than inventing
        # ground throttle or silently accepting a bad simulation fit.
        for aid,car in before.cars.items():
            if car.on_ground:continue
            best=controls[aid].copy()
            for axis in (2,3,4):
                for delta in (-.25,.25):
                    trial={k:v.copy() for k,v in controls.items()}
                    trial[aid][axis]=np.clip(best[axis]+delta,-1,1)
                    candidate,detail=error(trial);attempts+=1
                    if candidate<score:score,errors,best=candidate,detail,trial[aid].copy()
                controls[aid]=best.copy()
    return controls,score<=1,errors,attempts

def make_rows(frames,*,history=8,chunk_ticks=32,cap=1024,seed=20261016,limits=None):
    """All simulation is inverse fitting/forward verification of replay states.

    No policy plays an opponent, generates a training game or optimizes reward.
    Each sample's history ends BEFORE its target controls begin.
    """
    from rlgym.rocket_league.sim import RocketSimEngine
    limits=limits or {'position':40.,'velocity':180.,'rotation':.3}
    engine=RocketSimEngine(rlbot_delay=False);verify_engine=RocketSimEngine(rlbot_delay=False)
    observer=TeamObserver();rng=np.random.default_rng(seed)
    histories={};pending={};rows=[];seen=0;stats=Counter();past={};previous=None;kickoff=None;book=[]
    def clear():histories.clear();pending.clear();past.clear()
    def features(state,controls):
        views=observer.observe(state,controls);ids=sorted(state.cars)
        return {k:tuple(x.astype(np.float16) for x in native_observation(views[k])) for k in ids}
    try:
        for current in frames:
            # RLGym Tools sets tick_count=time_seconds*120, which is a float.
            # Normalize absolute frame times before both differencing and the
            # tick%8 sampling grid; int(delta) silently loses physics ticks.
            raw_tick=float(current.state.tick_count)
            if not math.isfinite(raw_tick):
                previous=None;clear();kickoff=None;stats['invalid_tick_count']+=1;continue
            current=copy.copy(current);current.state=copy.deepcopy(current.state)
            current.state.tick_count=math.floor(raw_tick+.5)
            if raw_tick!=current.state.tick_count:stats['fractional_tick_frames']+=1
            if previous is None:previous=current;continue
            frame=previous;previous=current;s,t=frame.state,current.state
            ticks=int(t.tick_count-s.tick_count)
            if not 1<=ticks<=16 or set(s.cars)!=set(t.cars) or not valid_state(s) or not valid_state(t):clear();kickoff=None;stats['invalid_or_discontinuous']+=1;continue
            if getattr(frame.scoreboard,'go_to_kickoff',False) or getattr(frame.scoreboard,'is_over',False) or getattr(frame.scoreboard,'kickoff_timer_seconds',0)>0:clear();kickoff=None;continue
            raw={k:np.asarray(frame.actions[k],np.float32) for k in s.cars if k in frame.actions}
            if set(raw)!=set(s.cars) or any(v.shape!=(8,) or not np.isfinite(v).all() or np.any(np.abs(v)>1.001) for v in raw.values()):clear();stats['missing_controls']+=1;continue
            if any(not np.isin(v[5:],[0,1]).all() for v in raw.values()):clear();stats['invalid_buttons']+=1;continue
            if any(not 0<=float(frame.update_age.get(k,999))<=.05 for k in s.cars):clear();stats['stale_states']+=1;continue
            fitted,accepted,errors,attempts=fit_transition(engine,s,t,raw,ticks,limits)
            stats['fit_attempts']+=attempts;stats['transitions']+=1
            if stats['transitions']%1000==0:print('RECONSTRUCT',stats['transitions'],'transitions; accepted',stats['accepted_fit'],'rejected',stats['rejected_fit'],'saved chunks',len(rows),flush=True)
            if not accepted:
                clear();kickoff=None;stats['rejected_fit']+=1
                for key in limits:
                    if errors[key]>limits[key]:stats['rejected_'+key]+=1
                continue
            stats['accepted_fit']+=1
            for key,value in errors.items():stats['max_accepted_'+key]=max(stats['max_accepted_'+key],value)
            if kickoff is None and np.linalg.norm(s.ball.position[:2])<1 and np.linalg.norm(s.ball.linear_velocity)<1 and all(c.on_ground and np.linalg.norm(c.physics.linear_velocity)<2 and abs(c.physics.position[1])>2300 for c in s.cars.values()):
                kickoff={'start':s.tick_count,'state':copy.deepcopy(s),'spawns':{k:(np.asarray(c.physics.position)*np.array([-1,-1,1]) if c.is_orange else np.asarray(c.physics.position)).tolist() for k,c in s.cars.items()},'controls':{k:[] for k in s.cars},'players':len(s.cars)}
            state=engine.set_state(s,{});remaining=ticks
            while remaining:
                tick=int(state.tick_count)
                if tick%8==0:
                    encoded=features(state,past)
                    segment={'start':copy.deepcopy(state),'controls':{k:[] for k in state.cars}}
                    for aid,car in state.cars.items():
                        h=histories.setdefault(aid,deque(maxlen=history));h.append(encoded[aid])
                        observations=[h[0]]*(history-len(h))+list(h)
                        hist=tuple(np.stack([item[j] for item in observations]) for j in range(3))
                        team=getattr(frame,'next_scoring_team',None);seconds=float(getattr(frame,'episode_seconds_remaining',0))
                        value=0. if team is None else (1. if team==car.team_num else -1.)*math.exp(-max(0,seconds)/15)
                        pending.setdefault(aid,[]).append({'history':hist,'controls':[],'value':value,'players':len(s.cars),'_segment':segment})
                count=min(remaining,8-tick%8)
                segments={id(row['_segment']):row['_segment'] for values in pending.values() for row in values}
                for segment in segments.values():
                    for aid in s.cars:segment['controls'][aid].extend(np.repeat(fitted[aid][None],count,axis=0).tolist())
                ready=[]
                for aid in s.cars:
                    block=np.repeat(fitted[aid][None],count,axis=0)
                    if kickoff is not None:kickoff['controls'][aid].extend(block.tolist())
                    active=[]
                    for row in pending.get(aid,[]):
                        row['controls'].extend(block.tolist())
                        if len(row['controls'])>=chunk_ticks:
                            row['controls']=np.asarray(row['controls'][:chunk_ticks],np.float16);ready.append(row)
                        else:active.append(row)
                    pending[aid]=active
                state=engine.step({k:np.repeat(v[None],count,axis=0) for k,v in fitted.items()},{})
                for row in ready:
                    segment=row.pop('_segment')
                    if 'valid' not in segment:
                        verify_engine.set_state(segment['start'],{})
                        predicted=verify_engine.step({k:np.asarray(v[:chunk_ticks],np.float32) for k,v in segment['controls'].items()},{})
                        observed=t if state.tick_count==t.tick_count else state
                        detail=transition_errors(predicted,observed)
                        segment['valid']=all(detail[k]<=limits[k] for k in limits)
                        stats['chunks_verified' if segment['valid'] else 'chunks_rejected']+=1
                    if not segment['valid']:continue
                    seen+=1
                    if len(rows)<cap:rows.append(row)
                    else:
                        index=int(rng.integers(seen))
                        if index<cap:rows[index]=row
                past={k:v.copy() for k,v in fitted.items()};remaining-=count
                if kickoff is not None:
                    touching=[aid for aid,c in state.cars.items() if c.ball_touches]
                    if touching:
                        verify_engine.set_state(kickoff['state'],{})
                        predicted=verify_engine.step({k:np.asarray(v,np.float32) for k,v in kickoff['controls'].items()},{})
                        detail=transition_errors(predicted,state)
                        if all(detail[k]<=limits[k] for k in limits):
                            for aid in touching:
                                if predicted.cars[aid].ball_touches:book.append({'spawn':kickoff['spawns'][aid],'players':kickoff['players'],'touch_ticks':len(kickoff['controls'][aid]),'controls':kickoff['controls'][aid]})
                        kickoff=None
                    elif state.tick_count-kickoff['start']>360:kickoff=None
        return rows,book,dict(stats)
    finally:engine.close();verify_engine.close()

def prepare(inputs,out,**kwargs):
    out=Path(out).resolve()
    if not out.is_relative_to(ROOT/'data/isolated'):raise ValueError('Dataset must be under data/isolated')
    out.mkdir(parents=True,exist_ok=True)
    with process_lock(out/'prepare.lock'):
        if (out/'manifest.json').exists():raise FileExistsError('Completed dataset exists. Use a new dataset directory to change inputs.')
        (out/'pause.flag').unlink(missing_ok=True)
        return _prepare(inputs,out,**kwargs)

def _prepare(inputs,out,*,max_replays=3000,per_replay=1024,max_samples=500000):
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from importlib.metadata import version
    if not 1<=max_replays<=100000 or not 16<=per_replay<=4096 or not 100<=max_samples<=2000000:raise ValueError('Invalid replay/data budget')
    out=Path(out).resolve()
    if not out.is_relative_to(ROOT/'data/isolated'):raise ValueError('Dataset must be under data/isolated')
    paths=[]
    for item in inputs:
        p=Path(item);paths.extend(sorted(p.rglob('*.replay')) if p.is_dir() else [p])
    paths=sorted({p.resolve() for p in paths if p.is_file() and p.suffix.lower()=='.replay'})[:max_replays]
    if not paths:raise ValueError('No .replay files found. Add real replays to data/replays or supply --inputs. No generated games will substitute.')
    out.mkdir(parents=True,exist_ok=True)
    cap=min(per_replay,max(16,max_samples//len(paths)))
    config={'history':8,'chunk_ticks':32,'per_replay':cap,'max_samples':max_samples,'observations':'raw_no_pretrained_encoder',
            'code':sha256(__file__),'rlgym_tools':version('rlgym-tools'),'interpolation':'rocketsim',
            'fit_limits':{'position':40.,'velocity':180.,'rotation':.3}}
    print('RECONSTRUCTION: RocketSim interpolation; transition and full-chunk quality checks enabled',flush=True)
    records=[];errors=[];seen=set();samples=0
    for index,path in enumerate(paths,1):
        if (out/'pause.flag').exists():raise RuntimeError('Replay preparation paused; completed replay shards are cached. Start again to resume.')
        print('REPLAY_PARSE_BEGIN',index,'/',len(paths),path.name,flush=True)
        digest=sha256(path);shard=out/'shards'/(digest+'.npz');meta=shard.with_suffix('.json')
        reconstruction=None
        try:
            prior=read_json(meta)
            if prior and prior['config']==config and prior['sha256']==sha256(shard):record=prior
            else:
                replay=ParsedReplay.load(path)
                original=str(replay.metadata.get('game',{}).get('id') or digest)
                group=hashlib.sha256(original.encode()).hexdigest()
                if group in seen:continue
                frames=replay_frames(replay)
                rows,book,stats=make_rows(frames,cap=cap,seed=int(digest[:8],16))
                reconstruction=stats
                if not rows:raise ValueError('No contiguous, forward-verified action chunks')
                shard.parent.mkdir(parents=True,exist_ok=True)
                tmp=shard.with_suffix('.partial')
                with tmp.open('wb') as stream:
                    np.savez_compressed(stream,**{k:np.stack([r['history'][j] for r in rows]) for j,k in enumerate(('q','kv','mask'))},controls=np.stack([r['controls'] for r in rows]),
                        value=np.asarray([r['value'] for r in rows],np.float32),players=np.asarray([r['players'] for r in rows],np.uint8))
                tmp.replace(shard)
                atomic_json(shard.with_suffix('.kickoffs.json'),{'entries':book,'group':group})
                record={'source':str(path),'original_sha256':digest,'group':group,'split':split(group),'samples':len(rows),
                        'players':sorted(set(r['players'] for r in rows)),'rank_provenance':read_json(path.with_suffix('.source.json'),{}).get('rank_filter','User-curated folder; ranks not independently verified'),
                        'shard':str(shard),'sha256':sha256(shard),'config':config,'reconstruction':stats}
                atomic_json(meta,record)
            if record['group'] in seen:continue
            seen.add(record['group']);records.append(record);samples+=record['samples']
        except Exception as error:
            detail={'file':path.name,'error':str(error)[:300]}
            if reconstruction is not None:detail['reconstruction']=reconstruction
            errors.append(detail)
            print('REPLAY_REJECT',path.name,detail['error'],flush=True)
        atomic_json(out/'parse_progress.json',{'completed':index,'total':len(paths),'samples':samples,'errors':errors})
        print('REPLAY_PARSE',index,'/',len(paths),'samples',samples,'errors',len(errors),flush=True)
        if samples>=max_samples:break
    counts=Counter(r['split'] for r in records)
    if min(counts.get(k,0) for k in ('train','validation','test'))<2:
        raise ValueError('Need at least two distinct real matches in each split. Add replays; successful shards are cached.')
    formats=Counter(str(n//2)+'v'+str(n//2) for record in records for n in record['players'])
    manifest={'schema':'replay-il-v2-raw','config':config,'sources':records,'errors':errors,'samples':samples,'matches_by_format':dict(formats),
              'matches_by_split':dict(counts),'learning':'pure_imitation','human_inputs':'reconstructed and forward-filtered; not exact ground truth'}
    atomic_json(out/'manifest.json',manifest);return manifest
