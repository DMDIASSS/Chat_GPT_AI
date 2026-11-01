"""Inference algebra, feature storage and real forecast parity; no training edits."""
import copy
import numpy as np
import pytest
import torch
from replay_il_inference import InferenceKernel,freeze_kernel
from replay_il_turbo import TurboKernel,FeatureStep,GraphFeatures,pack_observations,unpack_observations
from replay_il_snapshot import quaternion,encoded
from replay_il_forecast import native_encoded
from replay_il_native_runtime import NativeBatchPlanner,compare_records
from test_replay_runtime import model_book,state_fixture
from vendor.nexto.nexto_obs import rotation_to_quaternion


@pytest.mark.parametrize('batch,history',[(1,1),(3,4),(16,8),(64,8)])
@pytest.mark.parametrize('frozen',[False,True])
def test_turbo_causal_attention_and_packed_values_preserve_model(model_book,batch,history,frozen):
    model,_=model_book;before={k:v.clone() for k,v in model.state_dict().items()}
    kernel=TurboKernel(model);kernel=freeze_kernel(kernel) if frozen else kernel
    reference=InferenceKernel(model);generator=torch.Generator().manual_seed(52+batch)
    features=torch.randn(batch,history,128,generator=generator)
    observations=(torch.randn(batch,1,32,generator=generator),torch.randn(batch,41,24,generator=generator),torch.zeros(batch,41))
    observations[2][:,2:6]=-10000
    with torch.inference_mode():
        torch.testing.assert_close(kernel.encode(observations),model.encoder(observations),atol=3e-6,rtol=3e-6)
        for actual,expected in zip(kernel.decode(features),reference.decode(features)):
            torch.testing.assert_close(actual,expected,atol=3e-6,rtol=3e-6)
    for k,v in model.state_dict().items():torch.testing.assert_close(v,before[k],atol=0,rtol=0)


def test_packed_transfer_and_feature_step_update_dynamic_bank_slots(model_book):
    model,_=model_book;rng=np.random.default_rng(21)
    views=[(rng.normal(size=(1,32)).astype(np.float32),rng.normal(size=(41,24)).astype(np.float32),np.zeros(41,np.float32)) for _ in range(9)]
    packed=pack_observations(views)
    for actual,expected in zip(unpack_observations(torch.from_numpy(packed)),zip(*views)):
        np.testing.assert_array_equal(actual.numpy(),np.stack(expected))
    with torch.inference_mode():
        kernel=freeze_kernel(TurboKernel(model));bank=torch.zeros(50,128)
        for count,batch,offset in [(9,2,0),(3,3,20),(0,2,23)]:
            step=FeatureStep(kernel,bank,count,batch,8)
            history_indices=np.resize(np.arange(max(count,1))+offset,(batch,8)) if count else np.resize(np.arange(9),(batch,8))
            observations=pack_observations(views[:count])
            data=np.concatenate((observations,np.arange(offset,offset+count),history_indices.reshape(-1))).astype(np.float32)
            actual=step(torch.from_numpy(data))
            if count:
                expected_features=kernel.encode(unpack_observations(torch.from_numpy(observations)))
                torch.testing.assert_close(bank[offset:offset+count],expected_features,atol=0,rtol=0)
            for a,b in zip(actual,kernel.decode(bank[torch.from_numpy(history_indices)])):
                torch.testing.assert_close(a,b,atol=0,rtol=0)


def test_snapshot_scalar_quaternions_preserve_all_branch_choices():
    rng=np.random.default_rng(44)
    rotations=[np.eye(3),np.diag([1,-1,-1]),np.diag([-1,1,-1]),np.diag([-1,-1,1])]
    for _ in range(500):
        q,_=np.linalg.qr(rng.normal(size=(3,3)))
        if np.linalg.det(q)<0:q[:,0]*=-1
        rotations.append(q.astype(np.float32))
    for rotation in rotations:
        expected=rotation_to_quaternion(rotation.T.astype(np.float64))
        np.testing.assert_allclose(quaternion(rotation),expected,atol=5e-16,rtol=0)


@pytest.mark.parametrize('players',[2,4,6])
def test_fast_snapshots_keep_demo_ground_pad_and_orientation_contract(players):
    from rlgym.rocket_league.sim import RocketSimEngine
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        for phase in range(6):
            state=state_fixture(players)
            for index,car in enumerate(state.cars.values()):
                car.physics.euler_angles=np.array([phase*.9,index*.7,phase*.63],np.float32)
                car.has_flipped=phase==1;car.has_double_jumped=phase==2
                car.demo_respawn_timer=1.4 if phase==3 else 0.
                car.air_time_since_jump=1.3 if phase==4 else .2
                car.on_ground=phase%2==0
            state.boost_pad_timers[:]=np.resize(np.array([0,1e-6,1.0001e-6,2],np.float32),34)
            engine.set_state(state,{})
            ordered=sorted(state.cars,key=lambda aid:(state.cars[aid].is_orange,str(aid)))
            np.testing.assert_allclose(encoded(engine._arena,engine._cars,ordered),
                native_encoded(engine._arena,engine._cars,ordered),atol=5e-16,rtol=0)
    finally:engine.close()


@pytest.mark.parametrize('players,orange,goal',[(2,False,False),(2,True,True),(4,False,False),(6,True,False)])
@pytest.mark.parametrize('stepping,workers',[('compact',1),('processes',2)])
def test_turbo_full_forecasts_keep_actions_scores_and_repeated_calls(model_book,players,orange,goal,stepping,workers):
    model,book=model_book;state=state_fixture(players);before=copy.deepcopy(state)
    ours=next(a for a,c in state.cars.items() if c.is_orange==orange)
    if goal:state.ball.position=np.array([0,5050,100],np.float32);state.ball.linear_velocity=np.array([0,1500,0],np.float32)
    reference=NativeBatchPlanner(model,book,candidates=8,network='frozen')
    faster=NativeBatchPlanner(model,book,candidates=8,network='turbo',stepping=stepping,workers=workers)
    try:
        expected,report=reference.choose(state,{},ours)
        for _ in range(2):
            actual,result=faster.choose(state,{},ours)
            compare_records(report,result,tolerance=3e-5)
            np.testing.assert_array_equal(actual,expected)
            assert result['horizon_seconds']==1 and result['execute_first_ticks']==8
            assert result['network']=='turbo'
            assert not any(result['worker_torch_loaded'])
        for aid,car in state.cars.items():np.testing.assert_array_equal(car.physics.position,before.cars[aid].physics.position)
    finally:reference.close();faster.close()


def test_cuda_graphs_fail_explicitly_on_cpu_and_do_not_silently_claim_capture(model_book):
    model,book=model_book
    with pytest.raises(ValueError,match='CUDA graphs require'):GraphFeatures(TurboKernel(model),'cpu',100,8)
    with pytest.raises(ValueError,match='CUDA graphs require'):NativeBatchPlanner(model,book,network='cuda-graphs')


def test_graph_feature_indexing_reuses_shapes_and_handles_new_histories_on_cpu(model_book,monkeypatch):
    """Exercise actual bank/packing logic through an eager capture stand-in.

    Hardware capture/replay remains a separate CUDA-required test below.
    """
    from collections import OrderedDict
    import replay_il_turbo as turbo
    model,book=model_book;reference=NativeBatchPlanner(model,book,candidates=2,network='turbo')
    graph=GraphFeatures.__new__(GraphFeatures)
    graph.device=torch.device('cpu');graph.kernel=reference.inference_kernel;graph.capacity=100
    graph.history=8;graph.max_graphs=1;graph.bank=torch.zeros(100,128)
    graph.graphs=OrderedDict();graph.pool=None;graph.features={};graph.count=0
    graph.capture_ms=0.;graph.replays=0;graph.eager_calls=0;graph._allow_capture=False;graph.failure=None
    class EagerCapture:
        def __init__(self,step,example,device,pool):self.step=step
        def __call__(self,packed):return self.step(torch.from_numpy(packed))
    monkeypatch.setattr(turbo,'CapturedStep',EagerCapture)
    state=state_fixture();ours=next(iter(state.cars))
    try:
        for phase in range(2):
            graph.begin(allow_capture=True);reference.begin()
            views=[reference.observation(state,{ours:np.full(8,(i+phase)/20,np.float32)},ours) for i in range(12)]
            for histories in ([views[:4],views[1:5]],[views[:8],views[2:10]],[views[4:12],views[4:12]]):
                for actual,expected in zip(graph.infer(histories),reference.infer_batch(histories)):
                    torch.testing.assert_close(actual,expected,atol=0,rtol=0)
            assert len(graph.graphs)==1
        assert graph.replays==4 and graph.eager_calls==2
    finally:reference.close()


@pytest.mark.parametrize('reject',[False,True])
def test_tuner_checks_extra_rosters_saves_valid_profiles_and_preserves_sources(tmp_path,model_book,monkeypatch,reject):
    from pathlib import Path
    from replay_il_turbo_benchmark import tune
    from slater_v041_core import atomic_json,sha256
    model,book=model_book
    torch.save({'config':model.config,'model':model.state_dict()},tmp_path/'best.pt')
    np.save(tmp_path/'tokens.npy',book)
    atomic_json(tmp_path/'selected.json',{'sha256':sha256(tmp_path/'best.pt')})
    atomic_json(tmp_path/'tokenizer.json',{'book_sha256':sha256(tmp_path/'tokens.npy')})
    root=Path(__file__).resolve().parents[1]
    paths=list((root/'replay_il').glob('*.py'))+list(tmp_path.iterdir());before={p:sha256(p) for p in paths}
    choose=NativeBatchPlanner.choose
    def changed_choose(self,state,*args,**kwargs):
        action,report=choose(self,state,*args,**kwargs)
        if reject and self.network=='turbo' and len(state.cars)==4:report['records'][0]['value']+=.1
        return action,report
    monkeypatch.setattr(NativeBatchPlanner,'choose',changed_choose)
    report=tune(tmp_path,device='cpu',workers=(2,),threads=2,candidate_counts=(2,),repeats=2,warmups=1)
    assert report['validation_status']==('passed_with_rejections' if reject else 'passed')
    assert not report['cuda_graphs_tested']
    assert len(report['comparisons'])==5
    assert {c['scenario'] for c in report['comparisons']}=={'kickoff','early_goal','1v1_moving_orange','2v2_moving_orange','3v3_moving_orange'}
    assert sum(c['status']=='failed' for c in report['comparisons'])==int(reject)
    if reject:
        assert report['rejected_backends']==['turbo-workers2-threads2']
        assert report['recommended_backend_by_candidates']['2']['network']=='frozen'
    assert report['recommended_backend_by_candidates']['2']['backend'] in {r['backend'] for r in report['results']}
    assert {p:sha256(p) for p in paths}==before


@pytest.mark.skipif(not torch.cuda.is_available(),reason='CUDA hardware required for graph capture/replay')
def test_real_cuda_graphs_repeat_with_changed_data_and_irregular_shapes(model_book):
    model,book=model_book;model=copy.deepcopy(model).cuda();state=state_fixture();ours=next(iter(state.cars))
    reference=NativeBatchPlanner(model,book,candidates=8,network='frozen')
    faster=NativeBatchPlanner(model,book,candidates=8,network='cuda-graphs')
    try:
        faster.warmup(state,{},ours)
        for phase in range(3):
            state.cars[ours].physics.position+=np.array([phase*20,0,0],np.float32)
            if phase==2:state.ball.position=np.array([0,5050,100],np.float32);state.ball.linear_velocity=np.array([0,1500,0],np.float32)
            expected,report=reference.choose(state,{},ours);actual,result=faster.choose(state,{},ours)
            compare_records(report,result);np.testing.assert_array_equal(actual,expected)
            assert result['cuda_graphs']['captured_shapes']>0
            assert result['cuda_graphs']['capture_failure'] is None
        assert result['cuda_graphs']['replays']>0 and result['cuda_graphs']['eager_calls']>0
    finally:reference.close();faster.close()
