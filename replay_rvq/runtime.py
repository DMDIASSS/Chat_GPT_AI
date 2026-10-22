"""RLBot controller for a frozen state-only RVQ policy, optionally with search."""
import math,time
import numpy as np
import torch
from replay_rlbot_core import PacketObserver,ReplayController
try:
    from rvq_packet import PacketState,StateObserver
    from rvq_search import Search
except ModuleNotFoundError:
    from replay_rvq.packet import PacketState,StateObserver
    from replay_rvq.search import Search


class Controller:
    def __init__(self,kernel,field,*,device='cpu',mode='search',candidates=16,adaptive=True,scripted_kickoff=True):
        if mode not in ('policy','search') or type(candidates) is not int or not 1<=candidates<=64:raise ValueError('Invalid RVQ runtime mode/integer candidate budget')
        self.kernel=kernel;self.device=device;self.observer=PacketObserver(field);self.mode=mode;self.maximum_candidates=candidates
        self.search=Search(kernel,device=device,candidates=min(4,candidates) if adaptive else candidates,observer=StateObserver()) if mode=='search' else None
        self.packet_state=PacketState(self.observer);self.adaptive=adaptive;self.fast_decisions=0
        self.kickoff=ReplayController(None,np.zeros((1,32,8),np.float32),self.observer,scripted_kickoff=scripted_kickoff)
        self.last_tick=None;self.last_kickoff=None;self.decision_tick=None;self.previous=np.zeros(8,np.float32);self.sequence=None
        self.decisions=0;self.last_ms=None;self.max_ms=0.;self.over_budget=0;self.last_report={};self.source='neutral'

    def reset(self):
        self.last_tick=None;self.last_kickoff=None;self.decision_tick=None;self.previous[:]=0;self.sequence=None;self.source='neutral'
        self.kickoff.reset();self.packet_state.reset()

    @torch.inference_mode()
    def output(self,packet,index):
        now=float(packet.game_info.seconds_elapsed)
        if not math.isfinite(now):raise ValueError('Invalid packet clock')
        tick=math.floor(now*120+.5);kickoff=bool(packet.game_info.is_kickoff_pause)
        if self.last_tick is not None and (tick<self.last_tick or tick-self.last_tick>120 or kickoff and self.last_kickoff is False):self.reset()
        self.last_tick=tick;self.last_kickoff=kickoff
        if not packet.game_info.is_round_active or packet.game_info.is_match_ended or packet.game_cars[index].is_demolished:
            self.reset();return self.previous.copy()
        assist=self.kickoff.kickoff_action(packet,index,tick)
        if assist is not None:self.previous=assist;self.source='scripted_kickoff';return assist.copy()
        if self.decision_tick is None or tick-self.decision_tick>=8:
            start=time.perf_counter()
            if self.search is None:
                obs=self.observer.observe(packet,index,self.previous)
                tensors=tuple(torch.as_tensor(x[None],device=self.device) for x in obs)
                features=self.kernel.encode(tensors);self.sequence=self.kernel.greedy(features)[0][0].cpu().numpy()
                self.last_report={'mode':'policy','candidates':1}
            else:
                state=self.packet_state.from_packet(packet,index,self.previous,self.search.engine)
                self.sequence,self.last_report=self.search.choose(state,{index:self.previous},index)
            if self.sequence.shape!=(32,8) or not np.isfinite(self.sequence).all() or np.abs(self.sequence).max()>1.001 or not np.isin(self.sequence[:,5:],[0,1]).all():
                raise ValueError('RVQ runtime returned invalid controls')
            self.last_ms=1000*(time.perf_counter()-start);self.max_ms=max(self.max_ms,self.last_ms)
            self.decisions+=1;self.over_budget+=int(self.last_ms>1000*8/120);self.decision_tick=tick
            if self.search is not None and self.adaptive:
                if self.last_ms>1000*8/120:self.search.candidates=max(1,self.search.candidates//2);self.fast_decisions=0
                elif self.last_ms<35:self.fast_decisions+=1
                else:self.fast_decisions=0
                if self.fast_decisions>=8:
                    self.search.candidates=min(self.maximum_candidates,self.search.candidates*2);self.fast_decisions=0
        self.source=self.mode;self.previous=self.sequence[min(7,max(0,tick-self.decision_tick))].copy()
        return self.previous.copy()

    def close(self):
        if self.search is not None:self.search.close()
