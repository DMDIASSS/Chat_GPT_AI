"""Benchmark the trained RVQ reference search without generating training data."""
from pathlib import Path
import time
import numpy as np
import torch
from replay_rvq.inference import load,freeze
from replay_rvq.search import Search
from slater_v041_core import atomic_json,sha256


def benchmark(root,*,device='auto',candidates=(4,16,64),repeats=3):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    if not 1<=repeats<=20 or not candidates or any(not 1<=n<=64 for n in candidates):raise ValueError('Invalid benchmark budget')
    if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
    if device not in ('cpu','cuda') or device=='cuda' and not torch.cuda.is_available():raise ValueError('Requested device unavailable')
    root=Path(root);torch.set_num_threads(2);model=load(root,device);kernel=freeze(model)
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        state=engine.create_base_state();FixedTeamSizeMutator(1,1).apply(state,{});KickoffMutator().apply(state,{})
        state=engine.set_state(state,{});previous={aid:np.zeros(8,np.float32) for aid in state.cars};ours=next(iter(state.cars))
    finally:engine.close()
    results=[]
    for count in candidates:
        planner=Search(kernel,device=device,candidates=count)
        try:
            planner.choose(state,previous,ours);rows=[planner.choose(state,previous,ours)[1] for _ in range(repeats)]
        finally:planner.close()
        latency=[row['latency_ms'] for row in rows]
        report={'candidates':count,'median_ms':float(np.median(latency)),'p95_ms':float(np.percentile(latency,95)),
            'meets_66_7ms':float(np.percentile(latency,95))<=1000*8/120,'records':rows}
        results.append(report);print('RVQ_SEARCH:',count,'median',round(report['median_ms'],2),'p95',round(report['p95_ms'],2),flush=True)
    report={'schema':'replay-rvq-search-benchmark-v1','device':device,'checkpoint_sha256':sha256(root/'policy/best.pt'),
        'results':results,'scope':'warmed kickoff forecast timing only; no training, no playing-strength evaluation'}
    atomic_json(root/'search_benchmark.json',report);return report
