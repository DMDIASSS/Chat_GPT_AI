"""Compare compiler-free inference paths and tune workers on the actual PC."""
from pathlib import Path
import argparse
import copy
import platform
import random
import re
import numpy as np
import torch
from replay_il_native_runtime import NativeBatchPlanner,compare_records,ForecastParityError
from replay_il_runtime import resolve_device
from replay_il.planner import load
from slater_v041_core import atomic_json,sha256

ROOT=Path(__file__).resolve().parent


def scenarios(engine,team_size):
    """Fixed kickoff timings plus separate contact, goal and roster validation."""
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    def kickoff(size):
        state=engine.create_base_state();FixedTeamSizeMutator(size,size).apply(state,{})
        old=random.getstate();old_np=np.random.get_state()
        try:random.seed(271);np.random.seed(271);KickoffMutator().apply(state,{})
        finally:random.setstate(old);np.random.set_state(old_np)
        return copy.deepcopy(engine.set_state(state,{}))
    initial=kickoff(team_size);ours=next(iter(initial.cars))
    cases=[('kickoff',initial,ours)]
    goal=copy.deepcopy(initial);goal.ball.position=np.array([0,5050,100],np.float32)
    goal.ball.linear_velocity=np.array([0,1500,0],np.float32)
    cases.append(('early_goal',goal,ours))
    for size in (1,2,3):
        state=kickoff(size)
        for index,car in enumerate(state.cars.values()):
            car.physics.position=np.array([-240+index*170,-350+index*240,17 if index%2 else 250],np.float32)
            car.physics.linear_velocity=np.array([250-index*35,330-index*60,20],np.float32)
            car.physics.euler_angles=np.array([.1*index,.45*index,.13*index],np.float32)
            car.physics.angular_velocity=np.array([.2,.3,-.1],np.float32)
            car.on_ground=index%2==1;car.boost_amount=38.+index
        state.ball.position=np.array([60,70,120],np.float32)
        state.ball.linear_velocity=np.array([-180,350,60],np.float32)
        state.boost_pad_timers[::3]=2.5
        orange=next(aid for aid,car in state.cars.items() if car.is_orange)
        cases.append((f'{size}v{size}_moving_orange',state,orange))
    return cases


def tune(folder,*,device='auto',workers=(2,3,4),threads=1,candidate_counts=(16,32,64),
         repeats=5,warmups=2,team_size=1,networks=None):
    if not workers or any(not 1<=w<=8 for w in workers):raise ValueError('Workers must be 1..8')
    if not candidate_counts or any(not 1<=c<=64 for c in candidate_counts):raise ValueError('Candidates must be 1..64')
    if not 1<=threads<=8 or not 1<=repeats<=50 or not 1<=warmups<=5 or team_size not in (1,2,3):
        raise ValueError('Invalid thread, repeat, warmup or team-size budget')
    target=resolve_device(device)
    networks=tuple(networks or (('turbo','cuda-graphs') if target.type=='cuda' else ('turbo',)))
    if any(n not in ('turbo','cuda-graphs') for n in networks):raise ValueError('Tuned networks must be turbo or cuda-graphs')
    if 'cuda-graphs' in networks and target.type!='cuda':raise ValueError('CUDA graphs require --device cuda')
    folder=Path(folder).resolve();before={p.name:sha256(p) for p in (folder/'best.pt',folder/'tokens.npy')}
    model,book=load(folder,device='cpu');model.to(target).eval();counts=sorted(set(min(c,len(book)) for c in candidate_counts))
    from rlgym.rocket_league.sim import RocketSimEngine
    engine=RocketSimEngine(rlbot_delay=False);cases=scenarios(engine,team_size)
    _,initial,ours=cases[0];results=[];comparisons=[];failures=[];references={};deadline=8/120*1000
    print('TURBO_DEVICE:',target,'|',torch.cuda.get_device_name(target) if target.type=='cuda' else 'CPU',flush=True)
    print('Fixed FP32 weights | 1-second horizon | exact control edges | execute 8 ticks',flush=True)
    configurations=[('frozen',4,2)]+[(network,w,threads) for network in networks for w in sorted(set(workers))]
    try:
        for network,worker_count,torch_threads in configurations:
            torch.set_num_threads(torch_threads)
            label=f'{network}-workers{worker_count}-threads{torch_threads}'
            for count in counts:
                planner=None
                try:
                    if target.type=='cuda':torch.cuda.reset_peak_memory_stats(target)
                    planner=NativeBatchPlanner(model,book,candidates=count,workers=worker_count,stepping='processes',network=network)
                    for _ in range(warmups):
                        if network=='cuda-graphs':planner.warmup(initial,{},ours)
                        else:planner.choose(initial,{},ours)
                    samples=[];phases=[]
                    for _ in range(repeats):
                        _,last=planner.choose(initial,{},ours);samples.append(last['latency_ms']);phases.append(last['phase_ms'])
                    row={'backend':label,'network':network,'workers':worker_count,'threads':torch_threads,'candidates':count,
                        'latency_samples_ms':samples,'latency_median_ms':float(np.median(samples)),
                        'latency_p95_ms':float(np.quantile(samples,.95)),'latency_max_ms':max(samples),'deadline_ms':deadline,
                        'meets_deadline_p95':bool(np.quantile(samples,.95)<=deadline),'warmups':warmups,'repeats':repeats,
                        'phase_median_ms':{key:float(np.median([p[key] for p in phases])) for key in phases[0]},
                        'network_setup_ms':planner.network_setup_ms,'cuda_graphs':last.get('cuda_graphs'),
                        'worker_torch_loaded':last['worker_torch_loaded'],'forecast_parity':'reference' if network=='frozen' else 'passed'}
                    if target.type=='cuda':
                        row['peak_torch_allocated_mib']=torch.cuda.max_memory_allocated(target)/2**20
                        row['peak_torch_reserved_mib']=torch.cuda.max_memory_reserved(target)/2**20
                    records={'kickoff':last}
                    if count==max(counts):
                        for name,state,controlled in cases[1:]:
                            _,records[name]=planner.choose(state,{},controlled)
                    if network=='frozen':references[count]=records
                    else:
                        for name,report in records.items():
                            comparison={'backend':label,'candidates':count,'scenario':name}
                            try:comparison.update(status='passed',parity=compare_records(references[count][name],report))
                            except ForecastParityError as error:
                                row['forecast_parity']='failed'
                                comparison.update(status='failed',error=str(error),details=error.details,
                                    reference_records=references[count][name]['records'],actual_records=report['records'])
                            comparisons.append(comparison)
                    results.append(row)
                    print('TURBO',label,'candidates',count,'median_ms',round(row['latency_median_ms'],2),
                          'p95_ms',round(row['latency_p95_ms'],2),'parity',row['forecast_parity'],
                          'meets_67ms',row['meets_deadline_p95'],flush=True)
                    if row['cuda_graphs'] and row['cuda_graphs']['capture_failure']:
                        print('CUDA_GRAPH_FALLBACK:',row['cuda_graphs']['capture_failure'],flush=True)
                except (RuntimeError,ValueError) as error:
                    failures.append({'backend':label,'candidates':count,'error':str(error)[:1500]})
                    print('CONFIGURATION_FAILED:',label,'candidates',count,str(error)[:300],flush=True)
                    if network=='frozen':raise
                finally:
                    if planner is not None:planner.close()
                    if target.type=='cuda':torch.cuda.empty_cache()
    finally:engine.close()
    if before!={name:sha256(folder/name) for name in before}:raise ValueError('Model/vocabulary changed during benchmark')
    # A configuration failing any validation case is never recommended at a
    # different candidate budget, even if its kickoff-only comparison passed.
    invalid={row['backend'] for row in comparisons if row['status']=='failed'}|{row['backend'] for row in failures}
    invalid|={row['backend'] for row in results if row['network']=='cuda-graphs' and (
        not row['cuda_graphs']['captured_shapes'] or row['cuda_graphs']['capture_failure'])}
    recommended={}
    for count in counts:
        eligible=[r for r in results if r['candidates']==count and r['backend'] not in invalid]
        if eligible:
            best=min(eligible,key=lambda r:r['latency_p95_ms'])
            recommended[str(count)]={k:best[k] for k in ('backend','network','workers','threads','candidates','latency_p95_ms','meets_deadline_p95','forecast_parity')}
    viable=[r for r in recommended.values() if r['meets_deadline_p95']]
    selected=max(viable,key=lambda r:r['candidates']) if viable else None
    baseline={r['candidates']:r['latency_median_ms'] for r in results if r['network']=='frozen'}
    for row in results:row['median_speedup_vs_frozen']=baseline[row['candidates']]/row['latency_median_ms']
    print('RECOMMENDED:',selected if selected else 'No tested search configuration meets 66.67 ms',flush=True)
    return {'schema':'replay-il-turbo-runtime-v1','checkpoint_sha256':before['best.pt'],'book_sha256':before['tokens.npy'],
        'device':str(target),'device_name':torch.cuda.get_device_name(target) if target.type=='cuda' else platform.processor() or 'CPU',
        'torch':torch.__version__,'format':f'{team_size}v{team_size}','seed':271,'horizon_seconds':1.,'execute_first_ticks':8,
        'training_modified':False,'results':results,'comparisons':comparisons,'configuration_failures':failures,
        'validation_status':('passed_with_rejections' if recommended else 'failed') if invalid else 'passed',
        'rejected_backends':sorted(invalid),'recommended_backend_by_candidates':recommended,
        'selected_profile':selected,'cuda_graphs_tested':target.type=='cuda' and 'cuda-graphs' in networks,
        'note':'Warmed fixed-kickoff timings; extra moving/early-goal/2v2/3v3 cases check forecast parity. '
               'Five repetitions do not establish full-match tail latency or playing strength. '
               'This tunes inference; it is not a playable game adapter. Torch memory totals exclude the game/driver.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',default='replay_scratch01')
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--workers',type=int,nargs='+',default=[2,3,4])
    parser.add_argument('--threads',type=int,default=1)
    parser.add_argument('--candidates',type=int,nargs='+',default=[16,32,64])
    parser.add_argument('--networks',choices=('turbo','cuda-graphs'),nargs='+')
    parser.add_argument('--repeats',type=int,default=5);parser.add_argument('--warmups',type=int,default=2)
    parser.add_argument('--team-size',type=int,choices=(1,2,3),default=1)
    args=parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',args.run):parser.error('Invalid run name')
    folder=ROOT/'data/isolated/replay_imitation/runs'/args.run
    report=tune(folder,device=args.device,workers=args.workers,threads=args.threads,candidate_counts=args.candidates,
        networks=args.networks,repeats=args.repeats,warmups=args.warmups,team_size=args.team_size)
    output=folder/'turbo_runtime_benchmark.json';atomic_json(output,report)
    profile=folder/'runtime_profile.json'
    atomic_json(profile,{'schema':'replay-il-runtime-profile-v1','checkpoint_sha256':report['checkpoint_sha256'],
        'book_sha256':report['book_sha256'],'device_name':report['device_name'],'selected':report['selected_profile'],
        'recommendations':report['recommended_backend_by_candidates'],'source_report':output.name,
        'note':'Measured inference settings; no game adapter is installed by this benchmark.'})
    print('REPORT:',output,flush=True);print('PROFILE:',profile,flush=True)
    if report['rejected_backends']:
        print('REJECTED_CONFIGURATIONS:',', '.join(report['rejected_backends']),
              '| excluded from the saved recommendations; see diagnostics in the report',flush=True)
    if report['validation_status']=='failed':
        raise ValueError('Some configurations failed validation. Diagnostics saved; failed configurations excluded from recommendations.')
    print('COMPLETE: model, training code, action vocabulary and forecast horizon preserved.',flush=True)


if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError,RuntimeError) as error:
        print('STOPPED:',str(error),flush=True);raise SystemExit(1)
