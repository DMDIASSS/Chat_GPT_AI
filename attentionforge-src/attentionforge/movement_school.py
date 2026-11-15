"""Small physics-verified training demonstrations. Never used at inference."""
from pathlib import Path
import os
import numpy as np
from .runtime import batch,atomic_json
from .observation import ACTIONS,encode


def desired(k,task):
    p=r=j=0
    if task=='jump_touch':j=int(1<=k<5)
    else:
        if 1<=k<3:j=1
        elif 4<=k<8:p=1 if task=='half_flip' else -1;j=1
        elif task=='half_flip' and 8<=k<14:p=-1;r=1
        elif task=='half_flip' and 14<=k<22:r=1
    return p,r,j


def action_for(p,r,j,legal):
    values=np.array([0,0,p,0,r,j,0,int(bool(j and (p or r)))],np.float32)
    ix=int(np.flatnonzero(np.all(ACTIONS==values,axis=1))[0])
    if not legal[ix]:
        # After the flip impulse, jump is masked; releasing it preserves the
        # pitch/roll demonstration and produces a genuinely legal label.
        values[5]=values[7]=0;ix=int(np.flatnonzero(np.all(ACTIONS==values,axis=1))[0])
    if not legal[ix]:raise ValueError('Mechanics tutor produced an illegal label')
    return ix


def collect(cfg,n=48,seed=983717):
    all_x=[];all_l=[];all_y=[];records={}
    for ti,task in enumerate(('half_flip','forward_flip','jump_touch')):
        env=batch(cfg,n=n,seed=seed+ti*100003,kickoffs=True);env.scenario(8);raw=env.observe();rng=np.random.default_rng(seed+ti)
        active=np.arange(n)%2
        if task=='forward_flip':
            for a in range(n):
                w=raw['world'][a].copy();w[1:,9:12]*=-1;env.set_ground(a,w)
        elif task=='jump_touch':
            for a in range(n):
                w=raw['world'][a].copy();ego=active[a]+1;other=2 if ego==1 else 1;angle=rng.uniform(-np.pi,np.pi);direction=np.array([np.cos(angle),np.sin(angle),0],np.float32)
                center=rng.uniform([-1200,-1800],[1200,1800]);w[0,:3]=[*center,float(rng.uniform(230,260))];w[0,3:6]=direction*100;w[0,5]=300
                w[ego,:3]=w[0,:3]-direction*400;w[ego,2]=17;w[ego,3:6]=direction*600;w[ego,9:12]=direction;w[ego,12:15]=[0,0,1];w[ego,15]=33
                w[other,:3]=[3500,4200,17];w[other,3:6]=0;env.set_ground(a,w)
        raw=env.observe();loc=env.pad_locations();xs=[];ls=[];ys=[];success=np.zeros(n,np.float32);alive=np.ones(n,bool)
        length=18 if task=='jump_touch' else 32
        complete_at=np.full(n,length+1,np.int64)
        for k in range(length):
            x,l=encode(raw['world'],raw['pads'],loc);ac=np.full((n,2),8,np.int64);p,r,j=desired(k,task)
            for a in range(n):
                agents=(int(active[a]),) if task=='jump_touch' else (0,1)
                for agent in agents:ac[a,agent]=action_for(p,r,j,l[a,agent])
            xs.append(x.copy());ls.append(l.copy());ys.append(ac.copy());eligible=alive.copy();raw=env.step(ac)
            success+=raw['attack_info'][:,{'half_flip':3,'forward_flip':2,'jump_touch':4}[task]]
            if task=='half_flip':finished=success>=.59
            elif task=='jump_touch':finished=success>0
            else:
                cars=raw['final_world'][:,1:];ball=raw['final_world'][:,0:1,:3];direction=ball-cars[:,:,:3];alignment=np.sum(direction*cars[:,:,9:12],axis=-1)/(np.linalg.norm(direction,axis=-1)+1e-6)
                finished=(success>.15)&(cars[:,:,16]>.5).all(1)&(cars[:,:,14]>.8).all(1)&(alignment>.5).all(1)
            first=eligible&finished&(complete_at>length);complete_at[first]=k+1
            alive&=~(raw['terminated']|raw['truncated'])
        good=complete_at<=length
        for a in np.flatnonzero(good):
            for agent in ((int(active[a]),) if task=='jump_touch' else (0,1)):
                for k in range(int(complete_at[a])):all_x.append(xs[k][a,agent]);all_l.append(ls[k][a,agent]);all_y.append(ys[k][a,agent])
        records[task]={'trial_arenas':n,'successful_arenas':int(good.sum()),'label_rows':int(complete_at[good].sum())*(1 if task=='jump_touch' else 2),'criterion':'Actual RocketSim reward event; forward flips additionally require upright forward-facing landing. No student performance is claimed.'}
    if not all_x:return None,records
    return (np.asarray(all_x,np.float32),np.asarray(all_l,bool),np.asarray(all_y,np.int64)),records


def load_rehearsal(cfg,folder):
    path=Path(folder)/'movement_rehearsal_v1.npz';meta=Path(folder)/'movement_rehearsal.json'
    if path.exists():
        with np.load(path,allow_pickle=False) as z:return z['x'],z['legal'],z['y']
    data,records=collect(cfg)
    atomic_json(meta,{'version':1,'seed':983717,'tasks':records,'use':'Training auxiliary only; exported policies contain no scripted controls.'})
    if data is not None:
        temporary=path.with_suffix('.tmp.npz')
        try:
            np.savez_compressed(temporary,x=data[0],legal=data[1],y=data[2]);os.replace(temporary,path)
        finally:
            temporary.unlink(missing_ok=True)
        print('VERIFIED_MOVEMENT_REHEARSAL:',len(data[2]),'labels;',records,flush=True)
    else:print('MOVEMENT_REHEARSAL_UNAVAILABLE: no verified trajectories; PPO rewards remain active.',flush=True)
    return data
