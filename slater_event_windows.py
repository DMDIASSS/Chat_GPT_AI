"""Goal/save/kickoff clips for native curricula; future events are selection labels only."""
from __future__ import annotations
import argparse,copy,hashlib,json,math,random,struct
from collections import Counter
from pathlib import Path
import numpy as np
from slater_v041_core import atomic_json,sha256
from slater_versatile_data import label,valid_state,partition
from slater_research.replay_engine import goal_events
from nexto_teacher import nexto_actions
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/isolated/event_curriculum'

def events(parsed):
    result=[];players={str(p['unique_id']):bool(p['is_orange']) for p in parsed.metadata.get('players',[]) if p.get('unique_id') is not None}
    def stamp(frame):
        row=parsed.game_df.loc[int(frame)];row=row.iloc[0] if getattr(row,'ndim',1)>1 else row
        return float(row['time'])
    for time,attacker in goal_events(parsed):result.append(dict(kind='attack',time=time,query=str(attacker)))
    tagged=list(parsed.analyzer.get('hits',[]))
    tagged.extend({**hit,'is_save':True} for hit in parsed.analyzer.get('saves',[]) if isinstance(hit,dict))
    for hit in tagged:
        if hit.get('is_save') is True or hit.get('save') is True:
            aid=str(hit.get('player_unique_id'))
            if aid in players:result.append(dict(kind='save',time=stamp(hit['frame_number']),query=aid))
    for period in parsed.analyzer.get('gameplay_periods',[]):
        try:result.append(dict(kind='kickoff',time=stamp(period['start_frame'])+5,query=None))
        except (KeyError,ValueError,IndexError):pass
    return sorted(result,key=lambda e:(e['time'],e['kind']))

def source_coverage(parsed):
    return {str(aid):{key:int(df[key].notna().sum()) if key in df else 0 for key in ('throttle','steer')}
            for aid,df in parsed.player_dfs.items()}

def event_state_valid(state):
    if state.goal_scored or len(state.cars)!=2 or sorted(c.team_num for c in state.cars.values())!=[0,1]:return False
    if not np.allclose([state.config.gravity,state.config.boost_consumption,state.config.dodge_deadzone],[1,1,.5]):return False
    if not np.isfinite(state.boost_pad_timers).all() or np.any(state.boost_pad_timers<0):return False
    if any(c.is_demoed for c in state.cars.values()):return False
    for p in [state.ball]+[c.physics for c in state.cars.values()]:
        if not all(np.isfinite(v).all() for v in (p.position,p.linear_velocity,p.angular_velocity,p.rotation_mtx)):return False
        if not np.allclose(p.rotation_mtx.T@p.rotation_mtx,np.eye(3),atol=.02) or np.linalg.det(p.rotation_mtx)<.98:return False
        x,y,z=p.position
        if abs(x)>4100 or abs(y)>6000 or not 0<z<2045:return False
        # Cars/ball can legitimately enter the goal mouth before the goal event fires.
        if abs(y)>5120 and (abs(x)>900 or z>650):return False
    return all(not c.is_demoed and np.isfinite(c.boost_amount) and 0<=c.boost_amount<=100 for c in state.cars.values())


def event_label(car,controls,max_cost=.35):
    controls=np.asarray(controls,dtype=np.float32).copy()
    if controls.shape!=(8,) or not np.isfinite(controls).all() or np.any(np.abs(controls)>1.001):return None
    if car.boost_amount<=0:controls[6]=0
    if not (car.on_ground or car.is_jumping or car.has_flip):controls[5]=0
    if controls[5]==1 and car.can_flip:
        from rlgym_tools.rocket_league.replays.pick_action import get_best_action_options
        if not np.all(np.isclose(controls[5:],0)|np.isclose(controls[5:],1)):return None
        target=get_best_action_options(car,controls,nexto_actions(),greedy=True)
        if not np.isfinite(target).all() or target.sum()<=0:return None
        expected=np.array([controls[2],controls[3]+controls[4]])
        selected=nexto_actions()[target>0];directions=np.c_[selected[:,2],selected[:,3]+selected[:,4]]
        # Yaw and roll can encode the same dodge direction; do not penalize that equivalence.
        if np.abs(controls[2:5]).sum()>=.5 and np.linalg.norm(expected)>1e-9:
            expected/=np.linalg.norm(expected);directions/=np.maximum(np.linalg.norm(directions,axis=1,keepdims=True),1e-9)
            cost=float(np.min(2*(1-directions@expected)**2))
        else:cost=float(np.min(np.sum(directions**2,axis=1)))
        if cost>max_cost:return None
        return target.astype(np.float32),float(np.exp(-cost/.35))
    return label(car,controls,max_cost=max_cost)


def native_row(state,ids,previous,query,target,weight,split):
    def body(p):return np.r_[p.position,p.rotation_mtx.T.reshape(-1),p.linear_velocity,p.angular_velocity]
    blocks=[]
    for aid in ids:
        c=state.cars[aid];blocks.append(np.r_[body(c.physics),c.boost_amount,c.on_ground,c.has_jumped,c.has_double_jumped,c.has_flipped,
            c.is_jumping,c.jump_time,c.flip_time,c.air_time_since_jump,previous.get(aid,np.zeros(8)),c.flip_torque,c.wheels_with_contact,bool(c.is_flipping)])
    return np.r_[body(state.ball),state.boost_pad_timers,*blocks,ids.index(query),target,weight,split].astype('<f4')

def play_reference(initial,controls,learner_team=None):
    """All cars and the ball stay dynamic; optionally make one team passive."""
    from rlgym.rocket_league.sim import RocketSimEngine
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        state=engine.set_state(copy.deepcopy(initial),{});ids=sorted(state.cars,key=lambda k:(state.cars[k].team_num,str(k)));goal=None;touches={0:0,1:0}
        for step,actions in enumerate(controls):
            commands={aid:np.tile(np.zeros(8) if state.cars[aid].team_num==learner_team else actions[j],(8,1)) for j,aid in enumerate(ids)}
            state=engine.step(commands,{})
            for car in state.cars.values():touches[car.team_num]+=int(car.ball_touches>0)
            if state.goal_scored:goal=0 if state.ball.position[1]>0 else 1;break
        return {'goal_team':goal,'steps':step+1,'seconds':(step+1)/15,'touches_by_team':touches}
    finally:engine.close()

def prepare(inputs,out,*,max_replays=100,leads=(5,8,12),max_rows=100000):
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    from rlgym.rocket_league.common_values import BOOST_LOCATIONS
    out=Path(out).resolve()
    if not out.is_relative_to(BASE):raise ValueError('Output must be under data/isolated/event_curriculum')
    if (out/'manifest.json').exists():raise FileExistsError('Prepared curriculum exists; preserve it and choose a new name')
    if any(not 5<=x<=12 for x in leads) or not 1<=max_replays<=500 or not 100<=max_rows<=100000:raise ValueError('Invalid preparation budget')
    sources=sorted(Path(inputs).rglob('*.replay'))[:max_replays]
    if not sources:raise FileNotFoundError('No raw .replay files found')
    out.mkdir(parents=True,exist_ok=True);rows=[];windows=[];sources_report=[];stats=Counter();group_splits={}
    source_budget=max(1,max_rows//len(sources))
    for n,path in enumerate(sources):
        source_rows=[];source_initial=[];source_windows=[];source_ok=False
        digest=sha256(path);group=digest;split={'train':0,'validation':1,'test':2}[partition(group)]
        try:
            rp=ParsedReplay.load(str(path))
            match_id=rp.metadata.get('game',{}).get('id')
            if match_id:group=hashlib.sha256(('replay:'+str(match_id)).encode()).hexdigest()
            split={'train':0,'validation':1,'test':2}[partition(group)];group_splits[group]=split
            coverage=source_coverage(rp)
            eligible={aid for aid,values in coverage.items() if values['throttle'] and values['steer']}
            if len(eligible)!=2:raise ValueError('Need recorded ground controls for both duel players')
            frames=list(replay_to_rlgym(rp,interpolation='rocketsim'));times=np.array([f.state.tick_count/120 for f in frames]);ev=events(rp)
            if not len(times) or np.any(np.diff(times)<0):raise ValueError('Invalid replay clock')
            for event in ev:
                for lead in leads if event['kind']!='kickoff' else (5,):
                    start=float(event['time']-lead);stop=float(event['time']);indices=np.flatnonzero((times>=start)&(times<=stop))
                    if len(indices)<8 or times[indices[-1]]-times[indices[0]]<lead-.25:stats['short_or_missing_window']+=1;continue
                    first=frames[indices[0]]
                    if event['kind']=='kickoff' and np.linalg.norm(first.state.ball.position[:2])>1:stats['not_a_kickoff_start']+=1;continue
                    ids=sorted(first.state.cars,key=lambda k:(first.state.cars[k].team_num,str(k)))
                    if len(ids)!=2 or any(str(aid) not in eligible for aid in ids):continue
                    # Continuous play only; never bridge a reset/goal within the demonstration.
                    selected=[];last_tick=-1;broken=False
                    for tick in range(math.ceil(times[indices[0]]*120),math.floor(stop*120)+1,8):
                        ix=int(np.searchsorted(times,tick/120,'right')-1)
                        if ix<indices[0] or ix>indices[-1] or tick/120-times[ix]>.075:broken=True;break
                        f=frames[ix]
                        if f.state.tick_count==last_tick:broken=True;break
                        if f.state.goal_scored and tick/120>=stop-.15:break
                        if f.scoreboard.go_to_kickoff and tick/120>=stop-.15:break
                        if f.scoreboard.go_to_kickoff or f.scoreboard.is_over or f.scoreboard.kickoff_timer_seconds>0:broken=True;break
                        if not event_state_valid(f.state) or set(f.state.cars)!=set(ids):broken=True;break
                        if any(aid not in f.actions or f.update_age.get(aid,999)>.08 for aid in ids):broken=True;break
                        selected.append(f);last_tick=f.state.tick_count
                    if broken or len(selected)<8:stats['broken_window']+=1;continue
                    queries=ids if event['query'] is None else [aid for aid in ids if str(aid)==event['query']]
                    for query in queries:
                        role=selected[0].state.cars[query].team_num;kind=event['kind'];indices_added=[];previous={};targets=[]
                        for frame in selected:
                            target=event_label(frame.state.cars[query],frame.actions[query],max_cost=.35)
                            if target is not None:
                                dist,confidence=target;indices_added.append(len(source_rows));source_rows.append(native_row(frame.state,ids,previous,query,dist,confidence,split))
                            previous={aid:frame.actions[aid].copy() for aid in ids}
                        if not indices_added:continue
                        stats[kind+'_imitation_rows']+=len(indices_added)
                        # The long window supplies BC. RL uses only suffixes whose reference outcome reproduces.
                        if kind=='attack':
                            attack_added=False;save_added=False
                            for suffix in (1,2,5):
                                k=max(0,len(selected)-round(suffix*15));tail=selected[k:];controls=np.array([[f.actions[aid] for aid in ids] for f in tail],dtype=float)
                                if len(controls)<8 or len(controls)>180:continue
                                baseline=play_reference(tail[0].state,controls)
                                if baseline['goal_team']!=role:stats['unreproduced_attack_suffix']+=1;continue
                                initial_label=event_label(tail[0].state.cars[query],tail[0].actions[query],max_cost=.35)
                                if initial_label is None:continue
                                initial_row=native_row(tail[0].state,ids,{},query,initial_label[0],initial_label[1],split)
                                start_row=len(source_initial)
                                source_initial.append(initial_row)
                                common=dict(start_row=start_row,controls=controls.tolist(),split=split,replay_sha=digest,replay_group=group,query_team=role,kind='replay_attack',baseline=baseline)
                                passive_attack=play_reference(tail[0].state,controls,learner_team=role)
                                if baseline['touches_by_team'][role]>0 and passive_attack['goal_team']!=role and not attack_added:
                                    source_windows.append(common);stats['verified_attack_windows']+=1;attack_added=True
                                defense=play_reference(tail[0].state,controls,learner_team=1-role)
                                if defense['goal_team']==role and not save_added:
                                    source_windows.append({**common,'query_team':1-role,'kind':'replay_save','passive_defender_baseline':defense});stats['verified_save_windows']+=1;save_added=True
                                if attack_added and save_added:break
            source_ok=True
            sources_report.append(dict(path=str(path),sha256=digest,group=group,split=split,coverage=coverage,events=len(ev)))
        except Exception as exc:stats['source_errors']+=1;sources_report.append(dict(path=str(path),sha256=digest,split=split,error=str(exc)))
        if source_ok:
            capacity=min(source_budget,max_rows-len(rows));keep=min(len(source_initial),capacity);base=len(rows)
            rows.extend(source_initial[:keep])
            for window in source_windows:
                if window['start_row']<keep:windows.append({**window,'start_row':base+window['start_row']})
            take=min(len(source_rows),capacity-keep)
            if take:
                chosen=np.random.default_rng(int(digest[:12],16)).choice(len(source_rows),take,replace=False)
                rows.extend(source_rows[int(i)] for i in chosen)
        print('EVENT_PREPARE',n+1,'/',len(sources),'rows',len(rows),'verified_windows',len(windows),flush=True)
        if len(rows)>=max_rows:break
    atomic_json(out/'diagnostics.json',dict(stats=dict(stats),sources=sources_report,retained_rows=len(rows),verified_windows=len(windows)))
    if not rows:raise ValueError('No trustworthy event-window labels; inspect parser/control coverage')
    a=np.stack(rows);bank=out/'event_bank.bin'
    if not all(np.any(a[:,-1]==i) for i in (0,1,2)):raise ValueError('Need independent replay groups in train/validation/test; use more replays')
    with bank.open('wb') as f:
        f.write(b'SGRB');f.write(struct.pack('<IIII',1,2,len(rows),231));f.write(nexto_actions().astype('<f4').tobytes());f.write(np.asarray(BOOST_LOCATIONS,dtype='<f4').tobytes());f.write(a.tobytes())
    window_path=out/'windows.json';atomic_json(window_path,dict(version=1,bank_sha=sha256(bank),windows=windows))
    report=dict(version=1,bank=str(bank),bank_sha=sha256(bank),windows=str(window_path),windows_sha=sha256(window_path),rows=len(rows),stats=dict(stats),sources=sources_report,
                note='5–12s outcome-selected imitation windows; current-state actor inputs. Live RL uses dynamically reproduced suffixes. No teleports or invented save labels.')
    atomic_json(out/'manifest.json',report);return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',default='data/replays/ranked-duels');p.add_argument('--out',default=str(BASE/'windows01'));p.add_argument('--max-replays',type=int,default=100)
    a=p.parse_args();print(json.dumps(prepare(a.inputs,a.out,max_replays=a.max_replays),indent=2))
