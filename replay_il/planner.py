"""Inference-only RocketSim candidate search; never a training data source."""
from collections import deque
import copy,time
import numpy as np
import torch
from afk_team_research import TeamObserver
from slater_versatile_data import native_observation
from replay_il.model import ChunkPolicy

def load(folder,device='cpu',checkpoint='best.pt'):
    from pathlib import Path
    from slater_v041_core import sha256,read_json
    folder=Path(folder);doc=torch.load(folder/checkpoint,map_location=device,weights_only=True)
    if checkpoint=='best.pt' and read_json(folder/'selected.json',{}).get('sha256')!=sha256(folder/checkpoint):raise ValueError('Selected checkpoint changed')
    if read_json(folder/'tokenizer.json')['book_sha256']!=sha256(folder/'tokens.npy'):raise ValueError('Action vocabulary changed')
    model=ChunkPolicy(**doc['config']);model.load_state_dict(doc['model']);model.to(device).eval()
    return model,np.load(folder/'tokens.npy',allow_pickle=False)

class Planner:
    def __init__(self,model,book,*,candidates=64,horizon_ticks=120,uncertainty_penalty=1.,prior_weight=.03):
        from rlgym.rocket_league.sim import RocketSimEngine
        if not 1<=candidates<=64 or not 32<=horizon_ticks<=120:raise ValueError('Invalid planner budget')
        self.model=model.eval();self.book=np.asarray(book,np.float32);self.candidates=min(candidates,len(book))
        self.horizon=horizon_ticks;self.uncertainty=uncertainty_penalty;self.prior=prior_weight
        self.engine=RocketSimEngine(rlbot_delay=False);self.observer=TeamObserver()
        self.device=next(model.parameters()).device
    def observation(self,state,previous,ours):return native_observation(self.observer.observe(state,previous)[ours])
    def infer(self,history):
        return self.infer_batch([history])
    def infer_batch(self,histories):
        padded=[]
        for history in histories:
            views=list(history)[-self.model.history:]
            if not views:raise ValueError('Planner requires current observations')
            padded.append([views[0]]*(self.model.history-len(views))+views)
        x=tuple(torch.as_tensor(np.stack([np.stack([o[k] for o in views]) for views in padded]),device=self.device,dtype=torch.float32) for k in range(3))
        with torch.no_grad():return self.model(x)
    def choose(self,state,previous,ours,history=None):
        initial=copy.deepcopy(state);started=time.perf_counter()
        current=self.observation(initial,previous,ours)
        history=deque(list(history or [])[-self.model.history+1:]+[current],maxlen=self.model.history)
        logits,_=self.infer(history);logp=logits[0].log_softmax(-1)
        choices=logp.topk(self.candidates).indices.tolist();records=[]
        branches=[{'state':copy.deepcopy(initial),'history':deque(history,maxlen=self.model.history),
            'controls':{k:np.asarray(previous.get(k,np.zeros(8)),np.float32).copy() for k in initial.cars},
            'first':first,'token':first,'goal':None} for first in choices]
        chunk=len(self.book[0])
        for start in range(0,self.horizon,chunk):
            if start:
                next_logits,_=self.infer_batch([b['history'] for b in branches])
                for b,index in zip(branches,next_logits.argmax(-1).tolist()):b['token']=index
            for b in branches:
                if b['goal'] is not None:continue
                s=self.engine.set_state(b['state'],{})
                for offset in range(0,min(chunk,self.horizon-start),8):
                    count=min(8,self.horizon-start-offset,chunk-offset)
                    commands={k:np.repeat(v[None],count,axis=0) for k,v in b['controls'].items()}
                    commands[ours]=self.book[b['token'],offset:offset+count]
                    s=self.engine.step(commands,{})
                    b['controls'][ours]=commands[ours][-1].copy()
                    b['history'].append(self.observation(s,b['controls'],ours))
                    if s.goal_scored:
                        sign=-1 if s.cars[ours].is_orange else 1
                        b['goal']=1. if sign*s.ball.position[1]>0 else -1.;break
                b['state']=copy.deepcopy(s)
        _,predicted=self.infer_batch([b['history'] for b in branches])
        for b,values in zip(branches,predicted.cpu().numpy()):
            mean=float(values.mean()) if b['goal'] is None else b['goal']
            spread=float(values.std()) if b['goal'] is None else 0.
            score=mean-self.uncertainty*spread+self.prior*float(logp[b['first']])
            records.append({'token':b['first'],'score':score,'value':mean,'uncertainty':spread})
        best=max(records,key=lambda r:r['score']);elapsed=time.perf_counter()-started
        return self.book[best['token']].copy(),{'selected':best,'candidates':len(records),'horizon_seconds':self.horizon/120,
            'latency_ms':elapsed*1000,'maximum_decisions_per_second':1/max(elapsed,1e-9),'execute_first_ticks':8,
            'opponents':'last observed controls held; future human inputs are unknown','records':records}
    def close(self):self.engine.close()

class KickoffBook:
    def __init__(self,entries):self.entries=entries;self.active=None;self.tick=0
    def start(self,state,ours,*,is_kickoff):
        self.active=None;self.tick=0
        if not is_kickoff or np.linalg.norm(state.ball.position[:2])>1 or np.linalg.norm(state.ball.linear_velocity)>1:return False
        car=state.cars[ours];pos=np.asarray(car.physics.position)*([-1,-1,1] if car.is_orange else [1,1,1])
        # Let the closest teammate take kickoff; a book is not a reason to double commit.
        teammates=[np.linalg.norm(c.physics.position[:2]) for c in state.cars.values() if c.team_num==car.team_num]
        if np.linalg.norm(car.physics.position[:2])>min(teammates)+20:return False
        matches=[e for e in self.entries if e['players']==len(state.cars) and np.linalg.norm(pos-np.asarray(e['spawn']))<100]
        if not matches:return False
        self.active=min(matches,key=lambda e:e['touch_ticks']);return True
    def frame(self,state):
        if self.active is None:return None
        if np.linalg.norm(state.ball.position[:2])>5 or self.tick>=len(self.active['controls']):self.active=None;return None
        action=np.asarray(self.active['controls'][self.tick],np.float32);self.tick+=1;return action
