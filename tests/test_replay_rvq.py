"""Versioned cached-replay RVQ model, optimizer, proposals and forecast checks."""
import copy,json,os,subprocess,sys,shutil,tempfile,uuid
from pathlib import Path
import numpy as np
import pytest
import torch
from replay_rvq.model import ActionCodec,StatePolicy,controls_from_raw,reconstruction_loss
from replay_rvq.inference import freeze
from replay_rvq.data import RVQData,positive_weights,sample_controls
from slater_v041_core import sha256,read_json
from test_replay_imitation import raw_rows,fixture_dataset
from test_replay_runtime import state_fixture
from test_replay_rlbot_export import packet_fixture


def small_config():return {'codec':{'latent':16,'hidden':64,'levels':4,'codes':64},'policy':{'context':32,'hidden':64}}


def test_current_state_model_and_sequential_proposals_are_physical_and_distinct():
    torch.set_num_threads(2);torch.manual_seed(7);config=small_config()
    model=StatePolicy(ActionCodec(**config['codec']),**config['policy']).eval()
    obs=(torch.randn(3,1,32),torch.randn(3,41,24),torch.zeros(3,41))
    with torch.inference_mode():
        features=model.encode(obs);actions,codes,logp=model.propose(features)
        changed=tuple(item.clone() for item in obs);changed[0][...,24:]=torch.randn_like(changed[0][...,24:])
        torch.testing.assert_close(model.encode(changed),features)
        assert actions.shape==(3,64,32,8) and codes.shape==(3,64,4)
        assert torch.isfinite(actions).all() and actions.abs().max()<=1
        assert torch.isin(actions[...,5:],torch.tensor([0.,1.])).all()
        assert ((logp[:,1:]-logp[:,:-1])<=0).all()
        assert len(torch.unique(codes[0],dim=0))==64
        altered=codes[:1,0].clone();before=model.teacher_logits(features[:1],altered)
        altered[:,0]=(altered[:,0]+1)%64;after=model.teacher_logits(features[:1],altered)
        torch.testing.assert_close(before[:,0],after[:,0])
        assert not torch.allclose(before[:,1],after[:,1])


def test_learned_codec_preserves_boolean_buttons_and_receives_training_gradients():
    torch.set_num_threads(2);torch.manual_seed(8);model=ActionCodec(latent=16,hidden=64)
    targets=torch.zeros(32,32,8);targets[:,:,0]=torch.linspace(-1,1,32)[:,None]
    targets[::4,2:5,5]=1;targets[::3,:,6]=1
    weights=torch.tensor(positive_weights(targets.numpy()));model.initialize(targets)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.003)
    with torch.no_grad():before=float(reconstruction_loss(model(targets)[0],targets,weights))
    initial=model.codebooks.detach().clone()
    for _ in range(30):
        raw,codes,vq=model(targets);loss=reconstruction_loss(raw,targets,weights)+.1*vq
        optimizer.zero_grad();loss.backward();optimizer.step()
    with torch.no_grad():raw,codes,vq=model(targets);after=float(reconstruction_loss(raw,targets,weights))
    assert after<before and not torch.equal(initial,model.codebooks)
    assert codes.shape==(32,4) and torch.isin(controls_from_raw(raw)[...,5:],torch.tensor([0.,1.])).all()
    assert model.encoder[1].weight.grad.abs().sum()>0 and model.decoder[0].weight.grad.abs().sum()>0


def test_button_calibration_handles_ties_and_never_uses_unseen_positive_labels():
    from replay_rvq.model import calibrate_buttons
    raw=torch.zeros(2,32,8);targets=torch.zeros_like(raw)
    raw[:,:,5]=-1;raw[0,:4,5]=2;targets[0,:4,5]=1
    raw[:,:,6]=3 # No observed boost positives: retain the default threshold.
    thresholds=calibrate_buttons(raw,targets)
    assert thresholds[1]==0 and thresholds[2]==0
    prediction=controls_from_raw(raw,thresholds)
    torch.testing.assert_close(prediction[:,:8,5],targets[:,:8,5])


def test_frozen_codec_policy_matches_eager_for_dynamic_batches_and_proposals(tmp_path):
    torch.set_num_threads(2);torch.manual_seed(9);config=small_config()
    model=StatePolicy(ActionCodec(**config['codec']),**config['policy']).eval();kernel=freeze(model)
    path=tmp_path/'policy.pt';torch.jit.save(kernel,str(path));kernel=torch.jit.load(str(path)).eval()
    for batch in (1,3):
        obs=(torch.randn(batch,1,32),torch.randn(batch,41,24),torch.zeros(batch,41))
        with torch.inference_mode():
            expected=model.encode(obs);actual=kernel.encode(obs)
            torch.testing.assert_close(expected,actual,atol=3e-5,rtol=3e-5)
            for function in ('greedy','propose','value'):
                a=getattr(model,function)(expected);b=getattr(kernel,function)(actual)
                for first,second in zip(a,b) if isinstance(a,tuple) else [(a,b)]:
                    torch.testing.assert_close(first,second,atol=3e-5,rtol=3e-5)


def test_rvq_stages_train_save_resume_without_simulation_or_changing_old_data(tmp_path,raw_rows,monkeypatch):
    import replay_rvq.train as training
    from rlgym.rocket_league.sim import RocketSimEngine
    monkeypatch.setattr(training,'ROOT',tmp_path);monkeypatch.setattr(training,'source_identity',lambda:{'test':'fixed'})
    dataset=fixture_dataset(tmp_path/'dataset',raw_rows)
    protected={path:sha256(path) for path in dataset.iterdir()}
    root=tmp_path/'data/isolated/rvq_test';config=small_config()
    monkeypatch.setattr(RocketSimEngine,'__init__',lambda *a,**k:pytest.fail('Supervised training attempted to create a simulation'))
    training.train(dataset,root,codec_epochs=2,policy_epochs=1,device='cpu',batch_size=8,wandb_mode='disabled',config=config)
    assert read_json(root/'codec/progress.json')['updates']>0
    first=read_json(root/'policy/progress.json');assert first['updates']>0 and first['epoch']==1
    before=sha256(root/'policy/latest.pt')
    training.train(dataset,root,codec_epochs=2,policy_epochs=1,device='cpu',batch_size=8,wandb_mode='disabled',config=config)
    assert sha256(root/'policy/latest.pt')==before
    training.train(dataset,root,codec_epochs=2,policy_epochs=2,device='cpu',batch_size=8,wandb_mode='disabled',config=config)
    assert read_json(root/'policy/progress.json')['updates']>first['updates']
    assert {path:sha256(path) for path in protected}==protected
    assert not list(dataset.glob('*.npy')) and list((root/'labels').glob('*.npy'))
    report=read_json(root/'policy/epoch_0001.json')
    assert report['parameter_change_l2']>0 and report['rl_updates']==0 and report['self_play_games']==0
    with pytest.raises(ValueError,match='Codec is frozen'):
        training.train(dataset,root,codec_epochs=3,policy_epochs=2,device='cpu',batch_size=8,wandb_mode='disabled',config=config)


def test_safe_pause_saves_a_partial_codec_epoch_and_resume_reuses_it(tmp_path,raw_rows,monkeypatch):
    import replay_rvq.train as training
    monkeypatch.setattr(training,'ROOT',tmp_path);monkeypatch.setattr(training,'source_identity',lambda:{'test':'fixed'})
    dataset=fixture_dataset(tmp_path/'dataset',raw_rows);root=tmp_path/'data/isolated/rvq_pause'
    original=RVQData.take_controls;seen={'training':0}
    def take(self,rows,device):
        result=original(self,rows,device)
        if all(self.raw.records[r]['split']=='train' for r,_ in rows):
            seen['training']+=1
            if seen['training']==1:(root/'pause.flag').touch()
        return result
    monkeypatch.setattr(RVQData,'take_controls',take)
    training.train(dataset,root,codec_epochs=2,policy_epochs=1,device='cpu',batch_size=8,wandb_mode='disabled',config=small_config())
    paused=read_json(root/'codec/progress.json')
    assert paused['epoch']==0 and paused['updates']==1 and not (root/'policy').exists()
    assert read_json(root/'codec/epoch_0001.json')['paused_mid_epoch']
    monkeypatch.setattr(RVQData,'take_controls',original)
    training.train(dataset,root,codec_epochs=2,policy_epochs=1,device='cpu',batch_size=8,wandb_mode='disabled',config=small_config())
    assert read_json(root/'codec/progress.json')['updates']>1 and (root/'policy/latest.pt').is_file()


def test_search_repredicts_every_car_and_preserves_input_state():
    from replay_rvq.search import Search
    class Kernel:
        def eval(self):return self
        def encode(self,obs):return torch.zeros(len(obs[0]),4)
        def greedy(self,features):
            controls=torch.zeros(len(features),32,8);controls[:,:,0]=1;controls[:,:,6]=1
            return controls,torch.zeros(len(features),4,dtype=torch.long),torch.zeros(len(features))
        def propose(self,features):
            controls=torch.zeros(len(features),64,32,8);controls[:,:,:,0]=1
            return controls,torch.zeros(len(features),64,4,dtype=torch.long),torch.zeros(len(features),64)
        def value(self,features):return torch.zeros(len(features),3)
    state=state_fixture(4);ours=next(iter(state.cars));previous={aid:np.zeros(8,np.float32) for aid in state.cars}
    original={aid:car.physics.position.copy() for aid,car in state.cars.items()}
    planner=Search(Kernel(),candidates=2)
    try:controls,report=planner.choose(state,previous,ours)
    finally:planner.close()
    assert report['policy_car_predictions']==4+3*2*4 and report['horizon_ticks']==128
    assert report['candidates']==2 and controls.shape==(32,8)
    assert len(report['records'])==2 and report['ranking'].startswith('mean learned value only')
    for aid,position in original.items():np.testing.assert_array_equal(state.cars[aid].physics.position,position)


@pytest.mark.parametrize('players',[2,4,6])
def test_standalone_forecast_features_and_packet_state_match_training(players):
    from afk_team_research import TeamObserver
    from replay_rvq.packet import StateObserver,PacketState
    from replay_rlbot_core import PacketObserver
    from rlgym.rocket_league.sim import RocketSimEngine
    state=state_fixture(players)
    for i,car in enumerate(state.cars.values()):
        car.physics.euler_angles=np.array([.1*i,.2*i,-.05*i],np.float32);car.boost_amount=20+i
    state.boost_pad_timers[::3]=2.
    previous={aid:np.array([1,.2,0,0,0,0,1,0],np.float32) for aid in state.cars}
    expected=TeamObserver().observe(state,previous);actual=StateObserver().observe(state,previous)
    for aid in state.cars:
        for a,b in zip(actual[aid],expected[aid]):np.testing.assert_allclose(a,b,atol=2e-6,rtol=0)
    packet,field=packet_fixture(state);packet_observer=PacketObserver(field);adapter=PacketState(packet_observer)
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        inferred=adapter.from_packet(packet,0,previous[next(iter(state.cars))],engine)
        view=StateObserver().observe(inferred,{0:previous[next(iter(state.cars))]})[0]
        direct=packet_observer.observe(packet,0,previous[next(iter(state.cars))])
        for a,b in zip(view[:2],direct[:2]):np.testing.assert_allclose(a,b,atol=2e-6,rtol=0)
        np.testing.assert_array_equal(np.where(view[2]>0,-10000.,view[2]),direct[2])
        # It must also be a valid physical forecast state, not merely a feature array.
        engine.set_state(inferred,{})
        stepped=engine.step({aid:np.zeros((8,8),np.float32) for aid in inferred.cars},{})
        assert np.isfinite(stepped.ball.position).all()
    finally:engine.close()


def test_rvq_export_search_runs_in_an_isolated_folder_without_training_project(tmp_path):
    from replay_rvq.export import export
    from slater_v041_core import atomic_json
    root=tmp_path/'source';(root/'policy').mkdir(parents=True)
    config=small_config();model=StatePolicy(ActionCodec(**config['codec']),**config['policy']).eval()
    atomic_json(root/'protocol.json',{'provenance':'ENGINEERING_RANDOM_MODEL_NOT_USER_WEIGHTS'})
    torch.save({'schema':'replay-rvq-stage-v1','stage':'policy','config':config,'model':model.state_dict(),
        'protocol_sha256':sha256(root/'protocol.json')},root/'policy/best.pt')
    atomic_json(root/'policy/selected.json',{'sha256':sha256(root/'policy/best.pt')})
    before=sha256(root/'policy/best.pt');target=export(root,'RVQFixture',tmp_path/'exports')
    packet,field=packet_fixture(state_fixture())
    from types import SimpleNamespace
    payload=json.dumps({'packet':packet,'field':field},default=lambda value:value.item() if isinstance(value,np.generic) else vars(value))
    (target/'fixture.json').write_text(payload)
    script='''
import sys,json
from pathlib import Path
from types import SimpleNamespace as NS,ModuleType
base=ModuleType('rlbot.agents.base_agent');base.BaseAgent=type('BaseAgent',(),{});base.SimpleControllerState=lambda **kwargs:NS(**kwargs)
for name in ('rlbot','rlbot.agents'):sys.modules[name]=ModuleType(name)
sys.modules['rlbot.agents.base_agent']=base
from bot import ReplayRVQBot
data=json.loads(Path('fixture.json').read_text(),object_hook=lambda row:NS(**row))
agent=ReplayRVQBot();agent.index=0;agent.get_field_info=lambda:data.field;agent.initialize_agent()
assert agent.controller.mode=='search'
result=agent.get_output(data.packet)
assert not agent.error and -1<=result.throttle<=1
assert agent.controller.asynchronous and agent.controller.pending is not None
agent.controller.pending.result(timeout=10)
data.packet.game_info.seconds_elapsed+=1/120
agent.last_log=None
agent.get_output(data.packet)
assert agent.controller.last_report['opponents'].startswith('all other cars')
assert agent.controller.decisions==2 and Path('RVQ_DIAGNOSTICS.json').is_file()
assert Path('RVQ_DIAGNOSTICS_0.json').is_file()
report=json.loads(Path('RVQ_DIAGNOSTICS_0.json').read_text())
assert len(report['motion']['issued_action'])==8 and report['motion']['recent_trace']
original=agent.controller.output
def fail(*args):raise ValueError('injected diagnostic check')
agent.controller.output=fail;agent.last_log=None
stopped=agent.get_output(data.packet)
report=json.loads(Path('RVQ_DIAGNOSTICS_0.json').read_text())
assert stopped.throttle==0 and report['runtime_error_active']
assert report['last_runtime_error']['message']=='injected diagnostic check'
agent.controller.output=original;agent.last_log=None
agent.get_output(data.packet)
report=json.loads(Path('RVQ_DIAGNOSTICS_0.json').read_text())
assert not report['runtime_error_active'] and report['last_runtime_error']['message']=='injected diagnostic check'
assert 'replay_rvq' not in sys.modules and 'replay_il' not in sys.modules
agent.retire()
print('SELF_CONTAINED_RVQ_SEARCH_OK')
'''
    env=os.environ.copy();env['PYTHONPATH']=''
    result=subprocess.run([sys.executable,'-c',script],cwd=target,env=env,capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'SELF_CONTAINED_RVQ_SEARCH_OK' in result.stdout
    assert sha256(root/'policy/best.pt')==before


def test_production_cli_trains_default_architecture_from_an_existing_fixture_cache(raw_rows):
    from replay_rvq.train import ROOT
    base=ROOT/'data/isolated/replay_debug';base.mkdir(parents=True,exist_ok=True)
    run='rvq_cli_test_'+uuid.uuid4().hex[:10];folder=ROOT/'data/isolated/replay_imitation/rvq_runs'/run
    try:
        with tempfile.TemporaryDirectory(prefix='rvq_cli_',dir=base) as temporary:
            dataset=fixture_dataset(Path(temporary)/'dataset',raw_rows)
            before=sha256(dataset/'manifest.json')
            command=[sys.executable,'-u','-m','replay_rvq','start','--run',run,'--dataset',str(dataset),
                '--codec-epochs','2','--policy-epochs','1','--batch-size','8','--device','cpu','--wandb-mode','disabled']
            result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=60)
            assert result.returncode==0,result.stdout+result.stderr
            assert read_json(folder/'policy/model.json')['parameters']==3_074_595
            assert read_json(folder/'policy/progress.json')['updates']>0
            assert read_json(folder/'codec/button_calibration.json')['split']=='validation'
            assert sha256(dataset/'manifest.json')==before
            checkpoint=sha256(folder/'policy/latest.pt')
            result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=60)
            assert result.returncode==0,result.stdout+result.stderr
            assert sha256(folder/'policy/latest.pt')==checkpoint
    finally:shutil.rmtree(folder,ignore_errors=True)


def test_inference_refuses_changed_model_interpretation_before_loading_weights(tmp_path):
    from replay_rvq.inference import load
    from slater_v041_core import atomic_json
    (tmp_path/'policy').mkdir();(tmp_path/'policy/best.pt').write_bytes(b'not a checkpoint')
    atomic_json(tmp_path/'policy/selected.json',{'sha256':sha256(tmp_path/'policy/best.pt')})
    atomic_json(tmp_path/'protocol.json',{'code':{'replay_rvq/model.py':'0'*64}})
    with pytest.raises(ValueError,match='Model interpretation source changed'):load(tmp_path)


@pytest.mark.parametrize('throttle,expected',[(0.,'stationary_with_low_drive_commands'),(1.,'stationary_with_drive_commands')])
def test_motion_audit_distinguishes_idle_choices_from_issued_drive_and_retains_episode(throttle,expected):
    from replay_rvq.diagnostics import MotionAudit
    packet,_=packet_fixture(state_fixture());packet.game_info.is_round_active=True
    velocity=packet.game_cars[0].physics.velocity;velocity.x=velocity.y=velocity.z=0.
    audit=MotionAudit();action=np.zeros(8,np.float32);action[0]=throttle;original=action.copy()
    for i in range(31):
        packet.game_info.seconds_elapsed=i/10
        report=audit.observe(packet,0,action,decisions=i,source='search')
    assert report['status']==expected and report['stationary_seconds']==3
    assert report['decisions_in_recent_window']>0
    np.testing.assert_array_equal(action,original)
    packet.game_info.seconds_elapsed=3.1;velocity.x=500
    report=audit.observe(packet,0,action,decisions=32,source='search')
    assert report['status']=='moving_or_brief_wait' and report['last_stationary_episode']['status']==expected
    packet.game_info.seconds_elapsed=0
    report=audit.observe(packet,0,action,decisions=33,source='neutral',error={'message':'test error'})
    assert report['status']=='runtime_error' and report['stationary_seconds']==0
    action[5]=1
    report=audit.observe(packet,0,action,decisions=34,source='policy')
    assert report['button_edges']['jump']=={'press':1,'release':0}
    action[5]=0
    report=audit.observe(packet,0,action,decisions=35,source='policy')
    assert report['button_edges']['jump']=={'press':1,'release':1}
    packet.game_info.is_round_active=False
    report=audit.observe(packet,0,action,decisions=35,source='neutral',neutral_reason='round_inactive')
    assert report['last_inactive_trace'] and report['status']=='inactive_or_demolished'


def test_runtime_replanning_an_idle_prefix_is_reported_without_forcing_movement():
    from replay_rvq.runtime import Controller
    class Kernel:
        def encode(self,observations):return torch.zeros(len(observations[0]),4)
        def greedy(self,features):
            sequence=torch.zeros(len(features),32,8);sequence[:,8:,0]=1
            return sequence,torch.zeros(len(features),4,dtype=torch.long),torch.zeros(len(features))
    packet,field=packet_fixture(state_fixture());packet.game_info.is_round_active=True
    controller=Controller(Kernel(),field,mode='policy',scripted_kickoff=False)
    try:
        for tick in range(40):
            packet.game_info.seconds_elapsed=tick/120
            np.testing.assert_array_equal(controller.output(packet,0),np.zeros(8))
        assert controller.decisions==5
        assert controller.last_report['chosen_chunk']['drive_only_after_executed_prefix']
        assert controller.last_report['chosen_chunk']['unexecuted_last24']['throttle_abs_max']==1
        packet.game_info.is_round_active=False
        controller.output(packet,0)
        assert controller.neutral_reason=='round_inactive'
    finally:controller.close()


@pytest.mark.parametrize('orange',[False,True])
@pytest.mark.parametrize('goal_y_sign',[-1,1])
def test_search_terminal_goal_scores_are_oriented_to_the_controlled_team(orange,goal_y_sign):
    from replay_rvq.search import Search
    class Kernel:
        def eval(self):return self
        def encode(self,observations):return torch.zeros(len(observations[0]),4)
        def greedy(self,features):
            return torch.zeros(len(features),32,8),torch.zeros(len(features),4,dtype=torch.long),torch.zeros(len(features))
        def propose(self,features):
            return torch.zeros(len(features),64,32,8),torch.zeros(len(features),64,4,dtype=torch.long),torch.zeros(len(features),64)
        def value(self,features):return torch.zeros(len(features),3)
    state=state_fixture();ours=next(aid for aid,car in state.cars.items() if car.is_orange==orange)
    state.ball.position=np.array([0,goal_y_sign*5100,100],np.float32)
    state.ball.linear_velocity=np.array([0,goal_y_sign*1500,0],np.float32)
    planner=Search(Kernel(),candidates=1)
    try:_,report=planner.choose(state,{},ours)
    finally:planner.close()
    expected=1. if goal_y_sign==(-1 if orange else 1) else -1.
    assert report['selected']['value']==expected


class ManualSearchExecutor:
    """A deliberately unfinished worker: the control path must never wait."""
    def __init__(self,**kwargs):self.jobs=[]
    def submit(self,function,*args):
        from concurrent.futures import Future
        future=Future();future.set_running_or_notify_cancel();self.jobs.append((future,function,args));return future
    def shutdown(self,**kwargs):pass


def asynchronous_fixture(monkeypatch):
    import replay_rvq.runtime as runtime
    monkeypatch.setattr(runtime,'ThreadPoolExecutor',ManualSearchExecutor)
    class Kernel:
        def eval(self):return self
        def encode(self,obs):return torch.zeros(len(obs[0]),4)
        def greedy(self,features):
            sequence=torch.zeros(len(features),32,8);sequence[:,:,0]=.5;sequence[:,2:4,5]=1
            return sequence,torch.zeros(len(features),4,dtype=torch.long),torch.zeros(len(features))
    packet,field=packet_fixture(state_fixture());packet.game_info.is_round_active=True
    controller=runtime.Controller(Kernel(),field,scripted_kickoff=False)
    return controller,packet


def test_background_search_does_not_block_jump_edges_and_keeps_comparing_candidates(monkeypatch):
    controller,packet=asynchronous_fixture(monkeypatch)
    try:
        actions=[]
        for tick in range(12):
            packet.game_info.seconds_elapsed=tick/120;actions.append(controller.output(packet,0))
        assert [i for i,action in enumerate(actions) if action[5]]==[2,3]
        assert len(controller.executor.jobs)==1 and controller.bootstrap_decisions==1
        assert controller.contingency_frames==4
        sequence=np.zeros((32,8),np.float32);sequence[:,0]=1;sequence[2:4,5]=1
        controller.pending.set_result((sequence,{'latency_ms':100.,'candidates':4}))
        for tick in range(12,20):
            packet.game_info.seconds_elapsed=tick/120;actions.append(controller.output(packet,0))
        assert [i for i,action in enumerate(actions[12:],12) if action[5]]==[14,15]
        assert controller.last_report['state_age_ticks']==12 and controller.search.candidates==2
        assert len(controller.executor.jobs)==2 # No backlog or multiple workers.
        controller.pending.set_result((sequence,{'latency_ms':100.,'candidates':2}))
        packet.game_info.seconds_elapsed=20/120;controller.output(packet,0)
        assert controller.search.candidates==2 # A slow decision cannot silently turn search into argmax.
        assert controller.last_report['candidates']==2
    finally:controller.close()


@pytest.mark.parametrize('reset,completed_tick,reason',[(True,1,'reset_generation'),(False,40,'stale')])
def test_background_rejects_old_match_and_expired_plans(monkeypatch,reset,completed_tick,reason):
    controller,packet=asynchronous_fixture(monkeypatch)
    try:
        packet.game_info.seconds_elapsed=0;controller.output(packet,0);pending=controller.pending
        if reset:controller.reset()
        sequence=np.zeros((32,8),np.float32);sequence[:,0]=-1
        pending.set_result((sequence,{'latency_ms':300.,'candidates':4}))
        packet.game_info.seconds_elapsed=completed_tick/120;action=controller.output(packet,0)
        assert action[0]==.5 and controller.discarded_results==1
        assert controller.last_discarded_plan['reason']==reason
        assert controller.bootstrap_decisions==2 and len(controller.executor.jobs)==2
        assert controller.pending is not pending
    finally:controller.close()


def test_early_background_result_does_not_truncate_the_committed_prefix(monkeypatch):
    controller,packet=asynchronous_fixture(monkeypatch)
    try:
        packet.game_info.seconds_elapsed=0;controller.output(packet,0)
        sequence=np.zeros((32,8),np.float32);sequence[:,0]=1;sequence[6:8,5]=1
        controller.pending.set_result((sequence,{'latency_ms':5.,'candidates':4}))
        packet.game_info.seconds_elapsed=1/120;controller.output(packet,0)
        packet.game_info.seconds_elapsed=8/120;action=controller.output(packet,0)
        assert action[5]==1 and len(controller.executor.jobs)==2
        controller.pending.set_result((np.zeros((32,8),np.float32),{'latency_ms':5.,'candidates':4}))
        # The result is ready at tick eight, but prefix ticks 1..8 are committed.
        action=controller.output(packet,0)
        assert action[5]==1 and controller.decision_tick==1
        packet.game_info.seconds_elapsed=9/120;action=controller.output(packet,0)
        assert action[5]==0 and controller.decision_tick==9
    finally:controller.close()


def test_worker_exception_surfaces_without_waiting_and_next_reset_can_recover(monkeypatch):
    controller,packet=asynchronous_fixture(monkeypatch)
    try:
        packet.game_info.seconds_elapsed=0;controller.output(packet,0)
        controller.pending.set_exception(ValueError('forecast failed'))
        packet.game_info.seconds_elapsed=1/120
        with pytest.raises(ValueError,match='forecast failed'):controller.output(packet,0)
        assert controller.pending is None
        controller.reset();action=controller.output(packet,0)
        assert action[0]==.5 and len(controller.executor.jobs)==2
    finally:controller.close()
