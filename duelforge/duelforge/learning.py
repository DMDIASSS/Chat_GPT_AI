"""Versioned early-learning hypotheses; never change a resumed run silently."""
import numpy as np
from .observation import ACTIONS

def entropy_coefficient(cfg,transitions):
    p=cfg['ppo'];schedule=p.get('entropy_schedule')
    if not schedule:return float(p['entropy'])
    frac=np.clip(transitions/max(1,schedule['decay_transitions']),0.,1.)
    return float(schedule['start']+(schedule['end']-schedule['start'])*frac)

def bootstrap_parts(cfg,before,after,transitions):
    """Temporary speed-to-ball and bounded *new contact* event incentives.

    No reward for facing forward, jumping or flipping. The direction-to-ball
    term matches the usual positive velocity-to-ball idea, with explicit 3D
    geometry. It fades, because approaching forever is not match success.
    """
    c=cfg.get('bootstrap',{});n=len(before['world']);out=np.zeros((n,2,2),np.float32)
    if not c.get('enabled',False):return out
    scale=max(0.,1.-transitions/max(1,c['fade_transitions']))
    if scale==0:return out
    world=after['final_world'];ball=world[:,0,:3];cars=world[:,1:];delta=ball[:,None]-cars[:,:,:3];distance=np.linalg.norm(delta,axis=-1)
    direction=delta/np.maximum(distance[:,:,None],1.)
    toward=np.maximum(0.,(cars[:,:,3:6]*direction).sum(-1)/2300.)
    dt=after['info'][:,3:4]/8.
    valid=cars[:,:,20]<.5
    out[:,:,0]=np.minimum(1.,toward)*dt*valid*c['approach_weight']*scale
    out[:,:,1]=(after['info'][:,1:3]>0)*valid*c['contact_weight']*scale
    return out

def evaluation_summary(cfg,world,actions):
    """Descriptive controls, not extra reward objectives."""
    controls=ACTIONS[actions];cars=world[:,1:]
    jump=controls[:,:,5]>.5
    return np.asarray([(controls[:,:,0]<-.5).mean(),jump.mean(),((controls[:,:,0]>.5)&(controls[:,:,7]<.5)&~jump).mean()],np.float64)
