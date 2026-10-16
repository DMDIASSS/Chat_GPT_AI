"""Read-only GigaLearn MLP inference. C++ parity is required before evaluation."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from nexto_teacher import nexto_actions
from slater_v041_core import sha256

FILES=('POLICY.lt','SHARED_HEAD.lt','CRITIC.lt','RUNNING_STATS.json')

def checkpoint_identity(path):
    path=Path(path).resolve()
    if not path.is_dir() or not all((path/n).is_file() for n in FILES):raise ValueError('Need a complete native checkpoint folder: '+str(path))
    return {'path':str(path),'files':{n:sha256(path/n) for n in FILES}}

def sequence(path):
    archive=torch.jit.load(str(path),map_location='cpu')
    layers=[]
    for i,(name,module) in enumerate(archive.named_children()):
        if name!=str(i):raise ValueError('Unsupported native archive module layout')
        weights=dict(module.named_parameters(recurse=False))
        if not weights:layer=nn.ReLU()
        elif set(weights)=={'weight','bias'} and weights['weight'].ndim==2:
            w=weights['weight'];layer=nn.Linear(w.shape[1],w.shape[0])
        elif set(weights)=={'weight','bias'} and weights['weight'].ndim==1:
            layer=nn.LayerNorm(weights['weight'].numel(),eps=1e-5)
        else:raise ValueError('Unsupported native archive layer')
        if weights:layer.load_state_dict(weights,strict=True)
        layers.append(layer)
    if not layers:raise ValueError('Empty native model')
    return nn.Sequential(*layers).eval()

class NativeActor(nn.Module):
    def __init__(self,path):
        super().__init__();self.identity=checkpoint_identity(path)
        self.shared=sequence(Path(path)/'SHARED_HEAD.lt');self.policy=sequence(Path(path)/'POLICY.lt')
        if not isinstance(self.shared[0],nn.Linear) or self.shared[0].in_features!=230 or self.policy[-1].out_features!=90:
            raise ValueError('Only this backend\'s padded 230/90 ReLU MLP is supported')
        self.width=self.shared[0].out_features
        self.depth=sum(isinstance(m,nn.ReLU) for m in self.policy)
        self.eval()
    def forward(self,obs):return self.policy(self.shared(obs))
    def probabilities(self,obs,mask):
        if not mask.any(-1).all():raise ValueError('No feasible action')
        return (self(obs)+(-1e10)*(~mask.bool()).float()).softmax(-1).clamp(1e-11,1)

def packet(state,previous,engine=None):
    """Current state only; role order follows numeric simulator car IDs."""
    from rlgym.rocket_league.common_values import BOOST_LOCATIONS
    ids=list(state.cars)
    if engine is not None:ids.sort(key=lambda aid:engine._cars[aid].id)
    else:ids.sort(key=lambda aid:(state.cars[aid].team_num,str(aid)))
    ids_by_agent={aid:i+1 for i,aid in enumerate(ids)}
    def physics(p):return {'pos':np.asarray(p.position).tolist(),'rot':np.asarray(p.rotation_mtx).T.reshape(-1).tolist(),
        'vel':np.asarray(p.linear_velocity).tolist(),'ang':np.asarray(p.angular_velocity).tolist()}
    timers=np.asarray(state.boost_pad_timers).copy()
    if engine is not None:
        pads=engine._arena.get_boost_pads()
        # Python wheels need not enumerate pads in the bundled C++ order.
        positions=np.array([p.get_pos().as_numpy() for p in pads])
        order=np.linalg.norm(np.asarray(BOOST_LOCATIONS)[:,None,:]-positions[None,:,:],axis=-1).argmin(1)
        timers=timers[order]
    cars=[]
    for aid in ids:
        c=state.cars[aid];raw=engine._cars[aid].get_state() if engine is not None else None
        cars.append({'id':ids_by_agent[aid],'agent':str(aid),'team':int(c.team_num),**physics(c.physics),
          'boost':float(c.boost_amount),'ground':bool(raw.is_on_ground) if raw is not None else bool(c.on_ground),'jumped':bool(c.has_jumped),
          'double_jumped':bool(c.has_double_jumped),'flipped':bool(c.has_flipped),'air_time':float(c.air_time_since_jump),
          'demo':bool(c.is_demoed),'world_contact':bool(raw.has_world_contact) if raw is not None else False,
          'contact_normal':raw.world_contact_normal.as_numpy().tolist() if raw is not None else [0,0,0],
          'previous':np.asarray(previous.get(aid,np.zeros(8)),dtype=np.float32).tolist()})
    result={'ball':physics(state.ball),'timers':timers.tolist(),'cars':cars}
    if len(cars) not in (2,4,6) or not np.isfinite(np.array(timers)).all():raise ValueError('Unsupported native state')
    return result,ids_by_agent

def flip_available(car):return car['ground'] or (not car['flipped'] and not car['double_jumped'] and car['air_time']<1.25)

def observation(p,query):
    car=next(c for c in p['cars'] if c['id']==query);inv=np.array([-1,-1,1],dtype=np.float32) if car['team'] else np.ones(3,dtype=np.float32)
    def phys(b):
        return [np.asarray(b[k],dtype=np.float32)*inv for k in ('pos','vel','ang')]+[np.asarray(b['rot'],dtype=np.float32).reshape(3,3).T*inv[:,None]]
    bp,bv,ba,_=phys(p['ball'])
    timers=np.asarray(p['timers'],dtype=np.float32)
    # Preserve the pinned upstream accessor's historical reversed timer branch.
    # Pad availability is correctly oriented, but cooldowns use the other side.
    # Fixing this here would silently change the observations learned in C++.
    active=(timers<=0)[::-1] if car['team'] else timers<=0
    cooldown=timers if car['team'] else timers[::-1]
    out=[*(bp/5000),*(bv/2300),*(ba/3),*car['previous'],*np.where(active,1,1/(1+cooldown))]
    def block(c):
        pos,vel,ang,rot=phys(c)
        return np.concatenate((pos/5000,rot[:,0],rot[:,2],vel/2300,ang/3,rot.T@ang/3,
            rot.T@(bp-pos)/5000,rot.T@(bv-vel)/2300,[c['boost']/100,c['ground'],flip_available(c),c['demo'],c['jumped']])).tolist()
    out+=block(car)
    for same,slots in ((True,2),(False,3)):
        others=sorted([c for c in p['cars'] if c['id']!=query and (c['team']==car['team'])==same],key=lambda c:c['id'])
        for i in range(slots):out+=(block(others[i])+[1]) if i<len(others) else [0]*30
    out=np.asarray(out,dtype=np.float32)
    if out.shape!=(230,) or not np.isfinite(out).all():raise ValueError('Invalid native observation')
    return out

def action_mask(car):
    a=nexto_actions();idx=np.arange(len(a));ground=idx<24
    # Match upstream's strict i > numGroundActions, including its index-24 edge.
    air=((idx>24)&(a[:,5]==0)) | (ground&(a[:,0]==a[:,6])&((a[:,3]!=0)==a[:,7].astype(bool)))
    result=(ground if car['ground'] else air).copy()
    if car['boost']==0:result[a[:,6]!=0]=False
    if flip_available(car) or (car['world_contact'] and car['contact_normal'][2]>.9):result[a[:,5]!=0]=True
    if not result.any():raise ValueError('No native feasible action')
    return result

def infer(actor,p,query):
    car=next(c for c in p['cars'] if c['id']==query)
    with torch.no_grad():return int(actor.probabilities(torch.from_numpy(observation(p,query)[None]),torch.from_numpy(action_mask(car)[None])).argmax(-1))
