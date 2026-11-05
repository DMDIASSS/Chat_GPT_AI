import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
import torch
from nova.chronos import CHRONOS_CONTRACT,ChronosEnv
from nova.chronos_training import new_chronos_model,finish_config
from nova.chronos_guard import paired_statistics,judgement,check_progress,select_checkpoint,EvaluationStopped,screen
from nova.core import atomic_json,write_model_meta,check_model
from nova.training import load_config


def config():
    cfg=load_config(Path(__file__).resolve().parents[1]/'configs/chronos.json')
    cfg.update(workers=1,device='cpu');cfg['league']['weights']={'scorer':1.}
    cfg['ppo'].update(n_steps=8,batch_size=8,n_epochs=1)
    cfg['chronos']['critic_warmup_updates']=1
    cfg['chronos']['guard']['enabled']=False
    return cfg


@pytest.mark.parametrize('side',[0,1])
@pytest.mark.parametrize('ball_y',[5190.,5000.])
@pytest.mark.parametrize('outcome',[-1,1])
def test_goals_receive_exact_full_decision_reward_in_either_physics_half(side,ball_y,outcome):
    cfg=config();env=ChronosEnv(cfg,opponent='scorer',scenario='kickoff',side=side)
    try:
        env.reset(seed=22);state=copy.deepcopy(env.arena.state);direction=(1 if side==0 else -1)*outcome
        state.ball.position=np.array([0,ball_y*direction,100],dtype=np.float32)
        state.ball.linear_velocity=np.array([0,4000*direction,0],dtype=np.float32)
        env.arena.state=env.arena.engine.set_state(state,{})
        obs=env.observation();phi=env.arena.potential(env.arena.state)
        obs,reward,term,trunc,info=env.step(int(np.flatnonzero(obs[225:])[0]))
        assert term and not trunc and info['outcome']==outcome
        assert reward==pytest.approx(10*outcome-phi,abs=1e-6)
        assert info['reward_parts']['goal']==10*outcome
        assert info['episode']['r']==pytest.approx(reward)
    finally:env.close()


def test_timeout_waits_for_eight_ticks_and_retains_bootstrap_potential():
    cfg=config();cfg['env'].update(episode_seconds=.1,no_touch_seconds=1)
    env=ChronosEnv(cfg,opponent='scorer',scenario='kickoff')
    try:
        obs,_=env.reset(seed=22)
        obs,_,term,trunc,_=env.step(int(np.flatnonzero(obs[225:])[0]));assert not term and not trunc
        phi=env.arena.potential(env.arena.state)
        obs,reward,term,trunc,info=env.step(int(np.flatnonzero(obs[225:])[0]))
        assert trunc and not term and info['seconds']==pytest.approx(16/120)
        assert reward==pytest.approx(cfg['ppo']['gamma']*env.arena.potential(env.arena.state)-phi)
        env.reset(seed=22);assert env.reward_parts=={} and env.reward_total==0
    finally:env.close()


@pytest.mark.parametrize('failure',['kl','nonfinite'])
def test_failed_update_restores_policy_before_any_final_checkpoint(failure,monkeypatch):
    cfg=config();env=ChronosEnv(cfg,opponent='scorer');torch.set_num_threads(1)
    try:
        model=new_chronos_model(cfg,env,initialize=False)
        from stable_baselines3.common.logger import configure
        model.set_logger(configure(None,[]));model.rollout_buffer.observations[:]=0
        before={k:v.clone() for k,v in model.policy.state_dict().items()};rate=model.actor_lr
        def bad_update():
            with torch.no_grad():next(model.policy.actor.parameters()).add_(100)
            if failure=='nonfinite':raise FloatingPointError('injected invalid loss')
        monkeypatch.setattr(model,'_train_chronos',bad_update)
        monkeypatch.setattr(model.policy,'anchor_kl',lambda obs:torch.tensor(1.))
        if failure=='nonfinite':
            with pytest.raises(FloatingPointError):model.train()
        else:
            model.train();assert model.actor_lr==pytest.approx(rate*.5)
        assert all(torch.equal(v,before[k]) for k,v in model.policy.state_dict().items())
    finally:env.close()


def rows(delta=1,start=0,count=12):
    candidate=[];baseline=[]
    for i in range(count):
        for side in (0,1):
            base=dict(opponent='chronos',scenario='kickoff',seed=start+i,side=side,
                outcome=0,touches=1,timeout=False,practice_success=False)
            baseline.append(base);candidate.append(dict(base,outcome=delta if i%2 else 0))
    return candidate,baseline


def test_guard_clusters_mirrored_teams_and_rejects_unpaired_rows():
    a,b=rows();stats=paired_statistics(a,b)
    assert stats['blocks']==12 and stats['trials']==24
    assert stats['standard_error']==pytest.approx(np.std([0,1]*6,ddof=1)/np.sqrt(12))
    cfg=config()['chronos']['guard'];assert judgement(stats,cfg)=='improved'
    a,b=rows(-1);assert judgement(paired_statistics(a,b),cfg)=='regressed'
    with pytest.raises(ValueError):paired_statistics(a[:-1],b)


def checkpoint(run,step,data):
    path=run/'checkpoints'/f'step_{step:012d}.zip';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    write_model_meta(path,contract=CHRONOS_CONTRACT,timesteps=step)
    return path


def test_promotion_requires_fresh_confirmation_and_retains_a_separate_champion(tmp_path,monkeypatch):
    import nova.chronos_guard as guard
    run=tmp_path/'runs/test';old=checkpoint(run,0,b'initial');new=checkpoint(run,64,b'candidate')
    atomic_json(run/'latest.json',{'path':str(new.relative_to(run))})
    cfg=config();cfg['chronos']['guard'].update(enabled=True)
    calls=[]
    def fake_screen(cfg,candidate,baseline,pairs,seconds,seed,stop):calls.append(seed);return rows(1,seed)
    monkeypatch.setattr(guard,'screen',fake_screen)
    class Tracker:
        def log(self,*args):pass
    assert not check_progress(run,cfg,NS(num_timesteps=64),Tracker(),force=True)
    selected=select_checkpoint(run)
    assert len(calls)==2 and calls[0]!=calls[1]
    assert selected.read_bytes()==b'candidate' and selected!=new
    new.unlink();Path(str(new)+'.json').unlink()
    assert check_model(select_checkpoint(run),CHRONOS_CONTRACT)['timesteps']==64
    assert old.read_bytes()==b'initial'


def test_failed_confirmation_keeps_original_champion(tmp_path,monkeypatch):
    import nova.chronos_guard as guard
    run=tmp_path/'runs/test';initial=checkpoint(run,0,b'initial');new=checkpoint(run,64,b'candidate')
    atomic_json(run/'latest.json',{'path':str(new.relative_to(run))})
    cfg=config();cfg['chronos']['guard']['enabled']=True;calls=[]
    def fake(*args):calls.append(1);return rows(1 if len(calls)==1 else -1,int(args[5]))
    monkeypatch.setattr(guard,'screen',fake)
    check_progress(run,cfg,NS(num_timesteps=64),NS(log=lambda *args:None),force=True)
    assert select_checkpoint(run)==initial
    assert json.loads((run/'guard_state.json').read_text())['decision']=='retain'


def test_upgrade_backs_up_weights_and_preserves_machine_settings(tmp_path):
    old=config();old['chronos']['reward_profile']='potential_goal_v1';old['ppo']['gamma']=.990025
    old.update(seed=999,workers=1,threads=1,device='cpu')
    atomic_json(tmp_path/'config.json',old);source=checkpoint(tmp_path,64,b'original optimizer bytes')
    upgraded=finish_config(tmp_path,old,source)
    assert upgraded['ppo']['gamma']==.999 and upgraded['seed']==999 and upgraded['workers']==1
    assert upgraded['chronos']['guard']['enabled']
    assert (tmp_path/'upgrades/pre_v1_7_0/full.zip').read_bytes()==source.read_bytes()
    assert json.loads((tmp_path/'upgrades/pre_v1_7_0/config.json').read_text())['ppo']['gamma']==.990025
    assert finish_config(tmp_path,upgraded,source)==upgraded


def test_pause_is_honored_before_loading_models_for_evaluation(tmp_path):
    stop=tmp_path/'STOP';stop.touch()
    with pytest.raises(EvaluationStopped):screen(config(),'missing','missing',1,1,1,stop)


def test_substantial_match_regression_stops_training_and_preserves_champion(tmp_path,monkeypatch):
    import nova.chronos_guard as guard
    import nova.chronos_training as training
    run=tmp_path/'runs/test';initial=checkpoint(run,0,b'initial');latest=checkpoint(run,64,b'candidate')
    atomic_json(run/'latest.json',{'path':str(latest.relative_to(run))})
    cfg=config();cfg['chronos']['guard']['enabled']=True
    monkeypatch.setattr(guard,'screen',lambda *args:rows(-1))
    monkeypatch.setattr(guard,'reset_critic',lambda *args:None)
    monkeypatch.setattr(training,'load_network',lambda path:NS(state_dict=lambda:{'original':1}))
    restored=[]
    model=NS(num_timesteps=64,actor_lr=1e-5,anchor_coef=.2,policy=NS(actor=NS(load_state_dict=lambda state:restored.append(state))))
    assert check_progress(run,cfg,model,NS(log=lambda *args:None),force=True)
    assert (run/'STOP').exists() and model.training_halt_reason
    assert restored==[{'original':1}] and select_checkpoint(run)==initial


def test_probability_projection_preserves_valid_actions_and_mirrored_controls():
    from nova.chronos_fusion import project_probabilities
    from nova.giga_teachers import TABLE
    mask=np.ones(90,dtype=bool);source=TABLE.copy();source[:,[1,3,4]]*=-1
    probabilities=np.zeros(90);probabilities[0]=1
    result=project_probabilities(probabilities,source,True,mask)
    np.testing.assert_array_equal(result,probabilities)
    mask[0]=False;result=project_probabilities(probabilities,source,True,mask)
    assert result[0]==0 and result.sum()==pytest.approx(1)


def test_actual_three_teacher_probability_fusion_is_finite_and_chronos_weight_is_respected(request):
    if not request.config.getoption('--teachers'):pytest.skip('Requires downloaded three-teacher assets')
    from nova.chronos_fusion import TeacherFusion,softmax
    from nova.giga_teachers import native_action_mask
    cfg=config();env=ChronosEnv(cfg,opponent='scorer',scenario='recovery',side=1)
    try:
        obs,_=env.reset(seed=22);teacher=TeacherFusion()
        teacher.reset(env.arena.state,env.arena.agent,np.random.default_rng(22))
        target=teacher.probabilities(env.arena.state,env.previous,obs[:225],env.mirror)
        assert target.shape==(90,) and np.isfinite(target).all() and target.sum()==pytest.approx(1)
        assert not target[obs[225:]==0].any()
        teacher.weights=np.array([1.,0.,0.])
        target=teacher.probabilities(env.arena.state,env.previous,obs[:225],env.mirror)
        with torch.no_grad():original=teacher.chronos(torch.from_numpy(obs[:225])[None,:])[0].numpy()
        np.testing.assert_allclose(target,softmax(original,native_action_mask(env.arena.state.cars[env.arena.agent])),atol=1e-7)
    finally:env.close()
