"""Real simulation and PPO-contract tests; no claim of competitive learning."""
import copy,json,os,subprocess,sys,uuid,shutil
from pathlib import Path
import numpy as np
import pytest
import torch
from replay_rvq.model import ActionCodec,StatePolicy
from replay_hybrid.policy import fixed_decoder,sample,statistics,gae,clipped_loss,ReturnCritic
from replay_hybrid.env import World,reward,potential,GAMMA
from replay_hybrid.rollout import collect,tensors
from replay_hybrid.evaluate import evaluate,paired_summary
from slater_v041_core import atomic_json,sha256,read_json
from test_replay_imitation import raw_rows,fixture_dataset


def model_fixture():
    torch.set_num_threads(2)
    return StatePolicy(ActionCodec(latent=16,hidden=64),context=32,hidden=64).eval()


def source_fixture(folder,dataset,*,production=False):
    (folder/'policy').mkdir(parents=True)
    model=StatePolicy().eval() if production else model_fixture()
    config={'codec':model.codec.config,'policy':{'context':model.config['context'],'hidden':model.config['hidden']}}
    atomic_json(folder/'protocol.json',{'provenance':'ENGINEERING_RANDOM_FIXTURE_NOT_USER_WEIGHTS'})
    atomic_json(folder/'dataset.json',{'path':str(dataset)})
    torch.save({'schema':'replay-rvq-stage-v1','stage':'policy','model':model.state_dict(),'config':config,
        'protocol_sha256':sha256(folder/'protocol.json')},folder/'policy/best.pt')
    atomic_json(folder/'policy/selected.json',{'sha256':sha256(folder/'policy/best.pt'),'updates':1})
    return model


def test_autoregressive_joint_likelihood_and_fixed_physical_decoder():
    torch.manual_seed(5);model=fixed_decoder(model_fixture())
    obs=(torch.randn(7,1,32),torch.randn(7,41,24),torch.zeros(7,41))
    actions,codes,old=sample(model,obs)
    logp,entropy,features,_=statistics(model,obs,codes)
    torch.testing.assert_close(logp,old,atol=2e-5,rtol=2e-5)
    assert codes.shape==(7,4) and (entropy>=0).all()
    assert torch.isin(actions[...,5:],torch.tensor([0.,1.])).all()
    with torch.no_grad():
        changed=model.actions(torch.randn_like(features)*100,codes)
        torch.testing.assert_close(changed,actions)
    assert all(not p.requires_grad for name,p in model.named_parameters() if name.startswith(('codec.','offset.')))
    loss,kl=clipped_loss(logp,old,torch.linspace(-1,1,7));loss.backward()
    assert model.heads[0].weight.grad.abs().sum()>0 and abs(float(kl.detach()))<1e-5


def test_gae_handles_terminal_and_time_limit_boundaries_without_reset_leakage():
    rewards=torch.tensor([[1.],[100.]])
    values=torch.tensor([[2.],[3.]])
    next_values=torch.tensor([[10.],[0.]])
    terminated=torch.tensor([[False],[True]]);truncated=torch.tensor([[True],[False]])
    advantage,returns=gae(rewards,values,next_values,terminated,truncated,.9)
    assert float(advantage[0])==pytest.approx(8.) and float(returns[0])==pytest.approx(10.)
    assert float(returns[1])==pytest.approx(100.)
    terminated[0]=True;truncated[0]=False
    _,returns=gae(rewards,values,next_values,terminated,truncated,.9)
    assert float(returns[0])==pytest.approx(1.)


@pytest.mark.parametrize('orange',[False,True])
def test_potential_reward_telescopes_and_goals_dominate(orange):
    from types import SimpleNamespace as NS
    states=[NS(ball=NS(position=np.array([0,y,100.]))) for y in (0,2500,-1500,0)]
    total=sum(GAMMA**i*reward(states[i],states[i+1],orange,False) for i in range(3))
    assert total==pytest.approx(GAMMA**3*potential(states[-1],orange)-potential(states[0],orange),abs=1e-9)
    for y in (-5300,5300):
        final=NS(ball=NS(position=np.array([0,y,100.])))
        result=reward(states[0],final,orange,True)
        assert result==pytest.approx(1. if (y>0)!=orange else -1.)


@pytest.mark.parametrize('team_size',[1,2,3])
@pytest.mark.parametrize('orange',[False,True])
def test_world_physics_controls_defensive_geometry_and_goal_labels(team_size,orange):
    world=World(7,team_size,fixed_orange=orange)
    try:
        world.reset(orange=orange,scenario='defend')
        own_sign=1 if orange else -1
        assert all(own_sign*world.state.cars[aid].physics.position[1]>own_sign*world.state.ball.position[1] for aid in world.ours)
        commands={aid:np.zeros((8,8),np.float32) for aid in world.state.cars}
        # A real physical terminal verifies team-oriented outcome supervision.
        world.state.ball.position=np.array([0,5300,100],np.float32);world.state.ball.linear_velocity=np.zeros(3,np.float32)
        world.state=world.engine.set_state(world.state,{})
        result,done,cut,final,info=world.step(commands)
        assert done and not cut and len(final)==team_size
        expected=-1 if orange else 1
        assert np.sign(result)==expected and info['goal']==(not orange)
        assert len(world.goal_examples)==team_size
        assert all(label==pytest.approx(expected*GAMMA) for _,label in world.goal_examples)
    finally:world.close()


def test_time_limit_keeps_final_observation_and_excludes_censored_goal_labels():
    world=World(9,fixed_orange=False)
    try:
        world.reset(scenario='kickoff');world.limit=1
        world.state.cars[world.ours[0]].physics.position[0]=1000
        world.state=world.engine.set_state(world.state,{})
        _,done,cut,final,_=world.step({aid:np.zeros((8,8),np.float32) for aid in world.state.cars})
        assert not done and cut and world.decisions==0 and not world.goal_examples
        assert abs(float(final[0][0][0,5]))==pytest.approx(1000/2300,abs=.01)
    finally:world.close()


def test_paired_evaluation_is_repeatable_and_does_not_train():
    model=fixed_decoder(model_fixture());before={k:v.clone() for k,v in model.state_dict().items()}
    first=evaluate(model,model,games=2,seconds=1)
    second=evaluate(model,model,games=2,seconds=1)
    assert first==second and first['paired_goal_difference_per_minute']==0
    for name,value in model.state_dict().items():torch.testing.assert_close(value,before[name],rtol=0,atol=0)
    assert paired_summary([{'candidate_goal_difference':2,'source_goal_difference':0}]*4,120)['paired_bootstrap_95pct_interval']==[1.,1.]
    assert evaluate(model,model,games=2,seconds=1,stop=lambda:True)['interrupted']


def test_real_rollout_and_optimizer_preserve_decoder_and_parent_cache(tmp_path,raw_rows):
    from replay_rvq.data import RVQData
    from replay_hybrid.train import optimize
    dataset=fixture_dataset(tmp_path/'dataset',raw_rows);data=RVQData(dataset,tmp_path/'labels')
    anchor=model_fixture();actor=fixed_decoder(copy.deepcopy(anchor));critic=ReturnCritic()
    data.use_codec(actor.codec,'fixture_codec','cpu')
    world=World(20,opponents=('chaser',));before={name:p.clone() for name,p in actor.named_parameters() if not p.requires_grad}
    try:
        batch,metrics=collect(actor,critic,[world],{'source':anchor,'peer':anchor},horizon=8,device='cpu')
        assert batch['rewards'].shape==(8,1) and batch['codes'].shape==(8,1,4)
        result=optimize(actor,critic,anchor,torch.optim.Adam([p for p in actor.parameters() if p.requires_grad],lr=1e-4),
            torch.optim.Adam(critic.parameters(),lr=3e-4),batch,data,[world],device='cpu',update=1,minibatch=4,epochs=2)
        assert result['parameter_change_l2']>0 and result['optimizer_minibatches']>0
        for name,p in actor.named_parameters():
            if name in before:torch.testing.assert_close(p,before[name],rtol=0,atol=0)
    finally:world.close()


def test_hybrid_training_checkpoint_resume_and_export_compatibility(tmp_path,raw_rows,monkeypatch):
    import replay_hybrid.train as training
    from replay_rvq.inference import load
    dataset=fixture_dataset(tmp_path/'dataset',raw_rows);source=tmp_path/'source';source_fixture(source,dataset)
    protected={p:sha256(p) for p in list(dataset.iterdir())+list(source.rglob('*.pt'))}
    root=tmp_path/'data/isolated/hybrid'
    monkeypatch.setattr(training,'ROOT',tmp_path);monkeypatch.setattr(training,'identity',lambda:{'fixture':'fixed'})
    settings=dict(envs=1,team_size=1,horizon=4,minibatch=4,device='cpu',wandb_mode='disabled',
        evaluate_every=8,evaluation_games=2,evaluation_seconds=1,final_games=2,final_seconds=1)
    training.train(source,root,steps=16,**settings)
    progress=read_json(root/'progress.json');assert progress['steps']==16 and progress['updates']==4
    digest=sha256(root/'training/latest.pt')
    training.train(source,root,steps=16,**settings);assert sha256(root/'training/latest.pt')==digest
    training.train(source,root,steps=24,**settings);assert read_json(root/'progress.json')['steps']==24
    assert {p:sha256(p) for p in protected}==protected
    assert read_json(root/'protocol.json')['value_contract'].startswith('policy.values predicts discounted next goal')
    loaded=load(root)
    assert loaded.config['codec']['levels']==4
    # The source snapshot allows continuation even if the parent later changes.
    (source/'policy/best.pt').write_bytes(b'parent changed independently')
    training.train(source,root,steps=28,**settings)
    assert read_json(root/'progress.json')['steps']==28
    from replay_hybrid.__main__ import export_run
    name='HybridTest_'+uuid.uuid4().hex[:8];target=None
    atomic_json(root/'heldout_matches.json',{'checkpoint_sha256':'different-checkpoint','improvement_on_tested_pool':True})
    try:
        target=export_run(root,name,latest=True)
        info=read_json(target/'EXPORT_INFO.json')
        assert info['mode']=='policy' and info['hybrid']['experimental_latest']
        assert not info['hybrid']['heldout_checkpoint_matches'] and info['hybrid']['heldout']=={}
        assert read_json(target/'runtime.json')['mode']=='policy' and 'PPO' in info['learning']
    finally:
        if target is not None:shutil.rmtree(target,ignore_errors=True)


def test_hybrid_graceful_pause_preserves_consumed_rollout_and_resumes(tmp_path,raw_rows,monkeypatch):
    import replay_hybrid.train as training
    dataset=fixture_dataset(tmp_path/'dataset',raw_rows);source=tmp_path/'source';source_fixture(source,dataset)
    root=tmp_path/'data/isolated/hybrid_pause'
    monkeypatch.setattr(training,'ROOT',tmp_path);monkeypatch.setattr(training,'identity',lambda:{'fixture':'fixed'})
    original=training.collect
    def partial(*args,**kwargs):
        kwargs['horizon']=2
        result=original(*args,**kwargs);(root/'pause.flag').touch();return result
    monkeypatch.setattr(training,'collect',partial)
    settings=dict(envs=1,horizon=8,minibatch=4,device='cpu',wandb_mode='disabled',evaluate_every=8,
        evaluation_games=2,evaluation_seconds=1,final_games=2,final_seconds=1)
    training.train(source,root,steps=8,**settings)
    assert read_json(root/'progress.json')['steps']==2 and read_json(root/'status.json')['paused']
    monkeypatch.setattr(training,'collect',original)
    training.train(source,root,steps=8,**settings)
    assert read_json(root/'progress.json')['steps']==8 and not read_json(root/'status.json')['paused']


@pytest.mark.parametrize('nexto_regressed',[False,True])
def test_selection_uses_validation_and_separate_heldout_seeds(tmp_path,raw_rows,monkeypatch,nexto_regressed):
    import replay_hybrid.train as training
    dataset=fixture_dataset(tmp_path/'dataset',raw_rows);source=tmp_path/'source';source_fixture(source,dataset)
    root=tmp_path/'data/isolated/hybrid_selection'
    monkeypatch.setattr(training,'ROOT',tmp_path);monkeypatch.setattr(training,'identity',lambda:{'fixture':'fixed'})
    calls=[]
    def known_scores(*args,**kwargs):
        calls.append(kwargs.get('seed',800000))
        return {'paired_goal_difference_per_minute':1.,'paired_bootstrap_95pct_interval':[.5,1.5],
            'by_opponent':{'nexto':{'paired_goal_difference_per_minute':-1. if nexto_regressed else 1.}},
            'scope':'MOCKED SELECTION CONTROL FLOW, NOT MATCH RESULTS'}
    monkeypatch.setattr(training,'evaluate',known_scores)
    training.train(source,root,steps=8,envs=1,horizon=4,minibatch=4,device='cpu',wandb_mode='disabled',
        evaluate_every=8,evaluation_games=2,evaluation_seconds=1,final_games=2,final_seconds=1)
    selected=read_json(root/'policy/selected.json')
    if nexto_regressed:
        assert selected['updates']==0 and calls==[800000] and not (root/'heldout_matches.json').exists()
    else:
        assert selected['updates']>0 and calls==[800000,1800000]
        assert read_json(root/'heldout_matches.json')['checkpoint_sha256']==sha256(root/'policy/best.pt')


def test_paused_final_test_resumes_after_training_budget_is_complete(tmp_path,raw_rows,monkeypatch):
    import replay_hybrid.train as training
    dataset=fixture_dataset(tmp_path/'dataset',raw_rows);source=tmp_path/'source';source_fixture(source,dataset)
    root=tmp_path/'data/isolated/hybrid_final_pause';calls=[]
    monkeypatch.setattr(training,'ROOT',tmp_path);monkeypatch.setattr(training,'identity',lambda:{'fixture':'fixed'})
    def scores(*args,**kwargs):
        seed=kwargs.get('seed',800000);calls.append(seed)
        if seed==800000:(root/'pause.flag').touch()
        return {'paired_goal_difference_per_minute':1.,'paired_bootstrap_95pct_interval':[.5,1.5],
            'by_opponent':{},'scope':'MOCK CONTROL FLOW, NOT MATCH RESULTS'}
    monkeypatch.setattr(training,'evaluate',scores)
    settings=dict(steps=8,envs=1,horizon=4,minibatch=4,device='cpu',wandb_mode='disabled',evaluate_every=8,
        evaluation_games=2,evaluation_seconds=1,final_games=2,final_seconds=1)
    training.train(source,root,**settings)
    assert read_json(root/'status.json')['heldout_pending'] and calls==[800000]
    checkpoint=sha256(root/'training/latest.pt')
    training.train(source,root,**settings)
    assert calls==[800000,1800000] and not read_json(root/'status.json')['heldout_pending']
    assert sha256(root/'training/latest.pt')==checkpoint


def test_original_nexto_opponent_padding_matches_unpadded_inputs():
    path=os.environ.get('HYBRID_TEST_NEXTO')
    if not path:pytest.skip('Set HYBRID_TEST_NEXTO for original local Nexto weight parity')
    from replay_hybrid.nexto import NextoOpponent
    from nexto_teacher import NextoTeacher
    from vendor.nexto.nexto_obs import NextoObsBuilder
    world=World(21);teacher=NextoTeacher.__new__(NextoTeacher);teacher.torch=torch;teacher.device=torch.device('cpu')
    teacher.actor=torch.jit.load(path,map_location='cpu').eval()
    teacher.obs_builder=NextoObsBuilder(n_players=2,tick_skip=8)
    opponent=NextoOpponent(path)
    try:
        original=teacher.observe(world.state,world.previous);expected=teacher.logits([row[1:] for row in original])
        actual=opponent.logits(list(world.observe().values()))
        np.testing.assert_allclose(actual,expected,atol=3e-5,rtol=3e-5)
    finally:world.close()
    for size in (2,3):
        team_world=World(22,team_size=size)
        try:assert opponent.logits(list(team_world.observe().values())).shape==(2*size,90)
        finally:team_world.close()


def test_production_hybrid_cli_uses_existing_source_and_preserves_it(raw_rows):
    from replay_hybrid.train import ROOT
    token=uuid.uuid4().hex[:8];base=ROOT/'data/isolated/replay_debug'/('hybrid_cli_'+token)
    source_name='hybrid_source_'+token;run_name='hybrid_cli_'+token
    runs=ROOT/'data/isolated/replay_imitation/rvq_runs';source=runs/source_name;child=runs/run_name
    try:
        dataset=fixture_dataset(base/'dataset',raw_rows);source_fixture(source,dataset,production=True)
        before=sha256(source/'policy/best.pt')
        command=[sys.executable,'-m','replay_hybrid','start','--source-run',source_name,'--run',run_name,
            '--steps','8','--envs','1','--horizon','4','--minibatch','4','--evaluate-every','8',
            '--evaluation-games','2','--evaluation-seconds','1','--final-games','2','--final-seconds','1',
            '--device','cpu','--wandb-mode','disabled']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=90)
        assert result.returncode==0,result.stdout+result.stderr
        assert read_json(child/'progress.json')['steps']==8 and sha256(source/'policy/best.pt')==before
        assert read_json(child/'model.json')['actor_parameters']==3_074_595
    finally:
        for path in (base,source,child):shutil.rmtree(path,ignore_errors=True)
