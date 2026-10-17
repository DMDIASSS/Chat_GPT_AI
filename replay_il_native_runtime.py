"""Inference-only native RocketSim forecasts; preserves training source hashes."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import time
import numpy as np
import torch
import RocketSim as rs
from replay_il_runtime import RuntimePlanner,synchronize


# Re-export the existing helpers for callers/tests. The worker imports their
# lightweight module directly, without loading this Torch-dependent runtime.
from replay_il_forecast import native_encoded,controls,compile_controls,advance_batch,advance_branch


class NativeBatchPlanner(RuntimePlanner):
    """Reused native arenas with exact held-control steps and snapshots.

    At chunk boundaries use the same state reconstruction as the reference
    planner. This preserves its reset semantics while removing per-tick Python
    stepping, most GameState boxing, and branch deepcopy calls.
    """
    def __init__(self,model,*args,workers=1,stepping="compact",network='original',**kwargs):
        setup_started=time.perf_counter()
        if not 1<=workers<=16 or stepping not in ("compact","workers","multi_step","processes"):raise ValueError("Invalid native stepping configuration")
        if stepping=='processes' and workers>8:raise ValueError('CPU forecast processes must be 1..8')
        if stepping=='compact' and workers!=1:raise ValueError('Compact stepping uses one arena; use --stepping workers for multiple workers')
        self.workers=workers;self.stepping=stepping
        if network not in ('original','optimized','frozen','turbo','cuda-graphs'):raise ValueError('Invalid inference network')
        self.network=network
        if network=='cuda-graphs' and (next(model.parameters()).device.type!='cuda' or not torch.cuda.is_available()):
            raise ValueError('CUDA graphs require the model on an available CUDA device')
        super().__init__(model,*args,**kwargs)
        self.inference_kernel=None
        if network!='original':
            from replay_il_inference import InferenceKernel,freeze_kernel
            if network in ('turbo','cuda-graphs'):
                from replay_il_turbo import TurboKernel
                self.inference_kernel=TurboKernel(self.model)
            else:self.inference_kernel=InferenceKernel(self.model)
            if network in ('frozen','turbo','cuda-graphs'):self.inference_kernel=freeze_kernel(self.inference_kernel)
        self.graph_features=None;self.capture_graphs=False
        if network=='cuda-graphs':
            from replay_il_turbo import GraphFeatures
            self.graph_features=GraphFeatures(self.inference_kernel,self.device,
                self.model.history+self.candidates*((self.horizon+7)//8),self.model.history)
        self.control_plans=compile_controls(self.book) if network!='original' else None
        self.snapshot=native_encoded
        if network in ('turbo','cuda-graphs'):
            from replay_il_snapshot import encoded
            self.snapshot=encoded
        if stepping=='multi_step' and not callable(getattr(rs.Arena,'multi_step',None)):
            raise ValueError('Installed RocketSim lacks native multi_step; use workers stepping instead')
        self._pool=ThreadPoolExecutor(max_workers=workers) if stepping=="workers" and workers>1 else None
        self._base_arena=self.engine._arena;self._native_arenas=[]
        self.process_pool=None
        if stepping=='processes':
            from replay_il_processes import ForecastProcesses
            self.process_pool=ForecastProcesses(self.book,min(workers,self.candidates),fast_snapshot=network in ('turbo','cuda-graphs'))
        self.network_setup_ms=(time.perf_counter()-setup_started)*1000
    def encode_features(self,observations):
        return super().encode_features(observations) if self.inference_kernel is None else self.inference_kernel.encode(observations)
    def decode_features(self,features):
        return super().decode_features(features) if self.inference_kernel is None else self.inference_kernel.decode(features)
    def begin(self):
        super().begin()
        if self.graph_features is not None:self.graph_features.begin(allow_capture=self.capture_graphs)
    def infer_batch(self,histories):
        if self.graph_features is None:return super().infer_batch(histories)
        result=self.graph_features.infer(histories)
        self.encoded_observations=self.graph_features.count
        return result
    def warmup(self,*args,**kwargs):
        """Capture supported shapes before play; irregular game shapes stay eager."""
        self.capture_graphs=True
        try:return self.choose(*args,**kwargs)
        finally:self.capture_graphs=False
    def _reset_boundary(self,branch,initial):
        e=self.engine;e._arena=branch['arena'];e._cars=branch['cars']
        e._agent_ids={car.id:aid for aid,car in e._cars.items()}
        e._hitboxes={car.id:initial.cars[aid].hitbox_type for aid,car in e._cars.items()}
        e._touches={car.id:0 for car in e._cars.values()};e._game_config=initial.config;e._tick_count=branch['tick']
        state=e._get_state();e.set_state(state,{})
        branch['cars']=dict(e._cars);branch['last']=None
        for aid,car in branch['cars'].items():
            if aid!=branch['ours']:car.set_controls(controls(branch['previous'][aid]))
    def _views(self,rows,previous,index):
        """The original builder's arithmetic, allocating only our observation.

        Keep float64 intermediates and quaternion normalization identical to the
        training builder. This avoids constructing observations for every car
        when only the controlled player's view is evaluated.
        """
        if not rows:return []
        builder=self.observer.builder;encoded=np.stack(rows);batch=len(rows)
        players=(encoded.shape[1]-55)//38
        q=np.zeros((batch,1,32));kv=np.zeros((batch,41,24));mask=np.zeros((batch,41))
        kv[:,6,3]=1;kv[:,6,5:11]=encoded[:,37:43];kv[:,6,17:20]=encoded[:,43:46]
        kv[:,7:,4]=1;kv[:,7:,5:8]=builder._boost_locations
        kv[:,7:,20]=.12+.88*(builder._boost_locations[:,2]>72)
        kv[:,7:,21]=encoded[:,3:37]
        teams=encoded[0,56::38]
        kv[:,:players,1]=1-teams;kv[:,:players,2]=teams;kv[:,index,0]=1
        for i in range(players):
            car=encoded[:,55+38*i:55+38*(i+1)]
            kv[:,i,5:8]=car[:,2:5];kv[:,i,8:11]=car[:,9:12]
            rotation=builder._quats_to_rot_mtx(car[:,5:9])
            kv[:,i,11:14]=rotation[:,:,0];kv[:,i,14:17]=rotation[:,:,2]
            kv[:,i,17:20]=car[:,12:15];kv[:,i,20]=car[:,37]
            kv[:,i,21]=car[:,33];kv[:,i,22]=car[:,34];kv[:,i,23]=car[:,36]
        if teams[index]==1:
            kv*=builder._invert
            kv[...,[1,2]]=kv[...,[2,1]]
        kv/=builder._norm;q[:,0,:24]=kv[:,index,:]
        builder.convert_to_relative(q,kv);q[:,0,24:32]=np.stack(previous)
        mask[:,players:6]=-10000.
        q=q.astype(np.float32);kv=kv.astype(np.float32);mask=mask.astype(np.float32)
        return [(q[i],kv[i],mask[i]) for i in range(batch)]
    @torch.inference_mode()
    def choose(self,state,previous,ours,history=None):
        from rlgym.rocket_league.common_values import GOAL_THRESHOLD
        synchronize(self.device);started=time.perf_counter();self.begin();initial=state
        current=self.observation(initial,previous,ours)
        history=deque(list(history or [])[-(self.model.history-1):]+[current],maxlen=self.model.history)
        logits,_=self.infer_batch([history]);logp=logits[0].log_softmax(-1).cpu()
        choices=logp.topk(self.candidates).indices.tolist()
        ordered=sorted(initial.cars,key=lambda aid:(bool(initial.cars[aid].is_orange),str(aid)))
        our_index=ordered.index(ours);sign=-1 if initial.cars[ours].is_orange else 1
        phases={'initial_observation_and_policy':(time.perf_counter()-started)*1000,
                'branch_setup':0.,'continuation_and_value_network':0.,'simulation_and_snapshots':0.,
                'observation_build':0.,'boundary_reconstruction':0.}
        phase_started=time.perf_counter()
        # Reuse arena allocations across decisions. Each starts via the same
        # RLGym reconstruction as the reference; no native clone ID remapping.
        arena_count=0 if self.stepping=='processes' else 1 if self.stepping=='compact' else len(choices)
        while len(self._native_arenas)<arena_count:
            self._native_arenas.append(rs.Arena(rs.GameMode.SOCCAR))
        branches=[]
        try:
            for index,first in enumerate(choices):
                arena=None if self.stepping=='processes' else self._native_arenas[0 if self.stepping=='compact' else index]
                cars={}
                if self.stepping not in ('compact','processes'):
                    self.engine._arena=arena;self.engine._cars={}
                    self.engine.set_state(initial,{})
                    cars=dict(self.engine._cars)
                old={aid:np.asarray(previous.get(aid,np.zeros(8)),np.float32).copy() for aid in initial.cars}
                for aid,car in cars.items():
                    if aid!=ours:car.set_controls(controls(old[aid]))
                branches.append({'arena':arena,'cars':cars,'state':initial,'history':deque(history,maxlen=self.model.history),
                    'first':first,'token':first,'goal':None,'tick':initial.tick_count,'last':None,'ours':ours,'previous':old})
            if self.process_pool is not None:
                self.process_pool.prepare(initial,branches[0]['previous'],ours,choices,sign)
            phases['branch_setup']=(time.perf_counter()-phase_started)*1000
            chunk=len(self.book[0]);native_steps=0
            for start in range(0,self.horizon,chunk):
                if start:
                    phase_started=time.perf_counter()
                    next_logits,_=self.infer_batch([b['history'] for b in branches])
                    for b,index in zip(branches,next_logits.argmax(-1).tolist()):b['token']=index
                    phases['continuation_and_value_network']+=(time.perf_counter()-phase_started)*1000
                phase_started=time.perf_counter()
                snapshots=[]
                if self.stepping=='processes':
                    replies=self.process_pool.step([branch['token'] for branch in branches],
                        min(chunk,self.horizon-start),start+chunk<self.horizon)
                    for reply in replies:
                        native_steps+=reply['native_step_calls']
                        snapshots.extend((branches[int(index)],row,action)
                            for index,row,action in zip(reply['indices'],reply['rows'],reply['actions']))
                        for index,tick,goal in reply['branches']:
                            branches[index]['tick']=tick;branches[index]['goal']=goal
                elif self.stepping=='compact':
                    for branch in branches:
                        if branch['goal'] is not None:continue
                        self.engine._arena=branch['arena'];self.engine._cars={}
                        self.engine.set_state(branch['state'],{})
                        branch['cars']=dict(self.engine._cars);branch['last']=None
                        for aid,car in branch['cars'].items():
                            if aid!=ours:car.set_controls(controls(branch['previous'][aid]))
                        rows,steps=advance_branch(branch,ours,self.book,min(chunk,self.horizon-start),ordered,sign,self.control_plans,self.snapshot)
                        snapshots.extend(rows);native_steps+=steps
                        if start+chunk<self.horizon and branch['goal'] is None:
                            self.engine._tick_count=branch['tick']
                            # _get_state constructs new objects; unlike input
                            # caller state these internal snapshots need no copy.
                            branch['state']=self.engine._get_state()
                elif self.stepping=='workers':
                    active=[b for b in branches if b['goal'] is None]
                    tasks=[(b,ours,self.book,min(chunk,self.horizon-start),ordered,sign,self.control_plans,self.snapshot) for b in active]
                    if self._pool is None:
                        outcomes=[advance_branch(*args) for args in tasks]
                    else:
                        jobs=[self._pool.submit(advance_branch,*args) for args in tasks]
                        # Resolve every job before propagating an error: no arena
                        # may still be stepping when a failed search is retried.
                        outcomes=[];failure=None
                        for job in jobs:
                            try:outcomes.append(job.result())
                            except Exception as error:failure=error
                        if failure is not None:raise failure
                    for rows,steps in outcomes:snapshots.extend(rows);native_steps+=steps
                else:
                    for offset in range(0,min(chunk,self.horizon-start),8):
                        active=[b for b in branches if b['goal'] is None]
                        if not active:break
                        count=min(8,self.horizon-start-offset,chunk-offset)
                        commands=np.stack([self.book[b['token'],offset:offset+count] for b in active])
                        native_steps+=advance_batch(active,ours,commands)
                        for b,command in zip(active,commands[:,-1]):
                            b['tick']+=count
                            encoded=native_encoded(b['arena'],b['cars'],ordered)
                            snapshots.append((b,encoded,command.copy()))
                            if abs(encoded[38])>GOAL_THRESHOLD:b['goal']=1. if sign*encoded[38]>0 else -1.
                phases['simulation_and_snapshots']+=(time.perf_counter()-phase_started)*1000
                phase_started=time.perf_counter()
                views=self._views([r for _,r,_ in snapshots],[p for _,_,p in snapshots],our_index)
                for (branch,_,_),view in zip(snapshots,views):branch['history'].append(view)
                phases['observation_build']+=(time.perf_counter()-phase_started)*1000
                if start+chunk<self.horizon and self.stepping not in ('compact','processes'):
                    phase_started=time.perf_counter()
                    for b in branches:
                        if b['goal'] is None:self._reset_boundary(b,initial)
                    phases['boundary_reconstruction']+=(time.perf_counter()-phase_started)*1000
            phase_started=time.perf_counter()
            _,predicted=self.infer_batch([b['history'] for b in branches]);predicted=predicted.cpu().numpy();records=[]
            phases['continuation_and_value_network']+=(time.perf_counter()-phase_started)*1000
            for b,values in zip(branches,predicted):
                mean=float(values.mean()) if b['goal'] is None else b['goal']
                spread=float(values.std()) if b['goal'] is None else 0.
                score=mean-self.uncertainty*spread+self.prior*float(logp[b['first']])
                records.append({'token':b['first'],'score':score,'value':mean,'uncertainty':spread})
            best=max(records,key=lambda r:r['score']);synchronize(self.device);elapsed=time.perf_counter()-started
            return self.book[best['token']].copy(),{'mode':'search','backend':'native-'+self.stepping,
                'workers':len(self.process_pool.processes) if self.process_pool is not None else self.workers if self.stepping=='workers' else None,
                'worker_torch_loaded':[row['torch_loaded'] for row in self.process_pool.worker_info] if self.process_pool is not None else [],
                'selected':best,'candidates':len(records),
                'horizon_seconds':self.horizon/120,'latency_ms':elapsed*1000,'maximum_decisions_per_second':1/max(elapsed,1e-9),
                'execute_first_ticks':8,'device':str(self.device),'encoded_observations':self.encoded_observations,
                'native_step_calls':native_steps,'phase_ms':phases,'network':self.network,
                'cuda_graphs':self.graph_features.report() if self.graph_features is not None else None,
                'opponents':'last observed controls held; future human inputs are unknown','records':records}
        finally:self.engine._arena=self._base_arena
    def close(self):
        if self.graph_features is not None:self.graph_features.close()
        if self.process_pool is not None:self.process_pool.close()
        if self._pool is not None:self._pool.shutdown(wait=True)
        self.engine._arena=self._base_arena;self.engine._cars={};self._native_arenas.clear();super().close()


class ForecastParityError(ValueError):
    """A real comparison failure, with reportable diagnostics."""
    def __init__(self,message,details=None):
        super().__init__(message);self.details=details or {}


def compare_records(reference,native,tolerance=1e-4):
    """Match branches by token; list order is not part of forecast parity.

    FP32 kernel roundoff can reorder close policy logits. A different set of
    candidates, changed selected token or excessive score/value errors still
    fails. Nothing is rounded or reordered in the actual planner.
    """
    left=reference['records'];right=native['records']
    if reference['candidates']!=native['candidates'] or any(
            len(rows)!=report['candidates'] for rows,report in ((left,reference),(right,native))):
        raise ForecastParityError('Forecast parity failed: candidate counts differ',
            {'reference_candidates':reference['candidates'],'native_candidates':native['candidates'],
             'reference_record_count':len(left),'native_record_count':len(right)})
    by_left={row['token']:row for row in left};by_right={row['token']:row for row in right}
    if len(by_left)!=len(left) or len(by_right)!=len(right):
        raise ForecastParityError('Forecast parity failed: duplicate candidate tokens')
    common=sorted(by_left.keys()&by_right.keys());errors=[];nonfinite=[];worst=None
    for token in common:
        for key in ('score','value','uncertainty'):
            a=float(by_left[token][key]);b=float(by_right[token][key])
            if not np.isfinite(a) or not np.isfinite(b):
                nonfinite.append({'token':token,'field':key});continue
            error=abs(a-b);errors.append(error)
            if worst is None or error>worst['absolute_error']:
                worst={'token':token,'field':key,'absolute_error':error,'reference':a,'native':b}
    error=max(errors,default=0.)
    details={'same_candidate_set':by_left.keys()==by_right.keys(),
        'candidate_order_changed':[row['token'] for row in left]!=[row['token'] for row in right],
        'reference_only_tokens':sorted(by_left.keys()-by_right.keys()),
        'native_only_tokens':sorted(by_right.keys()-by_left.keys()),'matched_candidates':len(common),
        'same_selected_token':reference['selected']['token']==native['selected']['token'],
        'maximum_absolute_error':error if not nonfinite else None,'tolerance':tolerance,
        'nonfinite_fields':nonfinite,'worst_difference':worst}
    if not details['same_candidate_set']:
        raise ForecastParityError('Forecast parity failed: candidate sets differ',details)
    if reference['selected']['token'] not in by_left or native['selected']['token'] not in by_right:
        raise ForecastParityError('Forecast parity failed: selected token is absent from candidates',details)
    if nonfinite or error>tolerance or not details['same_selected_token']:
        raise ForecastParityError(f'Forecast parity failed: max score/value error {details["maximum_absolute_error"]}, '
                                  f'same selected token {details["same_selected_token"]}',details)
    return details


def benchmark(folder,*,device='auto',threads=2,workers=1,stepping='compact',
              repeats=3,warmups=1,candidate_counts=(4,16,64),compare_reference=True,team_size=1,
              network='original',compare_native=False,compare_compact=False,compare_frozen=False):
    """Measure the actual checkpoint, retaining the full horizon in both paths."""
    from pathlib import Path
    import platform,importlib.metadata
    from replay_il_runtime import resolve_device
    from replay_il.planner import load
    from slater_v041_core import sha256
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    if not 1<=threads<=64 or not 1<=repeats<=20 or not 1<=warmups<=5:
        raise ValueError('Threads must be 1..64, repeats 1..20, warmups 1..5')
    if not 1<=workers<=16 or stepping not in ('compact','workers','multi_step','processes') or team_size not in (1,2,3):
        raise ValueError('Invalid simulation worker, stepping or team-size setting')
    if stepping=='processes' and workers>8:raise ValueError('CPU forecast processes must be 1..8')
    if compare_compact and stepping!='processes':raise ValueError('Compact comparison requires process stepping')
    if stepping=='compact' and workers!=1:raise ValueError('Compact stepping uses one arena; use --stepping workers for multiple workers')
    if network not in ('original','optimized','frozen','turbo','cuda-graphs'):raise ValueError('Invalid inference network')
    if not candidate_counts or any(not 1<=c<=64 for c in candidate_counts):
        raise ValueError('Candidates must be 1..64')
    target=resolve_device(device);torch.set_num_threads(threads);folder=Path(folder).resolve()
    print('NATIVE_RUNTIME_DEVICE:',target,'| Torch threads:',threads,'| simulation workers:',workers,
          '| stepping:',stepping,'| network:',network,flush=True)
    model,book=load(folder,device='cpu');model.to(target).eval()
    engine=RocketSimEngine(rlbot_delay=False)
    state=engine.create_base_state();FixedTeamSizeMutator(team_size,team_size).apply(state,{})
    # Fix kickoff placement so repeat invocations measure the same scenario.
    import random
    rng_state=random.getstate();numpy_state=np.random.get_state()
    try:
        random.seed(271);np.random.seed(271);KickoffMutator().apply(state,{})
    finally:random.setstate(rng_state);np.random.set_state(numpy_state)
    state=engine.set_state(state,{})
    previous={aid:np.zeros(8,np.float32) for aid in state.cars};ours=next(iter(state.cars))
    deadline=8/120*1000;results=[];comparisons=[]

    def measure(planner,choose,backend):
        try:
            cold=None
            for index in range(warmups):
                warmup=planner.warmup if getattr(planner,'graph_features',None) is not None else choose
                _,report=warmup(state,previous,ours)
                if index==0:cold=report['latency_ms']
            samples=[];phase_samples=[]
            for _ in range(repeats):
                _,report=choose(state,previous,ours);samples.append(report['latency_ms'])
                if 'phase_ms' in report:phase_samples.append(report['phase_ms'])
            summary={key:value for key,value in report.items() if key!='records'}
            summary.update(backend=backend,latency_samples_ms=samples,latency_median_ms=float(np.median(samples)),
                latency_p95_ms=float(np.quantile(samples,.95)),first_call_ms=cold,deadline_ms=deadline,
                meets_deadline_p95=bool(np.quantile(samples,.95)<=deadline),warmups=warmups,repeats=repeats)
            if hasattr(planner,'network_setup_ms'):summary['network_setup_ms']=planner.network_setup_ms
            if phase_samples:
                summary['phase_median_ms']={key:float(np.median([sample[key] for sample in phase_samples])) for key in phase_samples[0]}
            results.append(summary)
            print('RUNTIME',backend,'candidates',summary['candidates'],'median_ms',round(summary['latency_median_ms'],2),
                  'p95_ms',round(summary['latency_p95_ms'],2),'meets_67ms',summary['meets_deadline_p95'],flush=True)
            if summary['candidates']==64 and phase_samples:
                print('PHASES_MS',backend,{key:round(value,2) for key,value in summary['phase_median_ms'].items()},flush=True)
            return report,summary
        finally:planner.close()

    def compare(reference_report,reference_summary,native_report,native_summary,prefix):
        result={'candidates':native_summary['candidates'],'reference_backend':reference_summary['backend'],
                'native_backend':native_summary['backend'],
                'median_speedup':reference_summary['latency_median_ms']/native_summary['latency_median_ms']}
        try:
            result.update(status='passed',parity=compare_records(reference_report,native_report))
            # A second comparison cannot clear a failure from the first one.
            if native_summary.get('forecast_parity')!='failed':native_summary['forecast_parity']='passed'
            reordered=result['parity']['candidate_order_changed']
            print(prefix,'PARITY OK | candidates',result['candidates'],'| speedup',round(result['median_speedup'],2),
                  'x | reordered candidates:',reordered,flush=True)
        except ForecastParityError as error:
            result.update(status='failed',error=str(error),parity=error.details,
                reference_records=reference_report['records'],native_records=native_report['records'],
                reference_selected=reference_report['selected'],native_selected=native_report['selected'])
            native_summary['forecast_parity']='failed'
            print(prefix,'PARITY FAILED | candidates',result['candidates'],'|',error,
                  '| diagnostics will be saved in the report',flush=True)
        comparisons.append(result)

    try:
        policy=RuntimePlanner(model,book,candidates=1)
        measure(policy,policy.choose_policy,'policy')
        for count in candidate_counts:
            reference_report=reference_summary=None
            if compare_reference:
                planner=RuntimePlanner(model,book,candidates=count)
                reference_report,reference_summary=measure(planner,planner.choose,'reference')
            compact_report=compact_summary=None
            if compare_compact:
                planner=NativeBatchPlanner(model,book,candidates=count,network=network)
                compact_report,compact_summary=measure(planner,planner.choose,'native-compact-'+network)
            native_original_report=native_original_summary=None
            if network!='original' and compare_native:
                planner=NativeBatchPlanner(model,book,candidates=count,workers=workers,stepping=stepping)
                native_original_report,native_original_summary=measure(planner,planner.choose,'native-'+stepping+'-original')
            frozen_report=frozen_summary=None
            if compare_frozen and network not in ('original','optimized','frozen'):
                planner=NativeBatchPlanner(model,book,candidates=count,workers=workers,stepping=stepping,network='frozen')
                frozen_report,frozen_summary=measure(planner,planner.choose,'native-'+stepping+'-frozen')
            planner=NativeBatchPlanner(model,book,candidates=count,workers=workers,stepping=stepping,network=network)
            label='native-'+stepping+('-'+network if network!='original' else '')
            report,summary=measure(planner,planner.choose,label)
            if reference_report is not None:
                compare(reference_report,reference_summary,report,summary,'REFERENCE')
            if native_original_report is not None:
                compare(native_original_report,native_original_summary,report,summary,'NATIVE NETWORK')
            if compact_report is not None:
                compare(compact_report,compact_summary,report,summary,'COMPACT VS MULTICORE')
            if frozen_report is not None:
                compare(frozen_report,frozen_summary,report,summary,'FROZEN VS TURBO')
    finally:engine.close()
    recommended={}
    for count in sorted({row['candidates'] for row in results if row['mode']=='search'}):
        rows=[row for row in results if row['mode']=='search' and row['candidates']==count
              and row.get('forecast_parity')!='failed']
        if not rows:continue
        fastest=min(rows,key=lambda row:row['latency_p95_ms'])
        recommended[str(count)]={'backend':fastest['backend'],'p95_ms':fastest['latency_p95_ms'],
                                 'meets_deadline':fastest['meets_deadline_p95'],
                                 'forecast_parity':fastest.get('forecast_parity','not_checked')}
    validation='failed' if any(row['status']=='failed' for row in comparisons) else 'passed' if comparisons else 'not_checked'
    return {'schema':'replay-il-native-runtime-v3' if stepping=='processes' else 'replay-il-native-runtime-v2.1','checkpoint_sha256':sha256(folder/'best.pt'),
        'book_sha256':sha256(folder/'tokens.npy'),'device':str(target),'requested_device':device,
        'device_name':torch.cuda.get_device_name(target) if target.type=='cuda' else platform.processor() or 'CPU',
        'cuda_available':torch.cuda.is_available(),'torch':torch.__version__,'rocketsim':importlib.metadata.version('rocketsim'),
        'threads':threads,'workers':workers,'stepping':stepping,'network':network,'format':f'{team_size}v{team_size}',
        'seed':271,'kickoff_positions':{str(aid):car.physics.position.tolist() for aid,car in state.cars.items()},
        'results':results,'comparisons':comparisons,'validation_status':validation,
        'recommended_backend_by_candidates':recommended,'training_modified':False,
        'note':'Warmed kickoff-state latency, not match strength or a playable adapter. Simulation runs on CPU. '
               'Workers stepping includes Python scheduling and feature extraction; it is not an all-C++ GigaLearn port.'}


def main(argv=None):
    import argparse,re
    from pathlib import Path
    from slater_v041_core import atomic_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',default='replay_scratch01')
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--workers',type=int,default=1,help='Simulation workers, independent of Torch threads')
    parser.add_argument('--stepping',choices=('compact','workers','multi_step','processes'),default='compact')
    parser.add_argument('--compare-compact',action='store_true',help='Compare multicore forecasts with the preceding compact backend')
    parser.add_argument('--network',choices=('original','optimized','frozen','turbo','cuda-graphs'),default='frozen')
    parser.add_argument('--compare-frozen',action='store_true',help='Compare the preceding frozen network with turbo/CUDA graphs')
    parser.add_argument('--skip-native-comparison',action='store_true',help='Skip timing the preceding native network')
    parser.add_argument('--team-size',type=int,choices=(1,2,3),default=1)
    parser.add_argument('--repeats',type=int,default=3);parser.add_argument('--warmups',type=int,default=1)
    parser.add_argument('--candidates',type=int,nargs='+',default=[4,8,12,16,64])
    parser.add_argument('--skip-reference',action='store_true',help='Skip older Python reference timings; native comparison still checks parity')
    args=parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',args.run):parser.error('Invalid run name')
    folder=Path(__file__).resolve().parent/'data/isolated/replay_imitation/runs'/args.run
    report=benchmark(folder,device=args.device,threads=args.threads,workers=args.workers,stepping=args.stepping,
        team_size=args.team_size,repeats=args.repeats,warmups=args.warmups,candidate_counts=args.candidates,
        compare_reference=not args.skip_reference,network=args.network,compare_native=not args.skip_native_comparison,
        compare_compact=args.compare_compact,compare_frozen=args.compare_frozen)
    output=folder/('native_runtime_multicore_benchmark.json' if args.stepping=='processes' else 'native_runtime_v2_benchmark.json')
    atomic_json(output,report)
    print('REPORT:',output,flush=True)
    if report['validation_status']=='failed':
        raise ValueError('Forecast parity failed. Timings and candidate diagnostics were saved in the report above; '
                         'failed backends are excluded from recommendations.')
    print('Inference benchmark complete. Your trained model and training code are unchanged.',flush=True)


if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError,RuntimeError,KeyError) as error:
        print('STOPPED:',str(error),flush=True);raise SystemExit(1)
