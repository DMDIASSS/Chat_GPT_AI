"""Runtime inference parity and device/latency-report checks; no training data."""
import copy
from pathlib import Path
import numpy as np
import pytest
import torch
from replay_il.model import ChunkPolicy
from replay_il.planner import Planner
from replay_il_runtime import RuntimePlanner,resolve_device,benchmark
from slater_v041_core import atomic_json,sha256

@pytest.fixture(scope='module')
def model_book():
    torch.set_num_threads(2);torch.manual_seed(44)
    model=ChunkPolicy(vocabulary=8).eval()
    rng=np.random.default_rng(44)
    book=np.zeros((8,32,8),np.float32)
    for i in range(8):
        book[i,:,0]=1;book[i,:,1]=rng.choice([-1.,0.,1.]);book[i,:,6]=i%2
        if i%3==0:book[i,4:12,5]=1;book[i,4:12,2]=-1
    return model,book

def state_fixture(players=2):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    engine=RocketSimEngine(rlbot_delay=False)
    s=engine.create_base_state();FixedTeamSizeMutator(players//2,players//2).apply(s,{});KickoffMutator().apply(s,{})
    s=copy.deepcopy(engine.set_state(s,{}));engine.close()
    return s

@pytest.mark.parametrize('players',[2,4,6])
def test_batched_observations_match_existing_observer_for_both_teams(model_book,players):
    model,book=model_book;planner=RuntimePlanner(model,book,candidates=2)
    states=[state_fixture(players) for _ in range(3)]
    rng=np.random.default_rng(9)
    previous=[{aid:rng.uniform(-1,1,8).astype(np.float32) for aid in state.cars} for state in states]
    try:
        for ours in (next(iter(states[0].cars)),list(states[0].cars)[-1]):
            actual=planner.observations_batch(states,previous,ours)
            for state,prev,got in zip(states,previous,actual):
                expected=planner.observation(state,prev,ours)
                for a,b in zip(got,expected):np.testing.assert_array_equal(a,b)
    finally:planner.close()

def test_cached_spatial_history_matches_full_model(model_book):
    model,book=model_book;planner=RuntimePlanner(model,book,candidates=2)
    state=state_fixture();ours=next(iter(state.cars))
    try:
        views=[planner.observation(state,{ours:np.full(8,i/10,np.float32)},ours) for i in range(10)]
        histories=[views[:2],views[1:9],views[2:10]]
        padded=[[h[0]]*(8-len(h))+h for h in histories]
        raw=tuple(torch.as_tensor(np.stack([np.stack([o[k] for o in h]) for h in padded])) for k in range(3))
        with torch.inference_mode():expected=model(raw)
        actual=planner.infer_batch(histories)
        for a,b in zip(actual,expected):torch.testing.assert_close(a,b,atol=3e-5,rtol=3e-5)
        encoded=planner.encoded_observations
        planner.infer_batch(histories)
        assert planner.encoded_observations==encoded==10
    finally:planner.close()

@pytest.mark.parametrize('goal',[False,True])
def test_search_matches_original_scores_tokens_and_preserves_state(model_book,goal):
    model,book=model_book;state=state_fixture();ours=next(iter(state.cars))
    if goal:
        state.ball.position=np.array([0,5050,100],np.float32);state.ball.linear_velocity=np.array([0,1500,0],np.float32)
    before=state.ball.position.copy();previous={k:np.zeros(8,np.float32) for k in state.cars}
    original=Planner(model,book,candidates=8);runtime=RuntimePlanner(model,book,candidates=8)
    try:
        a,first=original.choose(state,previous,ours);b,second=runtime.choose(state,previous,ours)
        assert first['selected']['token']==second['selected']['token']
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(state.ball.position,before)
        assert first['candidates']==second['candidates']==8
        for x,y in zip(first['records'],second['records']):
            assert x['token']==y['token']
            for k in ('score','value','uncertainty'):assert x[k]==pytest.approx(y[k],abs=3e-5)
        assert second['horizon_seconds']==1.0 and second['execute_first_ticks']==8
    finally:original.close();runtime.close()

def test_device_selection_never_silently_ignores_cuda(monkeypatch):
    monkeypatch.setattr(torch.cuda,'is_available',lambda:False)
    assert str(resolve_device('auto'))=='cpu'
    with pytest.raises(ValueError,match='CUDA was requested'):resolve_device('cuda')
    monkeypatch.setattr(torch.cuda,'is_available',lambda:True)
    assert str(resolve_device('auto'))==str(resolve_device('cuda'))=='cuda'
    assert str(resolve_device('cpu'))=='cpu'

def test_benchmark_loads_real_checkpoint_and_keeps_training_sources_unchanged(tmp_path,model_book):
    model,book=model_book
    torch.save({'config':model.config,'model':model.state_dict()},tmp_path/'best.pt')
    np.save(tmp_path/'tokens.npy',book)
    atomic_json(tmp_path/'selected.json',{'sha256':sha256(tmp_path/'best.pt')})
    atomic_json(tmp_path/'tokenizer.json',{'book_sha256':sha256(tmp_path/'tokens.npy')})
    root=Path(__file__).resolve().parents[1]
    before={p:sha256(p) for p in (root/'replay_il').glob('*.py')}
    result=benchmark(tmp_path,device='cpu',repeats=2,warmups=1,candidate_counts=[2])
    assert result['device']=='cpu' and result['checkpoint_sha256']==sha256(tmp_path/'best.pt')
    assert {r['mode'] for r in result['results']}=={'policy','search'}
    for row in result['results']:
        assert len(row['latency_samples_ms'])==2
        assert row['latency_p95_ms']>=row['latency_median_ms']>0
        assert row['meets_deadline_p95']==(row['latency_p95_ms']<=row['deadline_ms'])
    assert {p:sha256(p) for p in before}==before
