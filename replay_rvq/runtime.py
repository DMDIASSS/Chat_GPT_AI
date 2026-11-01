"""RLBot controls with bounded background search and per-tick chunk playback."""
from concurrent.futures import ThreadPoolExecutor
import math,time
import numpy as np
import torch
from replay_rlbot_core import PacketObserver,ReplayController
try:
    from rvq_packet import PacketState,StateObserver
    from rvq_search import Search
    from rvq_diagnostics import chunk_summary
except ModuleNotFoundError:
    from replay_rvq.packet import PacketState,StateObserver
    from replay_rvq.search import Search
    from replay_rvq.diagnostics import chunk_summary


class Controller:
    def __init__(self,kernel,field,*,device='cpu',mode='search',candidates=4,adaptive=True,
                 scripted_kickoff=True,asynchronous=True,max_plan_age_ticks=32):
        if mode not in ('policy','search') or type(candidates) is not int or not 1<=candidates<=64:
            raise ValueError('Invalid RVQ runtime mode/integer candidate budget')
        if type(max_plan_age_ticks) is not int or not 8<=max_plan_age_ticks<=64:
            raise ValueError('Plan age must be 8..64 ticks')
        self.kernel=kernel;self.device=device;self.observer=PacketObserver(field);self.mode=mode
        self.maximum_candidates=candidates;self.minimum_candidates=min(2,candidates)
        self.search=Search(kernel,device=device,candidates=min(4,candidates) if adaptive else candidates,
            observer=StateObserver()) if mode=='search' else None
        self.asynchronous=bool(asynchronous) and self.search is not None
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='rvq-search') if self.asynchronous else None
        self.pending=None;self.generation=0;self.last_submit_tick=None;self.max_plan_age_ticks=max_plan_age_ticks
        self.discarded_results=0;self.last_discarded_plan=None;self.pending_root_tick=None;self.pending_generation=None;self.closed=False
        self.packet_state=PacketState(self.observer);self.adaptive=adaptive;self.fast_decisions=0
        self.kickoff=ReplayController(None,np.zeros((1,32,8),np.float32),self.observer,scripted_kickoff=scripted_kickoff)
        self.last_tick=None;self.last_kickoff=None;self.decision_tick=None;self.previous=np.zeros(8,np.float32);self.sequence=None
        self.decisions=0;self.last_ms=None;self.max_ms=0.;self.over_budget=0;self.last_report={}
        self.source='neutral';self.neutral_reason=None;self.sequence_source='neutral';self.bootstrap_decisions=0
        self.contingency_frames=0;self.sequence_offset=None

    def reset(self):
        self.generation+=1
        if self.pending is not None and self.pending.cancel():self.pending=None
        # A running worker owns the simulator until it finishes. Its generation
        # is invalidated; never queue another job behind it or apply its result.
        self.last_submit_tick=None;self.last_tick=None;self.last_kickoff=None;self.decision_tick=None
        self.previous[:]=0;self.sequence=None;self.source='neutral';self.neutral_reason=None;self.sequence_offset=None
        self.kickoff.reset();self.packet_state.reset()

    def _timing(self,elapsed,*,adapt=True):
        self.last_ms=float(elapsed);self.max_ms=max(self.max_ms,self.last_ms)
        self.over_budget+=int(self.last_ms>1000*8/120)
        if self.search is not None and self.adaptive and adapt:
            if self.last_ms>1000*8/120:
                self.search.candidates=max(self.minimum_candidates,self.search.candidates//2);self.fast_decisions=0
            elif self.last_ms<1000*8/120*.7:self.fast_decisions+=1
            else:self.fast_decisions=0
            if self.fast_decisions>=8:
                self.search.candidates=min(self.maximum_candidates,self.search.candidates*2);self.fast_decisions=0

    def _accept(self,sequence,report,tick,source,elapsed):
        sequence=np.asarray(sequence,np.float32)
        if sequence.shape!=(32,8) or not np.isfinite(sequence).all() or np.abs(sequence).max()>1.001 or not np.isin(sequence[:,5:],[0,1]).all():
            raise ValueError('RVQ runtime returned invalid controls')
        self.sequence=sequence.copy();self.sequence_source=source;self.decision_tick=tick
        self.last_report=dict(report);self.last_report['chosen_chunk']=chunk_summary(sequence)
        self.decisions+=1;self._timing(elapsed,adapt=source=='search')

    def _policy(self,packet,index,tick):
        start=time.perf_counter();obs=self.observer.observe(packet,index,self.previous)
        tensors=tuple(torch.as_tensor(x[None],device=self.device) for x in obs)
        features=self.kernel.encode(tensors);sequence=self.kernel.greedy(features)[0][0].cpu().numpy()
        elapsed=1000*(time.perf_counter()-start)
        self._accept(sequence,{'mode':'policy','candidates':1,'bootstrap_or_expired_plan':self.asynchronous},tick,'policy',elapsed)
        if self.asynchronous:self.bootstrap_decisions+=1

    def _poll(self,tick):
        if self.pending is None or not self.pending.done():return
        if self.pending_generation==self.generation and self.sequence is not None and self.sequence_source=='search' and tick-self.decision_tick<8:
            return # An early result must not truncate the committed eight-tick prefix.
        pending=self.pending;self.pending=None
        root=self.pending_root_tick;generation=self.pending_generation
        if generation!=self.generation:
            self.discarded_results+=1;self.last_discarded_plan={'reason':'reset_generation','root_packet_tick':root};return
        sequence,report=pending.result();age=tick-root
        if age<0 or age>self.max_plan_age_ticks:
            self.discarded_results+=1;self._timing(report['latency_ms'])
            self.last_discarded_plan={'age_ticks':age,'reason':'stale','latency_ms':report['latency_ms']}
            return
        report={**report,'asynchronous':True,'root_packet_tick':root,'applied_at_tick':tick,'state_age_ticks':age,
            'execution':'First prefix starts when ready. Pending work continues the previous learned chunk, up to 32 ticks. No latency compensation is claimed.'}
        self._accept(sequence,report,tick,'search',report['latency_ms'])

    def _background(self,packet,index,tick):
        self._poll(tick)
        if self.sequence is None or tick-self.decision_tick>=32:self._policy(packet,index,tick)
        if self.pending is None and (self.last_submit_tick is None or tick-self.last_submit_tick>=8):
            # This only allocates/populates a detached GameState. Arena access
            # inside choose() remains exclusively owned by the single worker.
            state=self.packet_state.from_packet(packet,index,self.previous,self.search.engine)
            self.pending_root_tick=tick;self.pending_generation=self.generation;self.last_submit_tick=tick
            self.pending=self.executor.submit(self.search.choose,state,{index:self.previous.copy()},index)
        offset=min(31,max(0,tick-self.decision_tick));self.sequence_offset=offset
        self.contingency_frames+=int(offset>=8);self.source=self.sequence_source
        self.previous=self.sequence[offset].copy()
        return self.previous.copy()

    @torch.inference_mode()
    def output(self,packet,index):
        now=float(packet.game_info.seconds_elapsed)
        if not math.isfinite(now):raise ValueError('Invalid packet clock')
        tick=math.floor(now*120+.5);kickoff=bool(packet.game_info.is_kickoff_pause)
        if self.last_tick is not None and (tick<self.last_tick or tick-self.last_tick>120 or kickoff and self.last_kickoff is False):self.reset()
        self.last_tick=tick;self.last_kickoff=kickoff
        if not packet.game_info.is_round_active or packet.game_info.is_match_ended or packet.game_cars[index].is_demolished:
            self.reset();self.neutral_reason='match_ended' if packet.game_info.is_match_ended else 'demolished' if packet.game_cars[index].is_demolished else 'round_inactive'
            return self.previous.copy()
        self.neutral_reason=None
        assist=self.kickoff.kickoff_action(packet,index,tick)
        if assist is not None:self.previous=assist;self.source='scripted_kickoff';return assist.copy()
        if self.asynchronous:return self._background(packet,index,tick)
        if self.decision_tick is None or tick-self.decision_tick>=8:
            if self.search is None:self._policy(packet,index,tick)
            else:
                start=time.perf_counter();state=self.packet_state.from_packet(packet,index,self.previous,self.search.engine)
                sequence,report=self.search.choose(state,{index:self.previous},index)
                self._accept(sequence,report,tick,'search',1000*(time.perf_counter()-start))
        self.source=self.sequence_source;self.sequence_offset=min(7,max(0,tick-self.decision_tick))
        self.previous=self.sequence[self.sequence_offset].copy()
        return self.previous.copy()

    def close(self):
        if self.closed:return
        self.closed=True
        if self.executor is not None:self.executor.shutdown(wait=True,cancel_futures=True)
        if self.search is not None:self.search.close()
