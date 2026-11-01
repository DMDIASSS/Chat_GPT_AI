"""Native forecast physics/observation parity against the installed simulator."""
import copy
import numpy as np
import pytest
import torch
from replay_il.model import ChunkPolicy
from replay_il_runtime import RuntimePlanner
from replay_il_native_runtime import NativeBatchPlanner,native_encoded,advance_batch,advance_branch,compile_controls,controls,benchmark,compare_records
from test_replay_runtime import model_book,state_fixture

@pytest.mark.parametrize('players',[2,4,6])
def test_native_snapshot_features_match_original_all_colors_and_flags(model_book,players):
    from rlgym.rocket_league.sim import RocketSimEngine
    model,book=model_book;planner=NativeBatchPlanner(model,book,candidates=2)
    engine=RocketSimEngine(rlbot_delay=False);rng=np.random.default_rng(28)
    try:
        for phase in range(8):
            s=state_fixture(players)
            for i,car in enumerate(s.cars.values()):
                car.physics.euler_angles=np.array([phase*.31,phase*.47+i,phase*.63],np.float32)
                car.physics.angular_velocity=rng.uniform(-3,3,3).astype(np.float32)
                car.on_ground=phase%2==0
                car.has_flipped=phase==2;car.has_double_jumped=phase==3
                car.air_time_since_jump=1.3 if phase==4 else .4
                if phase==5:car.demo_respawn_timer=1.2
                car.boost_amount=float((phase*13+i*19)%101)
            s.boost_pad_timers[:]=np.resize(np.array([0,1e-7,1e-6,1.0001e-6,1.3,8.5],np.float32),34)
            s=engine.set_state(s,{})
            ordered=sorted(s.cars,key=lambda aid:(s.cars[aid].is_orange,str(aid)))
            encoded=native_encoded(engine._arena,engine._cars,ordered)
            for index in (0,len(ordered)-1):
                ours=ordered[index];previous=rng.uniform(-1,1,8).astype(np.float32)
                actual=planner._views([encoded],[previous],index)[0]
                expected=planner.observation(s,{ours:previous},ours)
                for a,b in zip(actual,expected):np.testing.assert_allclose(a,b,atol=2e-6,rtol=0)
    finally:planner.close();engine.close()

@pytest.mark.parametrize('players',[2,4,6])
def test_native_held_control_edges_match_tick_by_tick_physics(players):
    from rlgym.rocket_league.sim import RocketSimEngine
    engine=RocketSimEngine(rlbot_delay=False)
    initial=state_fixture(players);ids=list(initial.cars);ours=ids[0]
    # Put cars near the ball to exercise collisions, not just empty-arena motion.
    for i,car in enumerate(initial.cars.values()):
        car.physics.position=np.array([-160+90*i,-120+40*i,17],np.float32)
        car.physics.euler_angles=np.array([0,.4*i,0],np.float32)
    state=engine.set_state(initial,{})
    # Match collision graphs as well as exposed state. Independently created
    # arenas can order overlapping contacts differently even when both use the
    # ordinary tick loop; cloning both isolates the held-control optimization.
    raw=engine._arena.clone(False);reference=engine._arena.clone(False)
    engine._arena=reference
    engine._cars={aid:reference.get_car_from_id(car.id) for aid,car in engine._cars.items()}
    cars={aid:raw.get_car_from_id(car.id) for aid,car in engine._cars.items()}
    branch={'arena':raw,'cars':cars,'last':None}
    fixed={aid:np.array([1,.3 if i%2 else -.3,0,0,0,0,i%2,0],np.float32) for i,aid in enumerate(ids)}
    for aid in ids:
        if aid!=ours:cars[aid].set_controls(controls(fixed[aid]))
    try:
        for step in range(30):
            command=np.tile(fixed[ours],(8,1))
            if step%5==1:command[1:5,5]=1;command[1:5,2]=-1
            if step%4==2:command[3:,1]=1;command[5:,7]=1
            actions={aid:np.tile(v,(8,1)) for aid,v in fixed.items()};actions[ours]=command
            state=engine.step(actions,{})
            calls=advance_batch([branch],ours,command[None])
            assert 1<=calls<=8
            np.testing.assert_allclose(raw.ball.get_state().pos.as_numpy(),state.ball.position,atol=1e-4,rtol=0)
            np.testing.assert_allclose(raw.ball.get_state().vel.as_numpy(),state.ball.linear_velocity,atol=1e-4,rtol=0)
            for aid,c in state.cars.items():
                native=cars[aid].get_state()
                np.testing.assert_allclose(native.pos.as_numpy(),c.physics.position,atol=1e-4,rtol=0)
                np.testing.assert_allclose(native.vel.as_numpy(),c.physics.linear_velocity,atol=1e-4,rtol=0)
                assert tuple(native.wheels_with_contact)==tuple(c.wheels_with_contact)
                assert native.has_flipped==c.has_flipped and native.has_double_jumped==c.has_double_jumped
    finally:engine.close()

@pytest.mark.parametrize('goal',[False,True])
@pytest.mark.parametrize('players,orange',[(2,False),(4,True),(6,False)])
@pytest.mark.parametrize('workers,stepping,network',[(1,'compact','original'),(1,'workers','original'),
    (2,'workers','original'),(1,'multi_step','original'),(1,'compact','optimized'),(1,'compact','frozen'),
    (1,'processes','frozen'),(2,'processes','frozen')])
def test_native_search_matches_reference_scores_and_survives_repeated_calls(model_book,goal,players,orange,workers,stepping,network):
    model,book=model_book;state=state_fixture(players)
    ours=next(aid for aid,car in state.cars.items() if car.is_orange==orange)
    if goal:
        state.ball.position=np.array([0,5050,100],np.float32);state.ball.linear_velocity=np.array([0,1500,0],np.float32)
    before=copy.deepcopy(state);previous={aid:np.zeros(8,np.float32) for aid in state.cars}
    reference=RuntimePlanner(model,book,candidates=8)
    native=NativeBatchPlanner(model,book,candidates=8,workers=workers,stepping=stepping,network=network)
    try:
        expected,report=reference.choose(state,previous,ours)
        for _ in range(2):
            actual,result=native.choose(state,previous,ours)
            assert result['backend']=='native-'+stepping and result['candidates']==8
            assert result['horizon_seconds']==1. and result['execute_first_ticks']==8
            assert result['selected']['token']==report['selected']['token']
            np.testing.assert_array_equal(actual,expected)
            for x,y in zip(report['records'],result['records']):
                assert x['token']==y['token']
                for key in ('score','value','uncertainty'):assert x[key]==pytest.approx(y[key],abs=3e-5)
        np.testing.assert_array_equal(state.ball.position,before.ball.position)
    finally:reference.close();native.close()


def test_native_benchmark_loads_checkpoint_compares_forecasts_and_preserves_training(tmp_path,model_book,monkeypatch):
    from pathlib import Path
    from slater_v041_core import sha256,atomic_json
    model,book=model_book
    torch.save({'config':model.config,'model':model.state_dict()},tmp_path/'best.pt')
    np.save(tmp_path/'tokens.npy',book)
    atomic_json(tmp_path/'selected.json',{'sha256':sha256(tmp_path/'best.pt')})
    atomic_json(tmp_path/'tokenizer.json',{'book_sha256':sha256(tmp_path/'tokens.npy')})
    root=Path(__file__).resolve().parents[1]
    paths=list((root/'replay_il').glob('*.py'))+list(tmp_path.iterdir())
    before={path:sha256(path) for path in paths}
    original_choose=NativeBatchPlanner.choose
    def reordered_choose(self,*args,**kwargs):
        actions,report=original_choose(self,*args,**kwargs)
        if self.network=='frozen':report['records']=list(reversed(report['records']))
        return actions,report
    monkeypatch.setattr(NativeBatchPlanner,'choose',reordered_choose)
    report=benchmark(tmp_path,device='cpu',candidate_counts=[2],repeats=2,warmups=1,
                     network='frozen',compare_native=True)
    assert report['checkpoint_sha256']==before[tmp_path/'best.pt']
    assert {r['backend'] for r in report['results']}=={'policy','reference','native-compact-original','native-compact-frozen'}
    assert report['comparisons'][0]['parity']['same_selected_token']
    assert report['comparisons'][0]['parity']['candidate_order_changed']
    assert report['validation_status']=='passed'
    assert report['comparisons'][0]['median_speedup']>0
    recommended=report['recommended_backend_by_candidates']['2']
    searches=[row for row in report['results'] if row['mode']=='search']
    assert recommended['p95_ms']==min(row['latency_p95_ms'] for row in searches)
    assert recommended['backend'] in {'reference','native-compact-original','native-compact-frozen'}
    for row in report['results']:
        assert len(row['latency_samples_ms'])==2 and row['first_call_ms']>0
        assert row['latency_p95_ms']>=row['latency_median_ms']>0
        assert row['meets_deadline_p95']==(row['latency_p95_ms']<=row['deadline_ms'])
    assert {path:sha256(path) for path in paths}==before


def test_forecast_comparison_rejects_changed_actions_and_scores():
    reference={'candidates':1,'selected':{'token':1},'records':[{'token':1,'score':.1,'value':.2,'uncertainty':.3}]}
    assert compare_records(reference,reference)['maximum_absolute_error']==0
    for field,value in [('score',.4),('value',float('nan'))]:
        changed=copy.deepcopy(reference);changed['records'][0][field]=value
        with pytest.raises(ValueError,match='parity failed'):compare_records(reference,changed)
    changed=copy.deepcopy(reference);changed['selected']['token']=2
    with pytest.raises(ValueError,match='parity failed'):compare_records(reference,changed)


def test_comparison_matches_tokens_and_rejects_set_changes_duplicates_and_changed_selection():
    from replay_il_native_runtime import ForecastParityError
    reference={'candidates':2,'selected':{'token':7},'records':[
        {'token':7,'score':.9,'value':.8,'uncertainty':.1},
        {'token':3,'score':.2,'value':.4,'uncertainty':.2}]}
    reordered=copy.deepcopy(reference);reordered['records'].reverse()
    parity=compare_records(reference,reordered)
    assert parity['same_candidate_set'] and parity['candidate_order_changed']
    assert parity['matched_candidates']==2 and parity['maximum_absolute_error']==0
    changed=copy.deepcopy(reordered);changed['records'][0]['value']+=.1
    with pytest.raises(ForecastParityError) as error:compare_records(reference,changed)
    assert error.value.details['worst_difference']['token']==3
    assert error.value.details['worst_difference']['field']=='value'
    changed=copy.deepcopy(reordered);changed['records'][0]['token']=11
    with pytest.raises(ForecastParityError,match='sets differ') as error:compare_records(reference,changed)
    assert error.value.details['reference_only_tokens']==[3]
    assert error.value.details['native_only_tokens']==[11]
    changed=copy.deepcopy(reordered);changed['records'][0]['token']=7
    with pytest.raises(ForecastParityError,match='duplicate'):compare_records(reference,changed)
    changed=copy.deepcopy(reordered);changed['selected']['token']=3
    with pytest.raises(ForecastParityError) as error:compare_records(reference,changed)
    assert not error.value.details['same_selected_token']
    changed=copy.deepcopy(reordered);changed['records'].pop()
    with pytest.raises(ForecastParityError,match='counts differ'):compare_records(reference,changed)


def test_failed_comparison_keeps_results_saves_report_and_excludes_failed_backend(tmp_path,model_book,monkeypatch):
    import json
    import replay_il_native_runtime as runtime
    from slater_v041_core import sha256,atomic_json
    model,book=model_book
    torch.save({'config':model.config,'model':model.state_dict()},tmp_path/'best.pt')
    np.save(tmp_path/'tokens.npy',book)
    atomic_json(tmp_path/'selected.json',{'sha256':sha256(tmp_path/'best.pt')})
    atomic_json(tmp_path/'tokenizer.json',{'book_sha256':sha256(tmp_path/'tokens.npy')})
    original_choose=NativeBatchPlanner.choose
    def changed_choose(self,*args,**kwargs):
        actions,report=original_choose(self,*args,**kwargs)
        if self.network=='frozen':report['records'][0]['value']+=.25
        return actions,report
    monkeypatch.setattr(NativeBatchPlanner,'choose',changed_choose)
    report=benchmark(tmp_path,device='cpu',candidate_counts=[2],repeats=1,warmups=1,
                     network='frozen',compare_native=True,compare_reference=False)
    assert report['validation_status']=='failed'
    failure=report['comparisons'][0]
    assert failure['status']=='failed' and len(failure['native_records'])==len(failure['reference_records'])==2
    assert report['recommended_backend_by_candidates']['2']['backend']=='native-compact-original'
    assert len(report['results'])==3 and all(row['latency_median_ms']>0 for row in report['results'])
    monkeypatch.setattr(runtime,'benchmark',lambda *args,**kwargs:report)
    monkeypatch.setattr(runtime,'__file__',str(tmp_path/'replay_il_native_runtime.py'))
    with pytest.raises(ValueError,match='were saved'):runtime.main(['--run','failure_report'])
    output=tmp_path/'data/isolated/replay_imitation/runs/failure_report/native_runtime_v2_benchmark.json'
    saved=json.loads(output.read_text())
    assert saved['validation_status']=='failed' and saved['results']==report['results']
    assert saved['comparisons']==report['comparisons']


@pytest.mark.parametrize('count',[1,7,9,24,31,32])
def test_cached_controls_preserve_partial_chunks_and_button_edges(model_book,count):
    from rlgym.rocket_league.sim import RocketSimEngine
    _,book=model_book;initial=state_fixture();ordered=list(initial.cars);ours=ordered[0]
    engines=[RocketSimEngine(rlbot_delay=False) for _ in range(2)];branches=[]
    try:
        for engine in engines:
            engine.set_state(initial,{})
            branches.append({'arena':engine._arena,'cars':engine._cars,'last':None,'token':0,'tick':0,'goal':None})
        original,_=advance_branch(branches[0],ours,book,count,ordered,1)
        cached,_=advance_branch(branches[1],ours,book,count,ordered,1,compile_controls(book))
        assert branches[0]['tick']==branches[1]['tick']==count
        assert len(original)==len(cached)==(count+7)//8
        for (_,a,old),(_,b,new) in zip(original,cached):
            np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(old,new)
        assert branches[0]['goal']==branches[1]['goal']
    finally:
        for engine in engines:engine.close()
