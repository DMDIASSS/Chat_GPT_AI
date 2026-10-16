"""Separate inference runtime; preserves replay_il training source fingerprints."""
from collections import deque
from pathlib import Path
import argparse,copy,platform,time
import numpy as np
import torch
from afk_team_research import encode_multi
from replay_il.planner import Planner,load
from slater_v041_core import atomic_json,sha256

ROOT=Path(__file__).resolve().parent

def resolve_device(requested):
    if requested not in ('auto','cpu','cuda'):raise ValueError('Device must be auto, cpu or cuda')
    if requested=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA was requested but is unavailable in this Python environment')
    return torch.device('cuda' if requested=='auto' and torch.cuda.is_available() else 'cpu' if requested=='auto' else requested)

def synchronize(device):
    if device.type=='cuda':torch.cuda.synchronize(device)

class RuntimePlanner(Planner):
    """Same search decisions, with batched observations and cached spatial features."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self._features={};self._feature_tensor=None;self.encoded_observations=0
        self._causal=torch.ones(self.model.history,self.model.history,dtype=torch.bool,device=self.device).triu(1)
    def observations_batch(self,states,previous,ours):
        if len(states)!=len(previous):raise ValueError('State/control batch mismatch')
        if not states:return []
        encoded=[];roster=None
        for state in states:
            row,ids=encode_multi(state)
            if roster is None:roster=ids
            if ids!=roster:raise ValueError('Planner branch roster changed')
            encoded.append(row)
        index=roster.index(ours)
        obs=self.observer.builder.batched_build_obs(np.stack(encoded))
        self.observer.builder.add_actions(obs,np.stack([p.get(ours,np.zeros(8)) for p in previous]),index)
        q,kv,mask=obs[index]
        q=q.astype(np.float32);kv=kv.astype(np.float32)
        mask=np.where(mask>0,-10000.,mask).astype(np.float32)
        return [(q[i],kv[i],mask[i]) for i in range(len(states))]
    @torch.inference_mode()
    def infer_batch(self,histories):
        padded=[];new={}
        for history in histories:
            views=list(history)[-self.model.history:]
            if not views:raise ValueError('Planner requires current observations')
            views=[views[0]]*(self.model.history-len(views))+views;padded.append(views)
            for view in views:
                if id(view) not in self._features:new[id(view)]=view
        if new:
            views=list(new.values())
            x=tuple(torch.as_tensor(np.stack([v[k] for v in views]),device=self.device,dtype=torch.float32) for k in range(3))
            encoded=self.model.encoder(x)
            offset=0 if self._feature_tensor is None else len(self._feature_tensor)
            self._feature_tensor=encoded if self._feature_tensor is None else torch.cat((self._feature_tensor,encoded),dim=0)
            for index,view in enumerate(views):
                # Keep source tuples alive; gather all histories in one device operation.
                self._features[id(view)]=(view,offset+index)
            self.encoded_observations+=len(views)
        indices=torch.as_tensor([[self._features[id(v)][1] for v in views] for views in padded],device=self.device)
        x=self._feature_tensor[indices]
        x=self.model.project(x)+self.model.position[:,:x.shape[1]]
        causal=self._causal[:x.shape[1],:x.shape[1]]
        x=self.model.norm(self.model.temporal(x,mask=causal)[:,-1])
        return self.model.policy(x),torch.cat([head(x).tanh() for head in self.model.values],-1)
    def begin(self):
        self._features.clear();self._feature_tensor=None;self.encoded_observations=0
    @torch.inference_mode()
    def choose_policy(self,state,previous,ours,history=None):
        synchronize(self.device);started=time.perf_counter();self.begin()
        current=self.observation(state,previous,ours)
        context=list(history or [])[-(self.model.history-1):]+[current]
        logits,values=self.infer_batch([context]);token=int(logits[0].argmax())
        synchronize(self.device);elapsed=time.perf_counter()-started
        return self.book[token].copy(),{'mode':'policy','selected':{'token':token,'value':float(values[0].mean()),'uncertainty':float(values[0].std(unbiased=False))},
            'candidates':1,'horizon_seconds':0.,'latency_ms':elapsed*1000,'execute_first_ticks':8,'device':str(self.device)}
    @torch.inference_mode()
    def choose(self,state,previous,ours,history=None):
        synchronize(self.device);started=time.perf_counter();self.begin();initial=copy.deepcopy(state)
        current=self.observation(initial,previous,ours)
        history=deque(list(history or [])[-(self.model.history-1):]+[current],maxlen=self.model.history)
        logits,_=self.infer_batch([history]);logp=logits[0].log_softmax(-1).cpu()
        choices=logp.topk(self.candidates).indices.tolist()
        branches=[{'state':copy.deepcopy(initial),'history':deque(history,maxlen=self.model.history),
            'controls':{k:np.asarray(previous.get(k,np.zeros(8)),np.float32).copy() for k in initial.cars},
            'first':first,'token':first,'goal':None} for first in choices]
        chunk=len(self.book[0])
        for start in range(0,self.horizon,chunk):
            if start:
                next_logits,_=self.infer_batch([b['history'] for b in branches])
                for b,index in zip(branches,next_logits.argmax(-1).tolist()):b['token']=index
            snapshots=[]
            for b in branches:
                if b['goal'] is not None:continue
                s=self.engine.set_state(b['state'],{})
                for offset in range(0,min(chunk,self.horizon-start),8):
                    count=min(8,self.horizon-start-offset,chunk-offset)
                    commands={k:np.repeat(v[None],count,axis=0) for k,v in b['controls'].items()}
                    commands[ours]=self.book[b['token'],offset:offset+count]
                    s=self.engine.step(commands,{})
                    b['controls'][ours]=commands[ours][-1].copy()
                    snapshots.append((b,s,{ours:b['controls'][ours].copy()}))
                    if s.goal_scored:
                        sign=-1 if s.cars[ours].is_orange else 1
                        b['goal']=1. if sign*s.ball.position[1]>0 else -1.;break
                b['state']=copy.deepcopy(s)
            views=self.observations_batch([s for _,s,_ in snapshots],[p for _,_,p in snapshots],ours)
            for (branch,_,_),view in zip(snapshots,views):branch['history'].append(view)
        _,predicted=self.infer_batch([b['history'] for b in branches]);records=[]
        for b,values in zip(branches,predicted.cpu().numpy()):
            mean=float(values.mean()) if b['goal'] is None else b['goal']
            spread=float(values.std()) if b['goal'] is None else 0.
            score=mean-self.uncertainty*spread+self.prior*float(logp[b['first']])
            records.append({'token':b['first'],'score':score,'value':mean,'uncertainty':spread})
        best=max(records,key=lambda r:r['score']);synchronize(self.device);elapsed=time.perf_counter()-started
        return self.book[best['token']].copy(),{'mode':'search','selected':best,'candidates':len(records),'horizon_seconds':self.horizon/120,
            'latency_ms':elapsed*1000,'maximum_decisions_per_second':1/max(elapsed,1e-9),'execute_first_ticks':8,
            'device':str(self.device),'encoded_observations':self.encoded_observations,
            'opponents':'last observed controls held; future human inputs are unknown','records':records}

def benchmark(folder,*,device='auto',threads=2,repeats=3,warmups=1,candidate_counts=(4,16,64)):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    if not 1<=threads<=64 or not 1<=repeats<=20 or not 0<=warmups<=5:raise ValueError('Invalid benchmark budget')
    if not candidate_counts or any(not 1<=c<=64 for c in candidate_counts):raise ValueError('Candidates must be 1..64')
    target=resolve_device(device);torch.set_num_threads(threads)
    print('RUNTIME_DEVICE:',target,'| CPU threads:',threads,'| CUDA available:',torch.cuda.is_available(),flush=True)
    folder=Path(folder).resolve()
    # Load checkpoint/Adam tensors on CPU, then move only the inference network.
    model,book=load(folder,device='cpu');model.to(target).eval()
    engine=RocketSimEngine(rlbot_delay=False)
    state=engine.create_base_state();FixedTeamSizeMutator(1,1).apply(state,{});KickoffMutator().apply(state,{})
    state=engine.set_state(state,{});previous={k:np.zeros(8,np.float32) for k in state.cars};ours=next(iter(state.cars))
    results=[];deadline=8/120*1000
    try:
        for count in (None,*candidate_counts):
            planner=RuntimePlanner(model,book,candidates=count or 1)
            choose=planner.choose_policy if count is None else planner.choose
            try:
                for _ in range(warmups):choose(state,previous,ours)
                samples=[];last=None
                for _ in range(repeats):
                    _,last=choose(state,previous,ours);samples.append(last['latency_ms'])
                report={k:v for k,v in last.items() if k!='records'}
                report.update(latency_samples_ms=samples,latency_median_ms=float(np.median(samples)),
                    latency_p95_ms=float(np.quantile(samples,.95)),deadline_ms=deadline,
                    meets_deadline_p95=bool(np.quantile(samples,.95)<=deadline),warmups=warmups,repeats=repeats)
                results.append(report)
                print('RUNTIME',report['mode'],'candidates',report['candidates'],'device',target,
                    'median_ms',round(report['latency_median_ms'],2),'p95_ms',round(report['latency_p95_ms'],2),
                    'meets_67ms',report['meets_deadline_p95'],flush=True)
            finally:planner.close()
    finally:engine.close()
    return {'schema':'replay-il-runtime-v1','checkpoint_sha256':sha256(folder/'best.pt'),'book_sha256':sha256(folder/'tokens.npy'),
        'requested_device':device,'device':str(target),'cuda_available':torch.cuda.is_available(),
        'device_name':torch.cuda.get_device_name(target) if target.type=='cuda' else platform.processor() or 'CPU',
        'torch':torch.__version__,'threads':threads,'format':'1v1','results':results,
        'note':'Warmed repeated kickoff-state latency only. No playing-strength test; GPU does not move RocketSim off CPU.'}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',default='replay_scratch01')
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--threads',type=int,default=2);parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--warmups',type=int,default=1)
    parser.add_argument('--candidates',type=int,nargs='+',default=[4,16,64])
    args=parser.parse_args(argv)
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',args.run):parser.error('Invalid run name')
    folder=ROOT/'data/isolated/replay_imitation/runs'/args.run
    report=benchmark(folder,device=args.device,threads=args.threads,repeats=args.repeats,warmups=args.warmups,candidate_counts=args.candidates)
    output=folder/'runtime_benchmark.json';atomic_json(output,report)
    print('REPORT:',output,flush=True)
    print('This benchmarks inference only. It does not start training or connect to a game.',flush=True)

if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError,RuntimeError) as error:
        print('STOPPED:',str(error),flush=True);raise SystemExit(1)
