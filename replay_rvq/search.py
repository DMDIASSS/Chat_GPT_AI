"""Reference all-car policy rollouts: 64 lines, four chunks, value-only ranking."""
import copy,time
import numpy as np
import torch


class Search:
    def __init__(self,kernel,*,device='cpu',candidates=16,chunks=4,observer=None):
        from rlgym.rocket_league.sim import RocketSimEngine
        if type(candidates) is not int or not 1<=candidates<=64 or chunks!=4:raise ValueError('Use 1..64 integer candidates and four 32-tick chunks')
        if observer is None:
            from afk_team_research import TeamObserver
            observer=TeamObserver()
        self.kernel=kernel.eval();self.device=torch.device(device);self.candidates=candidates;self.chunks=chunks
        self.engine=RocketSimEngine(rlbot_delay=False);self.observer=observer

    def features(self,states,previous):
        views=[];ids=[]
        for state,actions in zip(states,previous):
            obs=self.observer.observe(state,actions);order=list(obs);ids.append(order)
            for aid in order:
                q,kv,mask=obs[aid];views.append((q,kv,np.where(mask>0,-10000.,mask)))
        tensors=tuple(torch.as_tensor(np.stack([v[i] for v in views]),device=self.device,dtype=torch.float32) for i in range(3))
        return self.kernel.encode(tensors),ids

    @torch.inference_mode()
    def choose(self,state,previous,ours):
        started=time.perf_counter();initial=copy.deepcopy(state)
        if ours not in initial.cars:raise ValueError('Controlled car missing from forecast state')
        features,orders=self.features([initial],[previous]);ids=orders[0];index=ids.index(ours)
        proposals,codes,logp=self.kernel.propose(features[index:index+1])
        proposals=proposals[0,:self.candidates].cpu().numpy();codes=codes[0,:self.candidates].cpu().numpy()
        logp=logp[0,:self.candidates].cpu().numpy()
        initial_actions=self.kernel.greedy(features)[0].cpu().numpy()
        branches=[{'state':copy.deepcopy(initial),'previous':{aid:np.asarray(previous.get(aid,np.zeros(8)),np.float32).copy() for aid in ids},
            'first':sequence.copy(),'codes':code.tolist(),'logp':float(prior),'goal':None} for sequence,code,prior in zip(proposals,codes,logp)]
        car_predictions=len(ids);simulation_ms=0.;network_ms=0.
        for chunk in range(self.chunks):
            alive=[b for b in branches if b['goal'] is None]
            if not alive:break
            if chunk:
                phase=time.perf_counter();contexts,orders=self.features([b['state'] for b in alive],[b['previous'] for b in alive])
                actions=self.kernel.greedy(contexts)[0].cpu().numpy();network_ms+=1000*(time.perf_counter()-phase)
                car_predictions+=len(actions)
            else:orders=[ids for _ in alive]
            position=0
            for branch,order in zip(alive,orders):
                commands={aid:(initial_actions[j].copy() if chunk==0 else actions[position+j].copy()) for j,aid in enumerate(order)}
                position+=len(order)
                if chunk==0:commands[ours]=branch['first']
                phase=time.perf_counter();current=self.engine.set_state(branch['state'],{})
                # Preserve button edges and detect terminal goals in short steps.
                for offset in range(0,32,8):
                    current=self.engine.step({aid:values[offset:offset+8] for aid,values in commands.items()},{})
                    branch['previous']={aid:values[offset+7].copy() for aid,values in commands.items()}
                    if current.goal_scored:
                        sign=-1 if current.cars[ours].is_orange else 1
                        branch['goal']=1. if sign*current.ball.position[1]>0 else -1.;break
                branch['state']=copy.deepcopy(current);simulation_ms+=1000*(time.perf_counter()-phase)
        alive=[b for b in branches if b['goal'] is None]
        if alive:
            phase=time.perf_counter();contexts,orders=self.features([b['state'] for b in alive],[b['previous'] for b in alive])
            own=[];start=0
            for order in orders:own.append(start+order.index(ours));start+=len(order)
            values=self.kernel.value(contexts[own]).mean(-1).cpu().numpy()
            network_ms+=1000*(time.perf_counter()-phase)
            for branch,value in zip(alive,values):branch['value']=float(value)
        records=[]
        for index,branch in enumerate(branches):
            value=branch['goal'] if branch['goal'] is not None else branch['value']
            records.append({'candidate':index,'codes':branch['codes'],'value':value,'proposal_logp':branch['logp']})
        if not all(np.isfinite(r['value']) for r in records):raise ValueError('Nonfinite forecast value')
        best=max(records,key=lambda row:row['value']);elapsed=1000*(time.perf_counter()-started)
        return branches[best['candidate']]['first'].copy(),{'selected':best,'records':records,'candidates':len(branches),
            'horizon_ticks':128,'horizon_seconds':128/120,'execute_first_ticks':8,'latency_ms':elapsed,
            'simulation_ms':simulation_ms,'continuation_network_ms':network_ms,'policy_car_predictions':car_predictions,
            'opponents':'all other cars use the frozen replay-trained argmax policy at every chunk',
            'ranking':'mean learned value only; terminal goals use known signed outcome; no handcrafted movement reward',
            'competitive_strength_verified':False}

    def close(self):self.engine.close()
