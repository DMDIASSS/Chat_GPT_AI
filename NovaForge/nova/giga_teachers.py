"""CPU interoperability adapters for the pinned Chronos and GalactusV2 exports.

These are simulator ports. Native feature/mask and network comparisons are
recorded separately; they do not establish live-game playing strength.
"""
from __future__ import annotations

import numpy as np
import torch
from torch import nn
from rlgym.rocket_league.action_parsers import LookupTableAction
from rlgym.rocket_league.common_values import BOOST_LOCATIONS

TABLE=np.asarray(LookupTableAction.make_lookup_table(),dtype=np.float32)
BOOSTS=np.asarray(BOOST_LOCATIONS,dtype=np.float32)
MIRROR_PADS=np.array([np.argmin(np.linalg.norm(BOOSTS-xyz*np.array([-1,1,1]),axis=1)) for xyz in BOOSTS])


def native_action_mask(car):
    """Match DefaultAction.cpp, including the original mask application order."""
    ground=np.arange(90)<24
    jump=TABLE[:,5]!=0
    air=(np.arange(90)>24)&~jump
    air |= ground&(TABLE[:,0]==TABLE[:,6])&((TABLE[:,3]!=0)==(TABLE[:,7]!=0))
    mask=(ground if car.on_ground else air).copy()
    if car.boost_amount==0: mask &= TABLE[:,6]==0
    if car.on_ground or car.has_flip: mask |= jump
    # RLGym's public Car state has no world-contact normal; do not invent one.
    return mask


def _physics(po,invert,mirror):
    sign=np.array([-1,-1,1] if invert else [1,1,1],dtype=np.float32)
    pos=po.position*sign
    vel=po.linear_velocity*sign
    ang=po.angular_velocity*sign
    rot=sign[:,None]*po.rotation_mtx
    if mirror:
        pos=pos*np.array([-1,1,1],dtype=np.float32)
        vel=vel*np.array([-1,1,1],dtype=np.float32)
        ang=ang*np.array([1,-1,-1],dtype=np.float32)
        rot=np.array([-1,1,1],dtype=np.float32)[:,None]*rot
        rot[:,1]*=-1
    return pos,vel,ang,rot


def _player(car,invert,mirror,ball):
    pos,vel,ang,rot=_physics(car.physics,invert,mirror)
    return np.concatenate((pos/5000,rot[:,0],rot[:,2],vel/2300,ang/3,
        (ang@rot)/3,((ball[0]-pos)@rot)/5000,((ball[1]-vel)@rot)/2300,
        [car.boost_amount/100,car.on_ground,car.on_ground or car.has_flip,
         car.is_demoed,car.has_jumped])).astype(np.float32)


def build_features(state,agent,previous,rng,kind,predictions=None,opponent_slot=None):
    if len(state.cars)!=2 or {c.team_num for c in state.cars.values()}!={0,1}:
        raise ValueError('GigaLearn teacher ports currently support 1v1 only')
    own=state.cars[agent]
    other=next(c for k,c in state.cars.items() if k!=agent)
    invert=own.team_num==1
    mirror=kind=='chronos' and own.physics.position[0]*(-1 if invert else 1)>0
    ball=_physics(state.ball,invert,mirror)
    prev=np.asarray(previous,dtype=np.float32).copy()
    timers=state.boost_pad_timers[::-1] if invert else state.boost_pad_timers
    pads=timers==0
    # The pinned Chronos GameState getter swaps timer orientation relative to
    # availability. Preserve its deployed features rather than correcting them.
    timer_features=timers[::-1] if kind=='chronos' else timers
    features=np.where(pads,1.,1/(1+timer_features))
    if mirror:
        features=features[MIRROR_PADS]
        prev[[1,3,4]]*=-1
    parts=[ball[0]/5000,ball[1]/2300,ball[2]/3,prev,features]
    if kind=='galactus':
        pos=own.physics.position*np.array([-1,-1,1] if invert else [1,1,1])
        relative=np.zeros(3,dtype=np.float32)
        distance=1500**2
        for i in [3,4,15,18,29,30]:
            delta=BOOSTS[i]-pos
            d=float(np.square(delta[:2]).sum())
            if pads[i] and d<=distance: relative=delta;distance=d
        parts.append(relative/5000)
    parts.extend([_player(own,invert,mirror,ball),np.zeros(58,dtype=np.float32)])
    slots=np.zeros((3,29),dtype=np.float32)
    slot=int(rng.integers(3)) if opponent_slot is None else int(opponent_slot)
    slots[slot]=_player(other,invert,mirror,ball)
    parts.append(slots.ravel())
    if kind=='galactus':
        if predictions is None or predictions.shape!=(5,6): raise ValueError('Expected five ball prediction samples')
        pred=predictions.copy()
        if invert: pred*=np.array([-1,-1,1,-1,-1,1],dtype=np.float32)
        pred[:,:3]/=5000
        pred[:,3:]/=2300
        parts.append(pred.ravel())
    out=np.concatenate(parts).astype(np.float32)
    expected=225 if kind=='chronos' else 258
    if out.shape!=(expected,) or not np.isfinite(out).all(): raise ValueError('Invalid native teacher features')
    return out,mirror


def _load_sequence(path,widths,input_size,activation,output=None):
    layers=[]
    size=input_size
    for width in widths:
        layers.extend([nn.Linear(size,width),nn.LayerNorm(width),activation()])
        size=width
    if output is not None: layers.append(nn.Linear(size,output))
    seq=nn.Sequential(*layers)
    if path is not None:
        archive=torch.jit.load(str(path),map_location='cpu')
        seq.load_state_dict(dict(archive.named_parameters()),strict=True)
    seq.requires_grad_(False)
    return seq.eval()


class GigaNetwork(nn.Module):
    def __init__(self,path,kind):
        super().__init__()
        if kind=='chronos':
            first=225;shared=[960,960];policy=[960,800,640,640];act=nn.ReLU
        elif kind=='galactus':
            first=258;shared=[1024,1024];policy=[1024]*4;act=nn.LeakyReLU
        else: raise ValueError(kind)
        self.head=_load_sequence(path/'SHARED_HEAD.lt' if path is not None else None,shared,first,act)
        self.policy=_load_sequence(path/'POLICY.lt' if path is not None else None,policy,shared[-1],act,90)
    def forward(self,x):
        return self.policy(self.head(x))


class BallForecast:
    def __init__(self):
        import RocketSim as rs
        self.rs=rs
        self.arena=rs.Arena(rs.GameMode.SOCCAR)
        self.last_tick=None
        self.pred=None
    def reset(self):
        self.last_tick=None
    def samples(self,state):
        if self.last_tick is None or state.tick_count-self.last_tick>=32:
            rs=self.rs
            self.arena.ball.set_state(rs.BallState(pos=rs.Vec(*state.ball.position),
                vel=rs.Vec(*state.ball.linear_velocity),ang_vel=rs.Vec(*state.ball.angular_velocity)))
            self.pred=np.empty((273,6),dtype=np.float32)
            for i in range(273):
                ball=self.arena.ball.get_state()
                self.pred[i]=[*ball.pos.as_numpy(),*ball.vel.as_numpy()]
                if i<272: self.arena.step(1)
            self.last_tick=state.tick_count
        age=int(state.tick_count-self.last_tick)
        return self.pred[np.array([30,60,120,180,240])+age].copy()


class GigaTeacher:
    def __init__(self,kind):
        from .teachers import verify_teacher
        self.kind=kind
        from .inference import frozen_inference
        self.network=frozen_inference(GigaNetwork(verify_teacher(kind),kind))
        self.forecast=BallForecast() if kind=='galactus' else None

    def reset(self,state,agent,rng):
        self.agent=agent
        self.rng=rng
        self.origin=state.tick_count
        self.last_call=None
        self.obs_previous=np.zeros(8,dtype=np.float32)
        self.held=np.zeros(8,dtype=np.float32)
        self.pending=None
        if self.forecast: self.forecast.reset()

    def controls_for_ticks(self,state,ticks=4):
        if ticks not in (2,4): raise ValueError('Native teacher scheduling expects two- or four-tick simulator calls')
        tick=int(state.tick_count-self.origin)
        if tick%2 or self.last_call==tick: raise ValueError('Native teacher must be advanced once per simulator state')
        self.last_call=tick
        if tick%8==0:
            pred=self.forecast.samples(state) if self.forecast else None
            obs,mirror=build_features(state,self.agent,self.obs_previous,self.rng,self.kind,pred)
            with torch.inference_mode(): logits=self.network(torch.from_numpy(obs)[None,:])[0].numpy()
            if not np.isfinite(logits).all(): raise ValueError('Nonfinite native policy logits')
            mask=native_action_mask(state.cars[self.agent])
            if not mask.any(): raise ValueError('Native action mask has no valid action')
            planned=TABLE[int(np.where(mask,logits,-np.inf).argmax())].copy()
            if mirror: planned[[1,3,4]]*=-1
            self.obs_previous=planned.copy()
            self.pending=(tick+7,planned)
        result=np.repeat(self.held[None,:],ticks,axis=0)
        if self.pending is not None:
            due,command=self.pending
            if due<tick+ticks:
                result[max(0,due-tick):]=command
                self.held=command.copy()
                self.pending=None
        return result
