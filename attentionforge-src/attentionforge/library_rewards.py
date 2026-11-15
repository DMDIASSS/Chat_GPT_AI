"""Batched adaptations of RLGym 2.0.1 / rlgym-tools 2.6.5 rewards.

Apache-2.0 upstream attribution and exact parameters: LIBRARY_REWARDS.md.
Only NumPy vectorization and undefined-normalization guards differ. No reward
clipping, extra shaping, opponent subtraction or time scaling is added.
"""
import copy
import numpy as np

NAMES=('GoalReward','AdvancedTouchReward','VelocityPlayerToBallReward','GoalViewReward','AerialDistanceReward')
PRESET={'profile':'rlgym_tools_v1','goal':10.,'touch':.05,'touch_acceleration':.5,'approach':.2,'goal_view':1.,'aerial_distance':2.,'control_progress':0.}


def goal_probability(positions):
    positions=np.asarray(positions,dtype=np.float64)
    def view(y):
        corners=np.array([[-801.505,y,91.25],[801.505,y,91.25],[-801.505,y,551.525],[801.505,y,551.525]])
        vectors=corners[None]-positions[:,None]
        lengths=np.linalg.norm(vectors,axis=-1,keepdims=True)
        vectors=np.divide(vectors,lengths,out=np.zeros_like(vectors),where=lengths>1e-12)
        def triangle(i,j,k):
            a,b,c=vectors[:,i],vectors[:,j],vectors[:,k]
            num=np.abs(np.sum(np.cross(a,b)*c,axis=-1))
            den=1+np.sum(a*b+b*c+c*a,axis=-1)
            return 2*np.arctan2(num,den)
        return (triangle(0,1,2)+triangle(1,3,2))/(4*np.pi)
    blue,orange=view(-5215.5),view(5215.5)
    return np.divide(orange,blue+orange,out=np.full(len(positions),.5),where=blue+orange>1e-15)


class LibraryRewards:
    def __init__(self,world,weights,gamma):
        if world.shape[1:]!=(3,32):raise ValueError('rlgym_tools_v1 currently supports 1v1 only: touch telemetry is per team')
        self.weights=copy.deepcopy(weights);self.gamma=float(gamma)
        if not 0<self.gamma<=1:raise ValueError('Invalid discount')
        for key in PRESET:
            if key!='profile' and (not np.isfinite(self.weights[key]) or self.weights[key]<0):raise ValueError('Invalid library reward weight: '+key)
        if self.weights['control_progress']!=0:raise ValueError('Custom control rewards are disabled in rlgym_tools_v1')
        self.prev=np.array(world,dtype=np.float64,copy=True)
        self.prob=goal_probability(self.prev[:,0,:3]);self.owner=np.full(len(world),-1,np.int8);self.distance=np.zeros((len(world),2))

    def reset_rows(self,world,rows=None):
        rows=np.arange(len(world)) if rows is None else np.asarray(rows)
        self.prev[rows]=world[rows];self.prob[rows]=goal_probability(np.asarray(world)[rows,0,:3]);self.owner[rows]=-1;self.distance[rows]=0

    def step(self,raw):
        # final_world is always the physical post-action state, before auto-reset.
        world=np.asarray(raw['final_world'],dtype=np.float64);info=raw['info'];hits=info[:,1:3]>0;goal=info[:,0]
        n=len(world);parts=np.zeros((n,2,5),np.float64);w=self.weights
        parts[:,:,0]=goal[:,None]*np.array([1.,-1.])*w['goal']
        acceleration=np.linalg.norm(world[:,0,3:6]-self.prev[:,0,3:6],axis=-1)/6000
        parts[:,:,1]=hits*(w['touch']+w['touch_acceleration']*acceleration[:,None])
        delta=world[:,0:1,:3]-world[:,1:,:3];length=np.linalg.norm(delta,axis=-1)
        toward=np.divide(np.sum(delta*world[:,1:,3:6],axis=-1),length,out=np.zeros((n,2)),where=length>1e-12)/2300
        parts[:,:,2]=np.maximum(0,toward)*(info[:,7,None]/120)*w['approach']
        prob=goal_probability(world[:,0,:3]);prob=np.where(goal>0,1,np.where(goal<0,0,prob))
        shaping=self.gamma*(2*prob-1)-(2*self.prob-1)
        parts[:,:,3]=shaping[:,None]*np.array([1.,-1.])*w['goal_view'];self.prob=prob
        ball_distance=np.linalg.norm(world[:,0,:3]-self.prev[:,0,:3],axis=-1)
        # Preserve upstream [blue, orange] iteration order, including simultaneous hits.
        for a in (0,1):
            own=self.owner==a;landed=own&(world[:,a+1,2]<256)
            self.distance[landed,a]=0;self.owner[landed]=-1
            own=self.owner==a
            car_distance=np.linalg.norm(world[:,a+1,:3]-self.prev[:,a+1,:3],axis=-1)
            self.distance[own,a]+=car_distance[own]+ball_distance[own]
            height=np.maximum(0,(world[:,a+1,2]+world[:,0,2])/2-256)
            parts[:,a,4]=np.where(hits[:,a],np.where(own,self.distance[:,a],height)/5120*w['aerial_distance'],0)
            self.owner[hits[:,a]]=a;self.distance[hits[:,a],a]=0
        rewards=parts.sum(axis=-1).astype(np.float32)
        if not np.isfinite(rewards).all():raise FloatingPointError('Non-finite library reward; optimizer not run')
        self.prev[:]=world
        done=raw['terminated']|raw['truncated']
        if done.any():self.reset_rows(raw['world'],np.flatnonzero(done))
        return rewards,parts.astype(np.float32)


class LibraryBatch:
    """Wrap native physics with one batched reward calculation, no GameState loops."""
    def __init__(self,native,weights,gamma):
        self.native=native;self.calculator=LibraryRewards(native.observe()['world'],weights,gamma)
    def __getattr__(self,name):return getattr(self.native,name)
    def step(self,actions):
        raw=self.native.step(actions);raw['rewards'],raw['library_info']=self.calculator.step(raw)
        # No legacy custom reward may leak into rewards OR reward telemetry.
        raw['reward_info'].fill(0);raw['skill_info'].fill(0);raw['attack_info'].fill(0)
        raw['info'][:,3]=raw['library_info'][:,0,0];raw['info'][:,4]=raw['library_info'][:,0,2];raw['info'][:,5]=raw['library_info'][:,0,1];raw['info'][:,6]=0
        return raw
    def scenario(self,kind):
        self.native.scenario(kind);self.calculator.reset_rows(self.native.observe()['world'])
    def set_ground(self,i,world):
        self.native.set_ground(i,world);self.calculator.reset_rows(self.native.observe()['world'],[i])
    def test_state(self,i,world):
        self.native.test_state(i,world);self.calculator.reset_rows(self.native.observe()['world'],[i])
    def skill_stage(self,*_):raise RuntimeError('Custom reward stages are disabled for rlgym_tools_v1')
    def drill_fraction(self,value):
        if value!=0:raise RuntimeError('Skills curriculum is disabled for rlgym_tools_v1')
        self.native.drill_fraction(0)
