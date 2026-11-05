from argparse import Namespace
import copy
import json
import numpy as np
import pytest

from nova import data,imitation
from nova.core import ACTIONS,nearest_action
from nova.environment import ArenaEnv
from nova.teachers import Scorer


def test_bootstrap_retains_general_scenarios_and_stable_ids(cfg):
    cfg['copy']=imitation.correction_options()
    cfg['curriculum']['weights']={'kickoff':.5,'shot':.2,'defense':.1,'recovery':.2,'wall':0.}
    original=copy.deepcopy(cfg)
    focused=imitation.collection_config(cfg,True)
    weights=focused['curriculum']['weights']
    assert weights['kickoff']==pytest.approx(.65)
    assert sum(weights.values())==pytest.approx(1)
    assert weights['shot']>0 and weights['defense']>0 and weights['recovery']>0 and weights['wall']==0
    assert list(weights)==list(original['curriculum']['weights']) and cfg==original


@pytest.mark.parametrize('side',[0,1])
def test_scorer_scores_a_ground_shot_and_routes_behind_ball(cfg,side):
    cfg['env'].update(episode_seconds=12,no_touch_seconds=13)
    env=ArenaEnv(cfg,opponent='scripted',scenario='shot',side=side)
    try:
        env.reset(seed=241);s=env.state;direction=1 if side==0 else -1
        s.ball.position=np.array([400,3000*direction,93.15],np.float32)
        s.ball.linear_velocity=np.zeros(3,np.float32);s.ball.angular_velocity=np.zeros(3,np.float32)
        for key,car in s.cars.items():
            car.physics.position=np.array([400,2400*direction,17] if key==env.agent else [3000,-3000*direction,17],np.float32)
            car.physics.euler_angles=np.array([0,np.pi/2*direction,0],np.float32)
            car.physics.linear_velocity=np.zeros(3,np.float32);car.physics.angular_velocity=np.zeros(3,np.float32)
            car.boost_amount=60
        env.state=env.engine.set_state(s,{})
        scorer=Scorer();scorer.reset(env.state,env.agent,np.random.default_rng(1))
        target,lined=scorer.target(env.state)
        assert lined and direction*(target[1]-env.state.ball.position[1])>0
        wrong=copy.deepcopy(env.state);wrong.cars[env.agent].physics.position[1]=3400*direction
        target,lined=scorer.target(wrong)
        assert not lined and direction*(target[1]-wrong.ball.position[1])<0
        for _ in range(360):
            _,_,terminal,truncated,info=env.step_controls(scorer.act(env.state))
            if terminal or truncated:break
        assert info['outcome']==1 and env.own_touches>0
    finally:env.close()


def test_collection_mixes_opponents_and_collects_teacher_takeovers(tmp_path,cfg,monkeypatch):
    teacher_action=np.array([1,0,0,0,0,0,0,0],np.float32)
    class Teacher:
        def reset(self,state,agent,rng):pass
        def act(self,state):return teacher_action.copy()
    class Student:
        def __init__(self,path):pass
        def action(self,obs):return nearest_action(-teacher_action)
    monkeypatch.setattr(data,'make_opponent',lambda name:Teacher())
    monkeypatch.setattr(data,'FrozenActor',Student)
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg))
    output=tmp_path/'corrections.npz'
    result=data.collect(Namespace(config=str(config),replay_bank=None,opponent='scripted,scorer',teacher='scripted',
        samples=160,out=str(output),seed=31,label_mode='final_executed',student_model='unused',student_prefix_fraction=1.))
    assert result['prefix_episodes']>0 and result['prefix_decisions']>0
    assert all(n>0 for n in result['kept_by_opponent'].values())
    with np.load(output) as z:
        # Student attempts provide states; only the frozen teacher supplies labels.
        np.testing.assert_array_equal(ACTIONS[z['actions']],np.repeat(teacher_action[None,:],len(z['actions']),axis=0))


def test_upgrade_preserves_student_and_validation_and_is_idempotent(tmp_path,monkeypatch):
    monkeypatch.setattr(imitation,'ROOT',tmp_path)
    monkeypatch.setattr(imitation,'check_model',lambda path:{'sha256':'a'*64})
    run=tmp_path/'runs/copy02';run.mkdir(parents=True)
    config={'copy':dict(history_free=True,epochs=10,lr=.0003)}
    selected=dict(path='published.zip',sha256='a'*64,timesteps=250000)
    state=dict(published=selected,best=selected,resume=dict(path='overfit.zip'),phase='fit',epoch=6,
               shards=[{'path':'old.npz'}],validation_shards=[{'path':'fixed.npz'}],history=[{'epoch':6}],round=9)
    (run/'config.json').write_text(json.dumps(config));(run/'copy_state.json').write_text(json.dumps(state))
    args=Namespace(run='copy02');imitation.upgrade_copy(args)
    upgraded=json.loads((run/'copy_state.json').read_text());new_cfg=json.loads((run/'config.json').read_text())
    assert upgraded['resume']==selected and upgraded['published']==selected
    assert upgraded['shards']==[] and upgraded['archived_shards_v152']==state['shards']
    assert upgraded['validation_shards']==state['validation_shards'] and upgraded['history']==state['history']
    assert upgraded['phase']=='collection' and upgraded['epoch']==0 and upgraded['round']==9
    assert new_cfg['copy']['epochs']==2 and new_cfg['copy']['lr']==.0001
    assert json.loads((run/'copy_upgrade_v152_backup.json').read_text())==dict(config=config,state=state)
    before=(run/'copy_state.json').read_bytes();imitation.upgrade_copy(args)
    assert (run/'copy_state.json').read_bytes()==before


def test_goal_screening_separates_goals_without_student_contact():
    from nova.evaluation import summarize
    rows=[dict(outcome=1,touches=t,timeout=False,practice_success=False) for t in [0,2]]
    summary=summarize(rows)
    assert summary['first_goal_wins']==2 and summary['wins_with_student_contact']==1
    assert summary['wins_without_student_contact']==1 and summary['contact_score_fraction']==.5


def test_selection_does_not_reward_zero_touch_goals(tmp_path,monkeypatch):
    def record(name):return dict(path=name,sha256=name[0]*64,timesteps=1)
    state=dict(best=record('lucky.zip'),best_validation={'balanced_loss':.1},resume=record('contact.zip'),
        history=[{'validation':{'balanced_loss':.3}}])
    monkeypatch.setattr(imitation,'load_ppo',lambda path:path.name)
    def probe(model,*args):
        return dict(trials=10,contact_fraction=.5,score_fraction=.9 if model=='lucky.zip' else .1,
                    contact_score_fraction=0. if model=='lucky.zip' else .1,concede_fraction=0.)
    monkeypatch.setattr(imitation,'student_probe',probe)
    imitation.publish_by_probe(None,tmp_path,state,{},tmp_path/'STOP')
    assert state['published']['path']=='contact.zip'
