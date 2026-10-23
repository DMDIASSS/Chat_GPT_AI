"""Self-contained RLBot v4 agent; imports inference/runtime only, never training."""
from pathlib import Path
import hashlib,json,time
import numpy as np
import torch
from rlbot.agents.base_agent import BaseAgent,SimpleControllerState
from rvq_runtime import Controller
from rvq_diagnostics import MotionAudit

HERE=Path(__file__).resolve().parent


class ReplayRVQBot(BaseAgent):
    def initialize_agent(self):
        torch.set_num_threads(2);metadata=json.loads((HERE/'EXPORT_INFO.json').read_text(encoding='utf8'))
        for name,digest in metadata['runtime_sha256'].items():
            if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:raise ValueError('RVQ export changed: '+name)
        settings=json.loads((HERE/'runtime.json').read_text(encoding='utf8'));device=settings.get('device','auto')
        if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
        if device not in ('cpu','cuda') or device=='cuda' and not torch.cuda.is_available():raise ValueError('Requested runtime device unavailable')
        kernel=torch.jit.load(str(HERE/'policy.pt'),map_location=device).eval()
        self.controller=Controller(kernel,self.get_field_info(),device=device,mode=settings.get('mode','search'),
            candidates=settings.get('candidates',4),adaptive=bool(settings.get('adaptive',True)),
            scripted_kickoff=bool(settings.get('scripted_kickoff',True)),
            asynchronous=bool(settings.get('asynchronous',True)),max_plan_age_ticks=settings.get('max_plan_age_ticks',32))
        self.last_log=None;self.last_log_wall=None;self.error=False;self.last_error=None;self.motion_audit=MotionAudit();self.max_control_update_ms=0.
        self.counts={source:{'samples':0,'jump':0,'boost':0,'handbrake':0} for source in ('neutral','policy','search','scripted_kickoff')}
        print('RVQ_READY:',metadata['name'],'| device',device,'| mode',self.controller.mode,'| no training',flush=True)

    def get_output(self,packet):
        control_started=time.perf_counter()
        try:action=self.controller.output(packet,self.index);self.error=False
        except (ValueError,RuntimeError,IndexError,KeyError) as error:
            self.controller.reset();action=np.zeros(8,np.float32)
            if not self.error:print('RVQ_PAUSED:',str(error),flush=True)
            self.error=True;self.last_error={'type':type(error).__name__,'message':str(error),'game_seconds':float(packet.game_info.seconds_elapsed)}
        control_update_ms=1000*(time.perf_counter()-control_started);self.max_control_update_ms=max(self.max_control_update_ms,control_update_ms)
        source=self.controller.source;row=self.counts[source];row['samples']+=1
        for name,axis in (('jump',5),('boost',6),('handbrake',7)):row[name]+=int(bool(action[axis]))
        now=float(packet.game_info.seconds_elapsed)
        try:
            motion=self.motion_audit.observe(packet,self.index,action,decisions=self.controller.decisions,
                source=source,error=self.last_error if self.error else None,neutral_reason=self.controller.neutral_reason)
        except (ValueError,AttributeError,IndexError,OverflowError) as error:
            motion={'status':'audit_input_error','message':str(error)}
        wall=time.monotonic()
        if self.last_log is None or now<self.last_log or now-self.last_log>=5 or wall-self.last_log_wall>=5:
            self.last_log=now;self.last_log_wall=wall
            report={'schema':'replay-rvq-live-v1','car_index':int(self.index),'source':source,'counts':self.counts,
                'decisions':self.controller.decisions,'last_ms':self.controller.last_ms,'max_ms':self.controller.max_ms,
                'over_budget_decisions':self.controller.over_budget,'search':self.controller.last_report,
                'motion':motion,'runtime_error_active':self.error,'last_runtime_error':self.last_error,
                'asynchronous':self.controller.asynchronous,
                'pending_search':self.controller.pending is not None and not self.controller.pending.done(),
                'ready_plan_waiting':self.controller.pending is not None and self.controller.pending.done(),
                'control_update_ms':control_update_ms,'max_control_update_ms':self.max_control_update_ms,
                'discarded_search_plans':self.controller.discarded_results,'policy_fallback_decisions':self.controller.bootstrap_decisions,
                'last_discarded_plan':self.controller.last_discarded_plan,
                'contingency_frames_after_tick8':self.controller.contingency_frames,'sequence_offset':self.controller.sequence_offset,
                'next_candidate_budget':self.controller.search.candidates if self.controller.search is not None else None,
                'scope':'Issued controls and local latency. Control timing excludes logging. Search may use aged states; timers are estimates. No training or competitive improvement claim.'}
            print('RVQ_OUTPUT:',source,'latency',self.controller.last_ms,'motion',motion['status'],'counts',self.counts,flush=True)
            try:
                path=HERE/('RVQ_DIAGNOSTICS_'+str(self.index)+'.partial');path.write_text(json.dumps(report,indent=2),encoding='utf8')
                path.replace(HERE/'RVQ_DIAGNOSTICS.json')
                own=HERE/('RVQ_DIAGNOSTICS_'+str(self.index)+'.json')
                temporary=own.with_suffix('.partial');temporary.write_text(json.dumps(report,indent=2),encoding='utf8');temporary.replace(own)
            except OSError:pass
        return SimpleControllerState(throttle=float(action[0]),steer=float(action[1]),pitch=float(action[2]),
            yaw=float(action[3]),roll=float(action[4]),jump=bool(action[5]),boost=bool(action[6]),handbrake=bool(action[7]))

    def retire(self):
        if hasattr(self,'controller'):self.controller.close()
