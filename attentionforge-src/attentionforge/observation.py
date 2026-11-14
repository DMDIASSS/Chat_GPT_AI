"""Public-state observation contract shared by native training and RLBot export.
world: [arenas, 1+cars,32], ordered ball,blue cars,orange cars.
No privileged opponent actions, intent, private flip timers or simulator IDs.
"""
import numpy as np

def action_table():
    a=[]
    for t in (-1,0,1):
        for s in (-1,0,1):
            for b in (0,1):
                for h in (0,1):
                    if b and t!=1:continue
                    a.append([t,s,0,s,0,0,b,h])
    for p in (-1,0,1):
        for y in (-1,0,1):
            for r in (-1,0,1):
                for j in (0,1):
                    for b in (0,1):
                        if j and y:continue
                        if p==r==j==0:continue
                        a.append([b,y,p,y,r,j,b,int(j and (p or y or r)!=0)])
    return np.asarray(a,np.float32)
ACTIONS=action_table()

def encode(world,pads,locations):
    world=np.asarray(world,np.float32); pads=np.asarray(pads,np.float32)
    e,rows,_=world.shape; n=rows-1;team=n//2
    if n not in (2,4,6):raise ValueError('Only balanced 1v1, 2v2, 3v3 are supported')
    ego=world[:,1:]; sign=np.where(np.arange(n)<team,1.,-1.).astype(np.float32)
    # A right-handed basis in RocketSim has right = up cross forward.
    f=ego[:,:,9:12];u=ego[:,:,12:15];right=np.cross(u,f)
    basis=np.stack([f,right,u],axis=-1)
    out=np.zeros((e,n,43,40),np.float32)
    selected=np.zeros((e,n,43,32),np.float32)
    types=np.zeros((n,43),np.int64)
    for a in range(n):
        own=list(range(0,team) if a<team else range(team,n));own.remove(a)
        opp=list(range(team,n) if a<team else range(0,team))
        selected[:,a,0]=ego[:,a];types[a,0]=1
        selected[:,a,1]=world[:,0];types[a,1]=2
        for j,b in enumerate(own):selected[:,a,2+j]=ego[:,b];types[a,2+j]=3
        for j,b in enumerate(opp):selected[:,a,4+j]=ego[:,b];types[a,4+j]=4
    selected[:,:,7:41,:3]=locations[None,None,:,:3];types[:,7:41]=5
    selected[:,:,41,1]=-sign[None,:]*5120;selected[:,:,42,1]=sign[None,:]*5120
    selected[:,:,41:43,2]=300;types[:,41:43]=6
    rel=selected[:,:,:,:3]-ego[:,:,None,:3]
    relvel=selected[:,:,:,3:6]-ego[:,:,None,3:6];relvel[:,:,0]=ego[:,:,3:6]
    out[:,:,:,0:3]=np.einsum('eaki,eaij->eakj',rel,basis)/4096
    out[:,:,:,3:6]=np.einsum('eaki,eaij->eakj',relvel,basis)/2300
    out[:,:,:,6:9]=np.einsum('eaki,eaij->eakj',selected[:,:,:,6:9],basis)/5.5
    rotation=np.stack([sign,sign,np.ones(n,np.float32)],axis=-1)[None,:,None,:]
    out[:,:,:,9:12]=selected[:,:,:,9:12]*rotation
    out[:,:,:,12:15]=selected[:,:,:,12:15]*rotation
    out[:,:,1,9:15]=0 # Ball orientation is not a portable public-state feature.
    out[:,:,:,15]=selected[:,:,:,15]/100
    out[:,:,:,16:21]=selected[:,:,:,16:21]
    out[:,:,:,23]=1-selected[:,:,:,18]
    out[:,:,:,24:27]=selected[:,:,:,:3]*rotation/np.array([4096,5120,2044],np.float32)
    out[:,:,7:41,28]=locations[None,None,:,3]
    out[:,:,41,28]=-1;out[:,:,42,28]=1
    out[:,:,7:41,29]=pads[:,None,:,0];out[:,:,7:41,30]=pads[:,None,:,1]/10
    out[:,:,0,31:39]=ego[:,:,21:29]
    out[:,:,:,39]=types[None]
    # Padded entities must be entirely zero, including derived geometry.
    out*= (types[None,:,:,None]!=0)
    legal=np.ones((e,n,90),bool)
    # Do not mask a first jump merely because a car left a surface; resets are valid.
    no_jump=(ego[:,:,18]>0.5)|(ego[:,:,20]>0.5)
    legal&=~(no_jump[:,:,None]&(ACTIONS[None,None,:,5]>0))
    legal&=~((ego[:,:,15:16]<=0)&(ACTIONS[None,None,:,6]>0))
    return out,legal
