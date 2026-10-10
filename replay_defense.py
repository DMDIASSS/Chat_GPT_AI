"""Replay-driven isolated Cycle9 defense drills. No model auto-promotion.

Requires rlgym-tools >=2.6, RocketSim, and the existing project's native Nexto tools.
First version: reconstructed replay car controls are approximate and MUST pass a
counterfactual fidelity check before treating a drill as verified.
"""
from __future__ import annotations
import argparse
import bisect
import contextlib
import copy
import hashlib
import json
import math
import os
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
EXPECTED = '50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
DATA = ROOT / 'data/replay_defense'
TICKS = 8
DT = TICKS / 120.0


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda:f.read(1024 * 1024), b''):
            h.update(c)
    return h.hexdigest()


def write_json(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.partial')
    tmp.write_text(json.dumps(value, indent=2, default=str), encoding='utf8')
    os.replace(tmp, p)


def player_statistics(metadata):
    """Use game-header stats without inventing numbers for missing fields."""
    players = metadata.get('players', [])
    if not isinstance(players, list): return 0, 0, False
    nshots = nsaves = 0; found = False
    for p in players:
        if not isinstance(p, dict): continue
        stats = p.get('stats', p)
        if not isinstance(stats, dict): stats = p
        for key in ['shots', 'saves']:
            v = next((obj[k] for obj in [stats,p] for k in [key,key.title(),key.upper()] if k in obj), None)
            if isinstance(v, (int,float)) and math.isfinite(v) and v >= 0:
                found = True
                if key == 'shots': nshots += int(v)
                else: nsaves += int(v)
    return nshots, nsaves, found


def rank_replays(items):
    """Known shots+saves descending; unknown stats do not falsely rank as zero."""
    return sorted(items, key=lambda r:(not r['stats_known'], -r['shots']-r['saves'], -r['shots'], r['path'].lower()))


def is_marked_shot(hit):
    return any(hit.get(k) is True for k in ('is_shot', 'shot', 'is_goal', 'goal'))

def is_marked_save(hit):
    return any(hit.get(k) is True for k in ('is_save','save'))


def toward_opposing_net(pos, vel, shooter_orange):
    """Loose trajectory screen for a real threatening ball, not game truth."""
    goal_y = -5120. if shooter_orange else 5120.
    vy = float(vel[1]); dt = (goal_y-float(pos[1]))/vy if abs(vy)>1 else -1
    if not (0.09 <= dt <= 2.8): return False
    x = float(pos[0]) + float(vel[0])*dt
    z = float(pos[2]) + float(vel[2])*dt - 325.*dt*dt
    return abs(x) < 1600. and -150. < z < 1150. and abs(vy) >= 400.


def events_from_replay(parsed, cap):
    players = {str(p.get('unique_id')):p for p in parsed.metadata.get('players',[]) if isinstance(p,dict)}
    events = []
    for hit in parsed.analyzer.get('hits',[]):
        if not isinstance(hit,dict) or 'frame_number' not in hit: continue
        frame = int(hit['frame_number'])
        shooter = str(hit.get('player_unique_id'))
        p = players.get(shooter)
        if not p or 'is_orange' not in p: continue
        try:
            row = parsed.ball_df.loc[frame]
            trow = parsed.game_df.loc[frame]
            if getattr(row,'ndim',1)!=1: row=row.iloc[0]
            if getattr(trow,'ndim',1)!=1: trow=trow.iloc[0]
            pos = np.array([row['pos_x'],row['pos_y'],row['pos_z']], dtype=float)
            vel = np.array([row['vel_x'],row['vel_y'],row['vel_z']], dtype=float)
            st = float(trow['time'])
        except (KeyError,IndexError,ValueError,TypeError): continue
        tagged = is_marked_shot(hit)
        dangerous = toward_opposing_net(pos,vel,bool(p['is_orange']))
        if not (tagged or dangerous): continue
        events.append({'frame':frame,'time':st,'shooter':shooter,'defender_orange':not bool(p['is_orange']),
                       'tagged':tagged,'trajectory_threat':dangerous})
    # Attach subsequent tagged save to the shot for *that* defender only.
    saves=[]
    for hit in parsed.analyzer.get('hits',[]):
        if not isinstance(hit,dict) or not is_marked_save(hit):continue
        player_id=str(hit.get('player_unique_id'));player=players.get(player_id)
        if player is None:continue
        try:
            row=parsed.game_df.loc[int(hit['frame_number'])]
            if getattr(row,'ndim',1)!=1:row=row.iloc[0]
            saves.append((float(row['time']),player_id,bool(player['is_orange'])))
        except (KeyError,ValueError,TypeError):continue
    for e in events:
        later=sorted((t,p) for t,p,orange in saves if orange==e['defender_orange'] and e['time']<=t<=e['time']+3.0)
        e['save_player']=later[0][1] if later else None
        e['save_time']=later[0][0] if later else None
    # Avoid many nearly identical hits for the same attack (2-second temporal gap).
    events.sort(key=lambda e:(not e['tagged'],-int(e['trajectory_threat']),e['time']))
    distinct = []
    for e in events:
        if all(abs(e['time']-x['time']) >= 1.75 for x in distinct): distinct.append(e)
        if len(distinct)>=cap: break
    return sorted(distinct,key=lambda e:e['time'])


def replay_sources(path):
    p = Path(path)
    if p.is_file():return [p] if p.suffix.lower()=='.replay' else []
    if not p.is_dir():raise FileNotFoundError(f'Replay directory not found: {p}')
    return sorted(f for f in p.rglob('*') if f.is_file() and f.suffix.lower()=='.replay')


def parse_replay(path):
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    return ParsedReplay.load(str(path))


def frame_data(frame):
    return float(frame.state.tick_count)/120.0


def latest_index(times, t):
    return max(0, min(len(times)-1, bisect.bisect_right(times,t)-1))


def save_drill(out, frames, times, event, defender, lead, slug, replay_rank):
    from rlgym_tools.rocket_league.misc.serialize import serialize_replay_frame
    start_at = event['time']-lead
    si = latest_index(times,start_at)
    if times[si] > start_at+.15 or start_at-times[si]>.2: return None
    start = copy.deepcopy(frames[si])
    original_ids = sorted(int(a) for a in start.state.cars)
    if len(original_ids) not in (2,4) or int(defender) not in original_ids:return None
    # Replay IDs can be 64-bit Steam IDs. ReplayFrame stores them as float32,
    # which would corrupt them; normalize to small, stable RocketSim car IDs.
    lookup = {aid:i+1 for i,aid in enumerate(original_ids)}
    aids = [lookup[aid] for aid in original_ids]
    start.state.cars = {lookup[aid]:start.state.cars[aid] for aid in original_ids}
    start.actions = {lookup[aid]:start.actions[aid] for aid in original_ids}
    start.update_age = {lookup[aid]:start.update_age[aid] for aid in original_ids}
    for car in start.state.cars.values():
        victim = getattr(car,'bump_victim_id',None)
        if victim is not None and victim in lookup:car.bump_victim_id = lookup[victim]
    # Don't span the kickoff reset or goal from another replay gameplay period.
    # Never cross a goal or large replay time gap into the next kickoff.
    end_time=min(event['time']+2.5, times[-1])
    for ix in range(si+1,len(times)):
        if times[ix]-times[ix-1] > .7 or (frames[ix].state.goal_scored and times[ix]>=event['time']):
            end_time=min(end_time,times[ix] if frames[ix].state.goal_scored else times[ix-1])
            break
        if times[ix]>=end_time:break
    n = int(max(0, math.floor((end_time-times[si])/DT)))
    if n<15 or times[si]+(n-1)*DT < event['time']-.15:return None
    actions = np.zeros((n,len(aids),8),dtype=np.float32)
    ball_reference = np.zeros((n,3),dtype=np.float32)
    for j in range(n):
        t = times[si]+j*DT
        ix = latest_index(times,t)
        f = frames[ix]
        if ix<si or t>times[-1]+.06:return None
        # Reject if goal crossed or kickoff reset within the drill window.
        if ix>si and f.state.goal_scored and t<event['time']-.3:return None
        ball_reference[j] = np.asarray(f.state.ball.position,dtype=np.float32)
        for k,orig_aid in enumerate(original_ids):
            act = f.actions.get(orig_aid, np.zeros(8))
            a = np.asarray(act,dtype=np.float32).reshape(8)
            if np.isfinite(a).all():actions[j,k] = np.clip(a,-1,1)
    save_player=lookup.get(int(event['save_player']),-1) if event.get('save_player') is not None else -1
    save_step=int(round((event['save_time']-times[si])/DT)) if event.get('save_time') is not None else -1
    encoded = np.asarray(serialize_replay_frame(start),dtype=np.float32)
    name = f'{slug}_rank{replay_rank:03d}_frame{event["frame"]:07d}_d{defender}_lead{lead:g}'
    target = out / f'{name}.npz'
    if target.exists():raise FileExistsError(f'Refusing to overwrite drill {target}')
    np.savez_compressed(target, start_frame=encoded, actions=actions, ball_reference=ball_reference,
                        agent_ids=np.asarray(aids,dtype=np.int64), defender=np.int64(lookup[defender]),
                        defender_orange=np.int8(event['defender_orange']),
                        shot_step=np.int32(max(0,min(n-1,round((event['time']-times[si])/DT)))),
                        save_player=np.int64(save_player),save_step=np.int32(save_step),
                        dt=np.float32(DT))
    return {'path':str(target.relative_to(ROOT)),'shot_frame':event['frame'], 'replay_rank':replay_rank,
            'lead_seconds':lead,'defender':lookup[defender],'original_defender_id':defender,'players':len(aids),'tagged_shot':event['tagged'],
            'trajectory_threat':event['trajectory_threat'],'save_player':save_player,'steps':n}


def cmd_index(args):
    files = replay_sources(args.replays)
    if not files:raise FileNotFoundError('No .replay files found. Copy saved Rocket League replay files into data/replay_defense/replays.')
    items=[]  # Never keep all parsed replay dataframes in RAM together.
    for ix,path in enumerate(files,1):
        try:
            rp=parse_replay(path)
            shots,saves,known=player_statistics(rp.metadata)
            ids={str(p.get('unique_id')) for p in rp.metadata.get('players',[]) if isinstance(p,dict)}
            if len(ids) not in (2,4):
                print(f'SKIP {path.name}: only 1v1/2v2 supported; found {len(ids)} players',flush=True);continue
            entry={'path':str(path.resolve()),'shots':shots,'saves':saves,'stats_known':known,
                   'players':len(ids)}
            items.append(entry)
            print(f'[{ix}/{len(files)}] {path.name}: shots={shots} saves={saves} known={known}',flush=True)
        except Exception as exc:
            print(f'FAILED {path.name}: {type(exc).__name__}: {exc}',flush=True)
    if not items:raise RuntimeError('No valid replay files indexed')
    ranked=rank_replays(items)
    target=DATA/'index.json';write_json(target,{'version':1,'ordering':'known shots+saves descending; unknown last',
        'items':[dict(x,rank=i+1) for i,x in enumerate(ranked)], 'created_utc':datetime.now(timezone.utc).isoformat()})
    print('Indexed',len(ranked),'replays; output:',target,flush=True)
    if args.index_only:return
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    drill_dir=DATA/'drills';drill_dir.mkdir(parents=True,exist_ok=True)
    drills=[]
    for ri,item in enumerate(ranked,1):
        try:rp=parse_replay(item['path'])
        except Exception as exc:
            print(f'Replay reload failed: {type(exc).__name__}: {exc}',flush=True);continue
        events=events_from_replay(rp,args.max_shots)
        if not events:
            print(f'No verified or trajectory-screened shot events in {Path(item["path"]).name}',flush=True);continue
        print(f'REPLAY {ri}/{len(ranked)} {Path(item["path"]).name}: {len(events)} shot candidates',flush=True)
        try:
            frames=list(replay_to_rlgym(rp,interpolation='linear'))
        except Exception as exc:
            print(f'Conversion failed: {type(exc).__name__}: {exc}',flush=True);continue
        times=[frame_data(f) for f in frames]
        if not times:continue
        raw_name=Path(item['path']).stem
        slug=''.join(c if c.isalnum() and c.isascii() else '_' for c in raw_name)[:28]
        for e in events:
            ix=latest_index(times,e['time'])
            state=frames[ix].state
            defending_ids=sorted(int(a) for a,c in state.cars.items() if bool(c.is_orange)==e['defender_orange'])
            if len(defending_ids)*2 != len(state.cars):continue
            # EACH 2v2 defender independently replaces their replay counterpart.
            for defender in defending_ids:
                for lead in args.leads:
                    try: result=save_drill(drill_dir,frames,times,e,defender,lead,slug,ri)
                    except Exception as exc:
                        print(f'Cannot save drill {slug} frame {e["frame"]}: {type(exc).__name__}: {exc}',flush=True);result=None
                    if result:drills.append(result)
        print(f'  created {sum(d["replay_rank"]==ri for d in drills)} drills',flush=True)
        del frames
    write_json(DATA/'drills.json',{'source_replays':[dict(x,rank=i+1) for i,x in enumerate(ranked)],
        'drills':drills,'warning':'Reconstructed replay actions may diverge from original. Validation required before claims of shot-saving skill.'})
    print(f'SAVED {len(drills)} individual defense drills -> {DATA / "drills.json"}',flush=True)
    if not drills:raise RuntimeError('No usable drills extracted. Send the index and conversion warnings.')


def load_drill(path):
    from rlgym_tools.rocket_league.misc.serialize import deserialize_replay_frame
    with np.load(path,allow_pickle=False) as p:
        frame=deserialize_replay_frame(p['start_frame'])
        acts=p['actions'].copy();reference=p['ball_reference'].copy()
        ids=[int(x) for x in p['agent_ids']]
        defender=int(p['defender']);orange=bool(p['defender_orange'])
        shot_step=int(p['shot_step'])
        save_player=int(p['save_player']);save_step=int(p['save_step'])
    if defender not in ids or set(frame.state.cars)!=set(ids):raise ValueError('Corrupt drill car IDs')
    if acts.shape!=(len(reference),len(ids),8) or len(acts)<5:raise ValueError('Corrupt drill actions')
    return frame.state,acts,reference,ids,defender,orange,shot_step,save_player,save_step


class DefenseDrill:
    def __init__(self,engine, path):
        self.engine=engine;self.path=Path(path)
        (self.initial,self.controls,self.ref,self.ids,self.defender,self.orange,
         self.shot_step,self.save_player,self.save_step)=load_drill(path)
        self.id_pos={aid:i for i,aid in enumerate(self.ids)}
        self.reset()
    def reset(self):
        self.state=self.engine.set_state(copy.deepcopy(self.initial),{})
        self.previous={};self.step_index=0;self.touch_count=0
        self.prev_goal_distance=self.goal_distance(self.state.ball.position)
        self.possible_goal=False
        return self.state
    def goal_distance(self,pos):
        return abs((-5120. if self.orange else 5120.)-float(pos[1]))
    def step(self, learner_controls, override=False):
        """Script other cars with recorded approximate controls; never freeze them."""
        i=self.step_index
        cdict={}
        for aid,j in self.id_pos.items():
            ctrl=self.controls[min(i,len(self.controls)-1),j].copy()
            if aid==self.defender and not override:ctrl=np.asarray(learner_controls,dtype=np.float32).reshape(8)
            cdict[aid]=np.tile(ctrl,(TICKS,1))
        pre_ball=np.asarray(self.state.ball.position,dtype=float).copy()
        self.state=self.engine.step(cdict,{})
        self.previous={aid:v[0].copy() for aid,v in cdict.items()}
        self.step_index+=1
        c=self.state.cars[self.defender]
        touched=int(getattr(c,'ball_touches',0))>0
        if touched:self.touch_count+=1
        got_goal=bool(self.state.goal_scored)
        # Consistent with blue attack +Y, orange attack -Y.
        conceded=got_goal and ((float(self.state.ball.position[1])>0)==self.orange)
        saved_goal=got_goal and not conceded
        # Small shaped reward: reverse dangerous approach; reward actual touches only when it changes path.
        newdist=self.goal_distance(self.state.ball.position)
        progress=float(np.clip((newdist-self.prev_goal_distance)/500.,-1.,1.))*.008
        self.prev_goal_distance=newdist
        v=np.asarray(self.state.ball.linear_velocity,dtype=float)
        # A ball moving toward the defender's goal: blue -Y, orange +Y.
        toward_goal=(v[1]>300) if self.orange else (v[1]<-300)
        away_after_touch = touched and not toward_goal
        reward=progress+(.13 if away_after_touch else 0.)-.0008
        if got_goal:reward+=-10. if conceded else 2.
        done=got_goal or self.step_index>=len(self.controls)
        if done and not conceded and self.shot_step<self.step_index:
            reward+=.4 # Survival is NOT guaranteed to be a real save; avoid large success reward.
        return float(reward),bool(done),{'goal':got_goal,'conceded':bool(conceded),'touch':bool(touched),
                                       'ball_error':float(np.linalg.norm(np.asarray(self.state.ball.position)-self.ref[min(self.step_index,len(self.ref)-1)])),
                                       'scripted':override}


def source_verified():
    if not SOURCE.is_file():raise FileNotFoundError('Original Cycle9 not found: '+str(SOURCE))
    h=sha256(SOURCE)
    if h!=EXPECTED:raise RuntimeError(f'Cycle9 source checksum mismatch: {h}')
    return h


def drill_catalog(args):
    idx=DATA/'drills.json'
    if not idx.exists():raise FileNotFoundError(f'Run REPLAY_1_EXTRACT.bat first; missing {idx}')
    d=json.loads(idx.read_text(encoding='utf8')).get('drills',[])
    if not d:raise ValueError('No replay drills generated')
    # Original ranking first, then challenging timings first; one defender at a time.
    d=sorted(d,key=lambda x:(x['replay_rank'],x['shot_frame'],x['lead_seconds'],x['defender']))
    return [(ROOT/x['path'],x) for x in d if (ROOT/x['path']).exists()]


def load_model():
    from auto_league import actor_from
    return actor_from(SOURCE,'cpu')


def predicted_action(actor,obs, sample):
    import torch
    from torch.distributions import Categorical
    from native_nexto import actor_logits
    from afk_team_research import tensors
    q,kv,mask=tensors(obs)
    with torch.no_grad():
        logits=actor_logits(actor,q,kv,mask)
        dist=Categorical(logits=logits)
        a=dist.sample() if sample else logits.argmax(-1)
    return int(a.item()),float(dist.log_prob(a).item())


def fallback_fidelity(args):
    """Read-only replay action reconstruction check. Scores WARNING not verified fidelity."""
    from rlgym.rocket_league.sim import RocketSimEngine
    catalog=drill_catalog(args)
    engine=RocketSimEngine(rlbot_delay=False)
    scores=[]
    try:
        for path,meta in catalog[:args.max_drills]:
            match=DefenseDrill(engine,path)
            errors=[];goal=False;threat=False
            for j in range(len(match.controls)):
                # All cars, INCLUDING defender, replay approximate actions.
                _,done,info=match.step(np.zeros(8),override=True)
                if j==match.shot_step:
                    errors.append(info['ball_error'])
                    ball=match.state.ball
                    threat=toward_opposing_net(np.asarray(ball.position),np.asarray(ball.linear_velocity),not match.orange)
                if info['conceded']:goal=True
                if done:break
            err=errors[0] if errors else float('inf')
            records={'drill':str(path.relative_to(ROOT)),'shot_ball_error_uu':round(err,1),
                     'simulated_opponent_goal':goal,'shot_still_threatening':threat,
                     'fid_ok':err<=args.max_ball_error and (threat or goal),
                     'warning':'Replay-derived controls are approximated and may diverge; no guarantee of exact reenactment'}
            scores.append(records)
            print(f'{path.name}: error at shot {err:.1f} uu threatening={threat} opponent_goal={goal} -> {"PASS" if records["fid_ok"] else "FAIL"}',flush=True)
    finally:engine.close()
    write_json(DATA/'fidelity.json',{'max_error':args.max_ball_error,'cases':scores})
    print(f'Reconstructed attack fidelity: {sum(x["fid_ok"] for x in scores)}/{len(scores)} passed. Report: {DATA / "fidelity.json"}',flush=True)
    if not any(x['fid_ok'] for x in scores):raise RuntimeError('No faithfully recreated dangerous drills. Do NOT train. Send fidelity report.')


def train(args):
    import torch
    import torch.nn.functional as F
    from torch.distributions import Categorical
    from rlgym.rocket_league.sim import RocketSimEngine
    from auto_league import exclusive_league_lock
    from afk_team_research import TeamObserver,TeamCritic,tensors
    from native_nexto import actor_logits,discounted_gae
    from nexto_teacher import nexto_actions
    if args.repeats<1 or args.rollout<8 or args.epochs<1 or args.lr<=0 or args.bc_weight<0:raise ValueError('Bad training settings')
    source_hash=source_verified()
    catalog=drill_catalog(args)
    fidelity_file=DATA/'fidelity.json'
    if not fidelity_file.exists():raise RuntimeError('Run REPLAY_2_FIDELITY.bat before training; must verify simulated shots')
    report=json.loads(fidelity_file.read_text(encoding='utf8'))
    whitelist={c['drill'] for c in report.get('cases',[]) if c.get('fid_ok')}
    catalog=[(p,m) for p,m in catalog if str(p.relative_to(ROOT)) in whitelist]
    if not catalog:raise RuntimeError('No approved replay drills in fidelity report')
    import random as pyrandom
    np.random.seed(args.seed);pyrandom.seed(args.seed);torch.manual_seed(args.seed)
    torch.set_num_threads(2)
    run=DATA/'training'/args.run_name;run.mkdir(parents=True,exist_ok=True)
    ckpt=run/'candidate.pt';progress=run/'progress.json'
    # Real AutoLeague lock: stale STATUS.json files don't matter; paused job releases it.
    with exclusive_league_lock(ROOT/'data/autoleague'):
        if ckpt.exists() and not args.resume:raise FileExistsError('Candidate exists: use --resume or choose --run-name')
        actor=load_model();anchor=load_model();anchor.eval()
        for par in anchor.parameters():par.requires_grad_(False)
        critic=TeamCritic();ao=torch.optim.Adam(actor.parameters(),lr=args.lr)
        co=torch.optim.Adam(critic.parameters(),lr=2e-4)
        start_idx=0;done_reps=0
        if args.resume:
            if not ckpt.exists():raise FileNotFoundError(ckpt)
            saved=torch.load(ckpt,map_location='cpu',weights_only=True)
            if saved.get('source_sha')!=source_hash:raise ValueError('Incompatible source checkpoint')
            if saved.get('data_manifest_sha')!=sha256(DATA/'drills.json'):raise ValueError('Drill manifest changed. Refusing unsafe resume.')
            actor.load_state_dict(saved['actor'],strict=True);critic.load_state_dict(saved['critic'])
            ao.load_state_dict(saved['ao']);co.load_state_dict(saved['co'])
            start_idx=int(saved['drill_index']);done_reps=int(saved['reps_done'])
        engine=RocketSimEngine(rlbot_delay=False);observer=TeamObserver();rng=np.random.default_rng(args.seed)
        seen=0
        def save(di,reps,counts):
            snap={'actor':{k:v.detach().cpu().clone() for k,v in actor.state_dict().items()},
                'critic':critic.state_dict(),'ao':ao.state_dict(),'co':co.state_dict(),
                'source_sha':source_hash,'data_manifest_sha':sha256(DATA/'drills.json'),
                'drill_index':di,'reps_done':reps,'counts':dict(counts)}
            temp=ckpt.with_suffix('.partial');torch.save(snap,temp);os.replace(temp,ckpt)
            write_json(progress,{'drill_index':di,'reps_done':reps,'counts':dict(counts),
                  'updated_utc':datetime.now(timezone.utc).isoformat(),'checkpoint':str(ckpt)})
        try:
            for di,(path,meta) in enumerate(catalog):
                if di<start_idx:continue
                counts=Counter();reps_start=done_reps if di==start_idx else 0
                for rep in range(reps_start,args.repeats):
                    drill=DefenseDrill(engine,path)
                    traj=[];last_done=False
                    demos=[]
                    # Expert actions are reconstructed from .replay, not raw controller input.
                    # Apply imitation only when THIS defender is the tagged save player.
                    if drill.defender==drill.save_player and drill.save_step>=0:
                        table=np.asarray(nexto_actions(),dtype=np.float32)
                        weight=np.asarray([1,1,1,1,1,3,2,2],dtype=np.float32)
                        for ix in range(len(drill.controls)):
                            sample=drill.controls[ix,drill.id_pos[drill.defender],:]
                            demos.append(int(np.argmin(((table-sample[None,:])**2*weight).sum(-1))))
                    for t in range(len(drill.controls)):
                        view=observer.observe(drill.state,drill.previous)[drill.defender]
                        a,lp=predicted_action(actor,view,sample=True)
                        with torch.no_grad():val=float(critic(*tensors(view)).item())
                        control=nexto_actions()[a]
                        reward,last_done,info=drill.step(control)
                        traj.append((view,a,lp,val,reward,last_done))
                        if info['conceded']:counts['conceded']+=1
                        if info['touch']:counts['touches']+=1
                        if last_done:break
                    if not traj:raise RuntimeError('Empty drill trajectory')
                    counts['attempts']+=1
                    if not bool(drill.state.goal_scored):counts['survived']+=1
                    if traj[-1][-1]:boot=0.
                    else:
                        v=observer.observe(drill.state,drill.previous)[drill.defender]
                        with torch.no_grad():boot=float(critic(*tensors(v)).item())
                    gae,returns=discounted_gae([x[4] for x in traj],[x[3] for x in traj],
                                                [x[5] for x in traj],boot)
                    q=torch.from_numpy(np.stack([x[0][0] for x in traj])).float()
                    kv=torch.from_numpy(np.stack([x[0][1] for x in traj])).float()
                    mask=torch.from_numpy(np.stack([x[0][2] for x in traj])).float()
                    ac=torch.tensor([x[1] for x in traj],dtype=torch.long)
                    old=torch.tensor([x[2] for x in traj]).float()
                    adv=torch.from_numpy(gae).float();ret=torch.from_numpy(returns).float()
                    adv=(adv-adv.mean())/(adv.std(unbiased=False)+1e-6)
                    for _ in range(args.epochs):
                        for indices in torch.randperm(len(traj)).split(args.rollout):
                            logits=actor_logits(actor,q[indices],kv[indices],mask[indices]);dist=Categorical(logits=logits)
                            ratio=(dist.log_prob(ac[indices])-old[indices]).exp()
                            surr=torch.minimum(ratio*adv[indices],ratio.clamp(.85,1.15)*adv[indices]).mean()
                            with torch.no_grad():ref=actor_logits(anchor,q[indices],kv[indices],mask[indices])
                            kl=F.kl_div(F.log_softmax(logits,-1),F.softmax(ref,-1),reduction='batchmean')
                            loss=-surr+args.anchor*kl-.001*dist.entropy().mean()
                            # If an actual saved shot was tagged, additionally imitate the
                            # recorded defender's inferred actions around that save moment.
                            if demos:
                                eligible=(indices>=max(0,drill.save_step-90)) & (indices<=drill.save_step)
                                if torch.any(eligible):
                                    expert=torch.tensor(demos,dtype=torch.long)[indices[eligible]]
                                    loss += args.bc_weight*F.cross_entropy(logits[eligible],expert)
                            if not torch.isfinite(loss):raise FloatingPointError('Nonfinite PPO')
                            ao.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(actor.parameters(),.5);ao.step()
                            value=critic(q[indices],kv[indices],mask[indices]);vloss=F.mse_loss(value,ret[indices])
                            co.zero_grad();vloss.backward();torch.nn.utils.clip_grad_norm_(critic.parameters(),.5);co.step()
                    seen+=1
                    if (rep+1)%args.save_every==0 or rep+1==args.repeats:
                        save(di,rep+1,counts)
                        print(f'DRILL {di+1}/{len(catalog)} rank={meta["replay_rank"]} defender={drill.defender} lead={meta["lead_seconds"]}s rep={rep+1}/{args.repeats} BC={bool(demos)} touched={counts["touches"]} conceded={counts["conceded"]} KL={float(kl.detach()):.6f}',flush=True)
                    if (run/'STOP_AFTER_REPETITION').exists():
                        save(di,rep+1,counts);print('SAFELY PAUSED. Remove STOP_AFTER_REPETITION to resume.',flush=True);return
                done_reps=0
            save(len(catalog),0,Counter())
            print('Replay defense PPO experiment completed. DO NOT promote without held-out tests and RLBot games.',flush=True)
        finally:engine.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    pre=sub.add_parser('preflight', help='Check replay parser and source actor, no training')
    index=sub.add_parser('index',help='Index .replay files by shots+saves, extract near-shot states')
    index.add_argument('--replays',type=Path,default=DATA/'replays')
    index.add_argument('--max-shots',type=int,default=12)
    index.add_argument('--leads',type=float,nargs='+',default=[1.5,3.0,5.0,10.0])
    index.add_argument('--index-only',action='store_true')
    verify=sub.add_parser('fidelity',help='Test whether scripted replay actions reproduce the dangerous situation')
    verify.add_argument('--max-drills',type=int,default=30)
    verify.add_argument('--max-ball-error',type=float,default=850.)
    trainp=sub.add_parser('train',help='Cycle9 PPO one defender at a time, repeated drills')
    trainp.add_argument('--repeats',type=int,default=32)
    trainp.add_argument('--epochs',type=int,default=2)
    trainp.add_argument('--rollout',type=int,default=64)
    trainp.add_argument('--lr',type=float,default=1e-6)
    trainp.add_argument('--anchor',type=float,default=.1)
    trainp.add_argument('--bc-weight',type=float,default=.025,help='Weak behavior-cloning weight for tagged saved shots')
    trainp.add_argument('--save-every',type=int,default=4)
    trainp.add_argument('--run-name',default='cycle9_replay_defense_v1')
    trainp.add_argument('--seed',type=int,default=104713)
    trainp.add_argument('--resume',action='store_true')
    a=p.parse_args()
    if a.command=='preflight':
        import rlgym_tools
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
        from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
        from rlgym_tools.rocket_league.misc.serialize import serialize_replay_frame,deserialize_replay_frame
        from afk_team_research import TeamObserver
        print('Cycle9 SHA verified:',source_verified()[:16])
        model=load_model()
        print('Replay parser, ReplayFrame serialization, TeamObserver and Cycle9 actor loaded: OK')
        print('PRECHECK PASSED. Nothing trained or overwritten.')
    elif a.command=='index':cmd_index(a)
    elif a.command=='fidelity':fallback_fidelity(a)
    else:train(a)

if __name__=='__main__':main()
