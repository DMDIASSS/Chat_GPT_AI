"""Octane expert ports. Model-specific observations, masks and 6/8-tick clocks.

These are simulator ports, not a claim of native playing-strength parity.
Ducky's V3 ball-prediction backend is approximated by installed RocketSim.
"""
from __future__ import annotations
import numpy as np
import torch
from torch import nn
from .giga_teachers import TABLE,BOOSTS,_physics,_player,_load_sequence,build_features,GigaNetwork,BallForecast,native_action_mask
from .core import check_model
from .teachers import verify_teacher

NAMES=('chronos','galactus','fusion','ducky','rain','megabyte')
PERIODS=dict(chronos=8,galactus=8,fusion=8,ducky=8,rain=6,megabyte=8)


def action_mask(car,kind):
    mask=native_action_mask(car)
    if kind=='ducky' and not car.on_ground:mask[24]=True # corrected >= ground-count boundary
    return mask


def _pads(state,invert,kind):
    timers=np.asarray(state.boost_pad_timers,dtype=np.float32)
    oriented=timers[::-1] if invert else timers
    # Rain's getter and the deployed ByteObs intentionally use opposite timers.
    legacy=oriented[::-1] if kind in ('rain','megabyte') else oriented
    return np.where(oriented==0,1.,1/(1+legacy)).astype(np.float32),oriented


def _ducky_player(car,own,invert,ball,self_slot):
    p,v,a,rot=_physics(car.physics,invert,False)
    op,ov,_,orr=_physics(own.physics,invert,False)
    parts=[p/5000,rot[:,0],rot[:,2],v/2300,(a@rot)/3,
        ((ball[0]-p)@rot)/5000,((ball[1]-v)@rot)/2300]
    if not self_slot:parts += [((p-op)@orr)/5000,((v-ov)@orr)/2300]
    dodge=1. if car.on_ground else (0. if car.has_flipped or car.has_double_jumped else max(0.,1-car.air_time_since_jump/1.25))
    parts.append([car.boost_amount/100,car.on_ground,car.on_ground or car.has_flip,
        car.is_demoed,car.has_jumped,1/(1+car.demo_respawn_timer),dodge,car.is_supersonic])
    return np.concatenate(parts).astype(np.float32)


def _best_pad(own,invert,timers,big):
    p,v,_,rot=_physics(own.physics,invert,False)
    ids=np.flatnonzero((BOOSTS[:,2]>71)==big)
    delta=BOOSTS[ids,:2]-p[:2];dist=np.linalg.norm(delta,axis=1)
    speed=float(np.linalg.norm(v[:2]));direction=v[:2]/speed if speed>1 else np.zeros(2)
    alignment=np.ones(len(ids),np.float32)
    valid=dist>1;alignment[valid]=(delta[valid]@direction)/dist[valid]
    cost=dist*(1+min(speed/2300,1)*(1-alignment))
    available=timers[ids]<=3
    pick=int(np.where(available,cost,np.inf).argmin()) if available.any() else int(dist.argmin())
    return ((BOOSTS[ids[pick]]-p)@rot)[:2]/5000


def features(state,agent,previous,rng,kind,predictions=None,opponent_slot=None):
    if len(state.cars)!=2 or {c.team_num for c in state.cars.values()}!={0,1}:raise ValueError('New expert ports currently support 1v1')
    own=state.cars[agent];other=next(c for k,c in state.cars.items() if k!=agent)
    inv=own.team_num==1;ball=_physics(state.ball,inv,False)
    pads,timers=_pads(state,inv,kind)
    parts=[ball[0]/5000,ball[1]/2300,ball[2]/3]
    if kind=='rain':
        # Preserve the pinned source's goal convention, including its orange side.
        own_goal=np.array([0,6000 if inv else -6000,642.775/2],np.float32)
        enemy_goal=own_goal*np.array([1,-1,1],np.float32)
        parts += [(own_goal-ball[0])/5000,(enemy_goal-ball[0])/5000]
    parts += [np.asarray(previous,dtype=np.float32),pads]
    if kind=='ducky':
        parts += [_ducky_player(own,own,inv,ball,True),np.zeros(70,np.float32)]
        slots=np.zeros((3,35),np.float32)
        slots[int(rng.integers(3)) if opponent_slot is None else opponent_slot]=_ducky_player(other,own,inv,ball,False)
        parts.append(slots.ravel())
        if predictions is None or predictions.shape!=(3,6):raise ValueError('Ducky needs predictions at .3, 1 and 3 seconds')
        p,v,_,rot=_physics(own.physics,inv,False)
        sign=np.array([-1,-1,1,-1,-1,1] if inv else [1]*6,np.float32)
        for predicted in predictions*sign:
            parts += [predicted[:3]/5000,predicted[3:]/2300,((predicted[:3]-p)@rot)/5000,((predicted[3:]-v)@rot)/2300]
        parts += [_best_pad(own,inv,timers,True),_best_pad(own,inv,timers,False)]
    elif kind in ('rain','megabyte'):
        slot_size=30 if kind=='megabyte' else 29
        def player(c):
            values=_player(c,inv,False,ball)
            return np.r_[values,np.float32(1)] if kind=='megabyte' else values
        if kind=='megabyte':parts.append([0,1/3])
        parts += [player(own),np.zeros(slot_size*2,np.float32)]
        slots=np.zeros((3,slot_size),np.float32)
        # Rain preserves source order; Byte/Ducky shuffle their padded slots.
        slot=0 if kind=='rain' else (int(rng.integers(3)) if opponent_slot is None else opponent_slot)
        slots[slot]=player(other);parts.append(slots.ravel())
    else:raise ValueError(kind)
    out=np.concatenate(parts).astype(np.float32)
    if out.shape!=({'ducky':295,'rain':231,'megabyte':233}[kind],) or not np.isfinite(out).all():raise ValueError('Invalid expert features')
    return out


class ExtraNetwork(nn.Module):
    def __init__(self,path,kind):
        super().__init__()
        if kind=='ducky':size=295;shared=[];policy=[512,512,512,256]
        elif kind=='rain':size=231;shared=[1280];policy=[1024,768,512,256]
        elif kind=='megabyte':size=233;shared=[1024,1024];policy=[1024,1024,512,512]
        else:raise ValueError(kind)
        self.head=_load_sequence(path/'SHARED_HEAD.lt',shared,size,nn.ReLU) if shared else nn.Identity()
        self.policy=_load_sequence(path/'POLICY.lt',policy,shared[-1] if shared else size,nn.ReLU,90)
        self.eval().requires_grad_(False)
    def forward(self,x):return self.policy(self.head(x))


class DuckyForecast:
    def __init__(self):
        from rlgym.rocket_league.sim import RocketSimEngine
        engine=RocketSimEngine();engine.close()
        import RocketSim as rs
        self.rs=rs;self.arena=rs.Arena(rs.GameMode.SOCCAR);self.reset()
    def reset(self):self.last=None
    def samples(self,state):
        if self.last is None or state.tick_count-self.last>=24 or state.tick_count<self.last:
            rs=self.rs;self.last=state.tick_count
            self.arena.ball.set_state(rs.BallState(pos=rs.Vec(*state.ball.position),vel=rs.Vec(*state.ball.linear_velocity),ang_vel=rs.Vec(*state.ball.angular_velocity)))
            self.pred=np.empty((385,6),np.float32)
            for i in range(385):
                b=self.arena.ball.get_state();self.pred[i]=[*b.pos.as_numpy(),*b.vel.as_numpy()]
                if i<384:self.arena.step(1)
        return self.pred[np.array([36,120,360])+int(state.tick_count-self.last)].copy()


class Pool:
    names=NAMES
    def __init__(self,fusion):
        from .chronos import CHRONOS_CONTRACT
        check_model(fusion,CHRONOS_CONTRACT)
        from rlgym.rocket_league.sim import RocketSimEngine
        setup=RocketSimEngine();setup.close()
        self.models={n:GigaNetwork(verify_teacher(n),n) for n in ('chronos','galactus')}
        self.models['fusion']=torch.jit.load(str(fusion),map_location='cpu').eval()
        self.models.update({n:ExtraNetwork(verify_teacher(n),n) for n in ('ducky','rain','megabyte')})
        for model in self.models.values():
            for parameter in model.parameters():parameter.requires_grad_(False)
        self.forecasts={'galactus':BallForecast(),'ducky':DuckyForecast()}
    def reset(self,state,agent,rng):
        self.agent=agent;self.rng=rng
        for forecast in self.forecasts.values():forecast.reset()
    def command(self,name,state,previous):
        if name in ('chronos','fusion','galactus'):
            kind='chronos' if name=='fusion' else name
            pred=self.forecasts[kind].samples(state) if kind=='galactus' else None
            obs,mirror=build_features(state,self.agent,previous,self.rng,kind,pred)
        else:
            pred=self.forecasts['ducky'].samples(state) if name=='ducky' else None
            obs=features(state,self.agent,previous,self.rng,name,pred);mirror=False
        with torch.inference_mode():logits=self.models[name](torch.from_numpy(obs)[None,:])[0].numpy()
        if logits.shape!=(90,) or not np.isfinite(logits).all():raise ValueError('Invalid '+name+' logits')
        command=TABLE[int(np.where(action_mask(state.cars[self.agent],name),logits,-np.inf).argmax())].copy()
        if mirror:command[[1,3,4]]*=-1
        return command


class Clock:
    """Only the selected frozen expert is inferred; switches preserve held controls."""
    def __init__(self,pool,gate=None,counts=None):
        self.pool=pool;self.gate=gate;self.counts=np.zeros(6,np.int64) if counts is None else counts
        self.fixed_choice=None;self.initialized=False
    def reset(self,state,agent,rng):
        self.pool.reset(state,agent,rng);self.agent=agent;self.rng=rng
        self.gate_rng=np.random.default_rng(int(rng.integers(2**32)))
        self.held=np.zeros(8,np.float32);self.previous=np.zeros(8,np.float32)
        self.pending=None;self.next_query=None;self.next_gate=None;self.last_choice=None;self.initialized=True
        if self.gate:self.gate.reset()
    def update(self,state):
        frame=int(state.tick_count)
        if self.pending is not None and frame>=self.pending[0]:self.held=self.pending[1].copy();self.pending=None
        if self.next_gate is None or frame>=self.next_gate:
            if self.fixed_choice is None:
                obs,_=build_features(state,self.agent,self.previous,self.gate_rng,'chronos')
                if hasattr(self,'observer'):self.observer(obs)
                choice=self.gate.choose(obs)
            else:choice=int(self.fixed_choice)
            self.counts[choice]+=1;self.next_gate=frame+8
            if choice!=self.last_choice:
                self.last_choice=choice;self.next_query=frame;self.pending=None
                # A newly selected expert sees controls actually held by the car.
                self.previous=self.held.copy()
        name=NAMES[self.last_choice]
        if frame>=self.next_query:
            command=self.pool.command(name,state,self.previous)
            self.previous=command.copy();self.pending=(frame+PERIODS[name]-1,command)
            self.next_query=frame+PERIODS[name]
        return self.held.copy()
    def controls_for_ticks(self,state,ticks=2):
        result=np.repeat(self.update(state)[None,:],ticks,axis=0)
        if self.pending is not None:
            due,command=self.pending
            if due<int(state.tick_count)+ticks:
                result[max(0,due-int(state.tick_count)):]=command;self.held=command.copy();self.pending=None
        return result


class NativeExpert:
    """Standalone new opponent, with native period and deterministic model actions."""
    def __init__(self,name):
        self.name=name;self.network=ExtraNetwork(verify_teacher(name),name)
        self.forecast=DuckyForecast() if name=='ducky' else None
    def reset(self,state,agent,rng):
        self.agent=agent;self.rng=rng;self.next_tick=int(state.tick_count)
        self.held=np.zeros(8,np.float32);self.previous=np.zeros(8,np.float32);self.pending=None
        if self.forecast:self.forecast.reset()
    def controls_for_ticks(self,state,ticks=2):
        if self.name=='rain' and ticks!=2:raise ValueError('Rain requires the new two-tick selector simulator path')
        frame=int(state.tick_count)
        if frame>=self.next_tick:
            pred=self.forecast.samples(state) if self.forecast else None
            obs=features(state,self.agent,self.previous,self.rng,self.name,pred)
            with torch.inference_mode():logits=self.network(torch.from_numpy(obs)[None,:])[0].numpy()
            if not np.isfinite(logits).all():raise ValueError('Nonfinite opponent logits')
            planned=TABLE[int(np.where(action_mask(state.cars[self.agent],self.name),logits,-np.inf).argmax())].copy()
            self.previous=planned;self.pending=(frame+PERIODS[self.name]-1,planned);self.next_tick=frame+PERIODS[self.name]
        result=np.repeat(self.held[None,:],ticks,axis=0)
        if self.pending is not None:
            due,command=self.pending
            if due<frame+ticks:
                result[max(0,due-frame):]=command;self.held=command.copy();self.pending=None
        return result


def transition(env,clock):
    """One eight-tick PPO transition, simulated in two-tick batches."""
    arena=env.arena
    if arena.cfg.get('chronos',{}).get('reward_profile')!='potential_goal_v2':raise ValueError('Six-expert native stepping requires potential_goal_v2')
    initial=arena.potential(arena.state)
    for _ in range(4):
        _,_,terminal,truncated,info=arena.step_control_ticks(clock.controls_for_ticks(arena.state,2),2)
        if terminal or truncated:break
    env.previous=clock.previous.copy();env.held=clock.held.copy()
    parts={'goal':arena.objective['goal']*info.get('outcome',0)}
    if arena.cfg['rewards']!='sparse':parts['potential']=arena.cfg['ppo']['gamma']*(0. if terminal else arena.potential(arena.state))-initial
    reward=float(sum(parts.values()));env.reward_total+=reward;env.decisions+=1
    for k,v in parts.items():env.reward_parts[k]=env.reward_parts.get(k,0.)+v
    if 'episode' in info:info.update(episode={'r':env.reward_total,'l':env.decisions},reward_parts=dict(env.reward_parts))
    return env.observation(),reward,terminal,truncated,info
