from argparse import Namespace
import copy
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest
import torch

from nova.core import OBS_SIZE,ACTIONS,nearest_action,check_model
from nova.environment import ArenaEnv
from nova.training import new_model
from nova.teachers import Scripted
from nova import imitation


def test_supervised_copying_learns_controls_without_value_or_ppo_updates(cfg,tmp_path,monkeypatch):
    torch.set_num_threads(1)
    cfg['ppo']['learning_rate']=.003
    env=ArenaEnv(cfg,opponent='scripted')
    try:
        model=new_model(cfg,env)
        monkeypatch.setattr(model,'learn',lambda *a,**k:pytest.fail('Copying must not call PPO.learn'))
        before={k:v.detach().clone() for k,v in model.policy.named_parameters() if 'value_net' in k}
        label=nearest_action(np.array([1,0,0,0,0,0,1,0],np.float32))
        rng=np.random.default_rng(73)
        data=dict(obs=rng.normal(size=(128,OBS_SIZE)).astype(np.float32),
            actions=np.full(128,label,np.int64),teacher_id=np.zeros(128,np.int16),scenario_id=np.zeros(128,np.int16))
        initial=imitation.validate(model,data,['nexto'],['kickoff'])
        for i in range(12): imitation.fit_epoch(model,data,i,tmp_path/'STOP',batch_size=32)
        final=imitation.validate(model,data,['nexto'],['kickoff'])
        assert final['loss']<initial['loss']*.5
        assert final['accuracy']>.9 and final['control_mae']<.05
        for key,value in model.policy.named_parameters():
            if key in before: torch.testing.assert_close(value,before[key],rtol=0,atol=0)
    finally:env.close()


def test_teacher_loss_weights_equalize_teacher_contribution():
    ids=np.array([0]*99+[1])
    w=imitation.balance_weights(ids)
    assert np.sum(w[ids[:99]])==pytest.approx(w[1])
    assert w[ids].mean()==pytest.approx(1)


def test_actor_is_independent_of_previous_controls_after_copy_update(tmp_path,cfg):
    torch.set_num_threads(1)
    env=ArenaEnv(cfg,opponent='scripted')
    try:
        model=new_model(cfg,env)
        rng=np.random.default_rng(77)
        data=dict(obs=rng.normal(size=(32,OBS_SIZE)).astype(np.float32),actions=np.full(32,7,np.int64),
            teacher_id=np.zeros(32,np.int16),scenario_id=np.zeros(32,np.int16))
        imitation.fit_epoch(model,data,17,tmp_path/'STOP')
        x=torch.as_tensor(data['obs'][:2]);changed=x.clone();changed[:,-8:]=torch.tensor([1,-1,0,1,0,1,1,0])
        with torch.no_grad():
            a=model.policy.get_distribution(x).distribution.logits
            b=model.policy.get_distribution(changed).distribution.logits
        torch.testing.assert_close(a,b,rtol=0,atol=0)
        layer=model.policy.mlp_extractor.policy_net[0]
        assert torch.count_nonzero(layer.weight[:,-8:])==0
    finally:env.close()


def test_final_control_labels_retain_native_style_mid_window_transitions(tmp_path,cfg,monkeypatch):
    from nova import data
    class LaggedTeacher:
        def reset(self,*args):self.calls=0;self.held=np.zeros(8,np.float32)
        def controls_for_ticks(self,state,ticks):
            commands=np.repeat(self.held[None,:],ticks,axis=0)
            if self.calls%2:
                self.held=np.array([1 if self.calls%4==1 else -1,0,0,0,0,0,0,0],np.float32)
                commands[-1]=self.held
            self.calls+=1;return commands
    monkeypatch.setattr(data,'make_opponent',lambda name:LaggedTeacher())
    cfg['curriculum']['weights']={'kickoff':1.}
    config=tmp_path/'settings.json';config.write_text(json.dumps(cfg))
    out=tmp_path/'transitions.npz'
    summary=data.collect(Namespace(config=str(config),replay_bank=None,opponent='scripted',teacher='scripted',
        samples=13,out=str(out),seed=501,label_mode='final_executed'))
    with np.load(out) as z:
        previous=z['obs'][:,-8:];target=ACTIONS[z['actions']]
        changed=np.max(np.abs(previous-target),axis=1)>1e-6
        assert changed.any() and (~changed).any()
        np.testing.assert_array_equal(z['transition'],changed)
    assert summary['accepted_mid_window_changes']>0 and summary['skipped_startup_idle']>0
    assert summary['label_mode']=='final_executed'


def test_validation_coverage_notes_distinguish_missing_and_small_samples():
    validation=dict(by_scenario={'kickoff':{'samples':5762},'aerial':{'samples':187}})
    notes=imitation.validation_coverage_notes(validation,{'kickoff':.5,'aerial':.1,'dribble':.1,'wall':0})
    assert any('dribble: no held-out' in n for n in notes)
    assert any('aerial: only 187' in n for n in notes)
    assert not any(n.startswith(('kickoff:','wall:')) for n in notes)
    assert len(imitation.validation_coverage_notes(None,{}))==1


def test_return_weighting_is_bounded_balanced_and_censored_returns_are_neutral():
    data=dict(teacher_id=np.array([0,0,0,1,1,1]),return_to_go=np.array([-10,0,10,-1,1,999],np.float32),
        return_complete=np.array([True,True,True,True,True,False]))
    w=imitation.return_weights(data)
    assert w[0]<w[1]<w[2] and w[3]<w[4]
    assert w[5]==1 and w.min()>=.5 and w.max()<=1.5
    assert w[:3].mean()==pytest.approx(1) and w[3:].mean()==pytest.approx(1)


def test_collection_records_discounted_teacher_returns_and_marks_censored_tail(tmp_path,cfg,monkeypatch):
    from nova import data
    class Zero:
        def reset(self,*args):pass
        def act(self,state):return np.zeros(8,np.float32)
    monkeypatch.setattr(data,'make_opponent',lambda name:Zero())
    cfg['curriculum']['weights']={'shot':1.}
    path=tmp_path/'settings.json';path.write_text(json.dumps(cfg))
    out=tmp_path/'demonstrations.npz'
    data.collect(Namespace(config=str(path),replay_bank=None,opponent='scripted',teacher='scripted',
        samples=13,out=str(out),seed=7101))
    with np.load(out,allow_pickle=False) as z:
        assert len(np.unique(z['episode']))==3
        assert np.any(np.abs(z['reward'])>1e-6)
        for episode in np.unique(z['episode']):
            indices=np.flatnonzero(z['episode']==episode)
            expected=[];future=0.
            for reward in z['reward'][indices][::-1]:
                future=float(reward)+cfg['ppo']['gamma']*future;expected.append(future)
            np.testing.assert_allclose(z['return_to_go'][indices],expected[::-1],rtol=1e-5,atol=1e-7)
            assert np.all(z['return_complete'][indices]==(episode<2))


def copy_args(config,run='copy_test'):
    return Namespace(run=run,config=str(config),teachers='nexto,ripple',resume=False,init=None,
        forever=False,rounds=1,samples=64,validation_samples=64,buffer_samples=128,
        epochs=2,lr=.001,seed=17017,wandb='off')


def setup_copy(tmp_path,cfg,monkeypatch):
    from nova import data
    monkeypatch.setattr(imitation,'ROOT',tmp_path)
    (tmp_path/'teachers.lock.json').write_text('[]')
    monkeypatch.setattr(imitation,'verify_teacher',lambda name:None)
    monkeypatch.setattr(imitation,'student_probe',lambda *a,**k:dict(trials=4,contact_fraction=0.,score_fraction=0.,concede_fraction=1.,timeout_fraction=0.))
    teachers=[]
    class FrozenTestTeacher(Scripted):
        def __init__(self):
            self.network=torch.jit.trace(torch.nn.Linear(3,2),torch.zeros(1,3))
            self.original=copy.deepcopy(self.network.state_dict())
            teachers.append(self)
    monkeypatch.setattr(data,'make_opponent',lambda name:FrozenTestTeacher())
    monkeypatch.setattr('stable_baselines3.PPO.learn',lambda *a,**k:pytest.fail('PPO called during imitation'))
    config=tmp_path/'settings.json';config.write_text(json.dumps(cfg))
    return config,teachers


def test_student_probe_measures_own_controls_and_honors_pause(cfg,tmp_path):
    zero=nearest_action(np.zeros(8,np.float32))
    class Idle:
        def predict(self,obs,deterministic=True):return np.asarray(zero),None
    result=imitation.student_probe(Idle(),cfg,tmp_path/'STOP')
    assert result['trials']==10 and result['active_control_fraction']==0
    assert result['forward_throttle_fraction']==0 and result['boost_fraction']==0
    assert result['score_fraction']+result['concede_fraction']+result['timeout_fraction']==pytest.approx(1)
    (tmp_path/'STOP').touch()
    assert imitation.student_probe(Idle(),cfg,tmp_path/'STOP') is None


def test_monitoring_seeds_cover_all_standard_kickoff_spawns(cfg):
    env=ArenaEnv(cfg,opponent='scripted',scenario='kickoff',side=0)
    try:
        positions=set()
        for seed in imitation.PROBE_SEEDS:
            env.reset(seed=seed)
            positions.add(tuple(env.state.cars[env.agent].physics.position.round().tolist()))
        assert len(positions)==5
    finally:env.close()


def test_published_student_prefers_actual_contacts_over_lower_copy_loss(tmp_path,monkeypatch):
    def record(name):return dict(path=name,sha256=(name[0]*64),timesteps=50000)
    state=dict(best=record('validation.zip'),best_validation={'balanced_loss':.1},resume=record('last.zip'),
        published=record('initial.zip'),history=[{'validation':{'balanced_loss':.3}}])
    monkeypatch.setattr(imitation,'load_ppo',lambda path:path.name)
    contacts={'validation.zip':0.,'last.zip':1.}
    monkeypatch.setattr(imitation,'student_probe',lambda model,*a:dict(trials=12,contact_fraction=contacts[model],score_fraction=0.,concede_fraction=1.))
    probe=imitation.publish_by_probe(None,tmp_path,state,{},tmp_path/'STOP')
    assert probe['contact_fraction']==1
    assert state['published']['path']=='last.zip'
    assert state['best']['path']=='validation.zip'
    assert json.loads((tmp_path/'latest.json').read_text())['path']=='last.zip'
    contacts['last.zip']=0.
    imitation.publish_by_probe(None,tmp_path,state,{},tmp_path/'STOP')
    assert state['last_student_probe']['contact_fraction']==1


def test_first_contact_curriculum_resets_after_teacher_touch(tmp_path,cfg):
    from nova import data
    cfg['env'].update(episode_seconds=8,no_touch_seconds=9)
    cfg['curriculum']['weights']={'kickoff':1.}
    config=tmp_path/'first_touch.json';config.write_text(json.dumps(cfg))
    result=data.collect(Namespace(config=str(config),replay_bank=None,opponent='scripted',teacher='scripted',
        samples=400,out=str(tmp_path/'touches.npz'),seed=731,label_mode='final_executed',first_contact_fraction=1.))
    assert result['first_contact_segments']>0


def test_copy_pipeline_frozen_teachers_separate_validation_resume_and_safe_report(tmp_path,cfg,monkeypatch):
    torch.set_num_threads(1)
    config,teachers=setup_copy(tmp_path,cfg,monkeypatch)
    args=copy_args(config);imitation.train_copy(args)
    run=tmp_path/'runs/copy_test'
    first=json.loads((run/'copy_state.json').read_text())
    assert first['round']==1 and first['collected_decisions']==64
    assert first['gradient_updates']>0
    assert not ({e['path'] for e in first['validation_shards']}&{e['path'] for e in first['shards']})
    assert first['validation_decisions']==64
    initial_hash=check_model(run/'checkpoints/initial.zip')['sha256']
    args.resume=True;imitation.train_copy(args)
    state=json.loads((run/'copy_state.json').read_text())
    assert state['round']==2 and state['collected_decisions']==128
    assert state['gradient_updates']>first['gradient_updates']
    assert state['validation_shards']==first['validation_shards']
    assert check_model(run/'checkpoints/initial.zip')['sha256']==initial_hash
    pointer=json.loads((run/'latest.json').read_text())
    assert pointer['path']==state['best']['path']
    assert check_model(run/pointer['path'])['sha256']==state['best']['sha256']
    for teacher in teachers:
        assert not teacher.network.training
        assert not any(p.requires_grad for p in teacher.network.parameters())
        for name,tensor in teacher.network.state_dict().items():
            torch.testing.assert_close(tensor,teacher.original[name],rtol=0,atol=0)
    # The report is an allowlist, rather than a dump of configs/state/credentials.
    secret='DO_NOT_EXPORT_COPY_SECRET'
    state['api_key']=secret
    (run/'copy_state.json').write_text(json.dumps(state))
    (run/'wandb_status.json').write_text(json.dumps(dict(api_key=secret,url='https://wandb.ai/me/project/runs/abc?key='+secret)))
    imitation.report_copy(Namespace(run='copy_test'))
    out=next((tmp_path/'reports').glob('*copy_report*.zip'))
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist())=={'report.json','training.csv','progress.html','README.txt'}
        assert secret not in ''.join(z.read(n).decode() for n in z.namelist())
        report=json.loads(z.read('report.json'))
        assert report['kind']=='frozen_teacher_copying'
        assert report['best_checkpoint']['sha256']==state['best']['sha256']


def test_pause_during_fit_preserves_optimizer_and_resumes_same_round(tmp_path,cfg,monkeypatch):
    torch.set_num_threads(1)
    config,_=setup_copy(tmp_path,cfg,monkeypatch)
    args=copy_args(config,'paused_copy');real_fit=imitation.fit_epoch
    args.forever=True
    def stop_after_fit(*a,**k):
        result=real_fit(*a,**k);a[3].touch();return result
    monkeypatch.setattr(imitation,'fit_epoch',stop_after_fit)
    imitation.train_copy(args)
    run=tmp_path/'runs/paused_copy'
    paused=json.loads((run/'copy_state.json').read_text())
    assert paused['phase']=='fit' and paused['epoch']==0 and paused['round']==0
    assert paused['gradient_updates']>0
    assert json.loads((run/'status.json').read_text())['state']=='stopped'
    monkeypatch.setattr(imitation,'fit_epoch',real_fit)
    args.resume=True;args.forever=False;imitation.train_copy(args)
    resumed=json.loads((run/'copy_state.json').read_text())
    assert resumed['round']==1
    assert resumed['collected_decisions']==paused['collected_decisions']
    assert resumed['gradient_updates']>paused['gradient_updates']


def test_copy_resume_rejects_changed_teacher_lock(tmp_path,cfg,monkeypatch):
    config,_=setup_copy(tmp_path,cfg,monkeypatch)
    args=copy_args(config);imitation.train_copy(args)
    (tmp_path/'teachers.lock.json').write_text('[{"changed":true}]')
    args.resume=True
    with pytest.raises(ValueError,match='Teacher lock changed'):imitation.train_copy(args)


def test_pause_during_validation_collection_preserves_partial_shard(tmp_path,cfg,monkeypatch):
    torch.set_num_threads(1)
    config,_=setup_copy(tmp_path,cfg,monkeypatch)
    args=copy_args(config,'collection_pause');args.validation_samples=1100
    real_collect=imitation.collect
    def pause_collection(options):
        original=options.on_progress
        def stop_after_chunk(n,k):
            original(n,k);options.stop_path.touch()
        options.on_progress=stop_after_chunk
        return real_collect(options)
    monkeypatch.setattr(imitation,'collect',pause_collection)
    imitation.train_copy(args)
    run=tmp_path/'runs/collection_pause'
    first=json.loads((run/'copy_state.json').read_text())
    assert first['validation_decisions']==1000 and first['collected_decisions']==0
    assert len(first['validation_shards'])==1
    monkeypatch.setattr(imitation,'collect',real_collect)
    args.resume=True;imitation.train_copy(args)
    final=json.loads((run/'copy_state.json').read_text())
    assert final['validation_decisions']==1100 and len(final['validation_shards'])==2
    assert final['validation_shards'][0]==first['validation_shards'][0]
    assert final['round']==1 and final['collected_decisions']==64
