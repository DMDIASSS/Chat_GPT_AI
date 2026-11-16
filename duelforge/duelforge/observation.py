"""109-float observation and DF90-v1 mask, shared by training tests and exports.
Feature order/normalization follows pinned GGL AdvancedObs for 1v1.
Mask deliberately fixes boost-addition ordering and uses an observable turtle proxy.
"""
import numpy as np

def action_table():
    rows=[]
    for t in (-1,0,1):
        for s in (-1,0,1):
            for b in (0,1):
                for h in (0,1):
                    if b and t!=1:continue
                    rows.append([t,s,0,s,0,0,b,h])
    for p in (-1,0,1):
        for y in (-1,0,1):
            for r in (-1,0,1):
                for j in (0,1):
                    for b in (0,1):
                        if j and y:continue
                        if p==r==j==0:continue
                        rows.append([b,y,p,y,r,j,b,int(j and (p or y or r))])
    return np.asarray(rows,dtype=np.float32)
ACTIONS=action_table()


def encode(world,pads,locations):
    world=np.asarray(world,dtype=np.float32);pads=np.asarray(pads,dtype=np.float32);locations=np.asarray(locations,dtype=np.float32)
    if world.ndim!=3 or world.shape[1:]!=(3,32) or pads.shape!=(len(world),34,2) or locations.shape!=(34,4):raise ValueError('Standard 1v1 observation shapes required')
    rotated=locations[:,:3]*np.array([-1,-1,1],np.float32);dist=((rotated[:,None]-locations[None,:,:3])**2).sum(-1);inverse=dist.argmin(-1)
    if np.max(np.min(dist,axis=1))>.01:raise ValueError('Boost-pad rotation is inconsistent')
    n=len(world);obs=np.empty((n,2,109),np.float32);mask=np.empty((n,2,90),bool)
    for a in (0,1):
        sign=np.array([-1,-1,1] if a else [1,1,1],np.float32);ball=world[:,0,:9]*np.tile(sign,3)
        ego=world[:,a+1];pad=pads[:,inverse if a else np.arange(34)]
        pieces=[ball[:,:3]/5000,ball[:,3:6]/2300,ball[:,6:9]/3,ego[:,21:29],np.where(pad[:,:,0]>.5,1,1/(1+pad[:,:,1]))]
        for b in (a,1-a):
            car=world[:,b+1];s=car[:,:15]*np.tile(sign,5);f=s[:,9:12];up=s[:,12:15];right=np.cross(up,f)
            pieces.extend([s[:,:3]/5000,s[:,9:15],s[:,3:6]/2300,s[:,6:9]/3])
            for val in (s[:,6:9]/3,(ball[:,:3]-s[:,:3])/5000,(ball[:,3:6]-s[:,3:6])/2300):pieces.append(np.stack([(f*val).sum(-1),(right*val).sum(-1),(up*val).sum(-1)],axis=-1))
            pieces.append(np.stack([car[:,15]/100,car[:,16],car[:,29],car[:,20],car[:,17]],axis=-1))
        obs[:,a]=np.concatenate(pieces,axis=-1)
        ground=ego[:,16]>.5;can=(ego[:,29]>.5)|((ego[:,14]<-.5)&(ego[:,2]<65));ix=np.arange(90)
        air=((ix>=24)&(ACTIONS[:,5]==0))|((ix<24)&(ACTIONS[:,0]==ACTIONS[:,6])&((ACTIONS[:,3]!=0)==ACTIONS[:,7].astype(bool)))
        legal=np.where(ground[:,None],ix[None]<24,air[None]);legal|=can[:,None]&(ACTIONS[None,:,5]>0);legal&=~((ego[:,15,None]<=0)&(ACTIONS[None,:,6]>0));mask[:,a]=legal
    return obs,mask
