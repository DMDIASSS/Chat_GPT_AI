import copy,json
from pathlib import Path
import numpy as np
import pytest
import torch
from attentionforge import _attention_native as n
from attentionforge.runtime import batch,config,save_checkpoint,sha
from attentionforge.model import ActorCritic
from attentionforge.observation import ACTIONS
from attentionforge.offense import setup,evaluate,pin_candidate
from attentionforge.gpu_profile import model_hash
from test_contracts import native as needs_meshes


def cfg():
    c=config('laptop_config.json');c['rewards'].update(profile='attack_v1',goal=20.,touch=.1,approach=.3);return c


def test_shot_quality_is_bounded_and_prefers_goal_mouth_over_aiming_at_posts():
    assert n.attack_shot_quality(0,0,94,0,2000,0,0)>.8
    assert n.attack_shot_quality(0,0,94,1200,2000,0,0)<.01
    assert n.attack_shot_quality(0,0,1500,0,2000,1800,0)<.01
    assert n.attack_shot_quality(0,0,94,0,-2000,0,0)==0
    rng=np.random.default_rng(749)
    for _ in range(100):
        p=rng.uniform([-3000,-4500,94],[3000,4500,1700]);v=rng.uniform(-3000,3000,3)
        a=n.attack_shot_quality(*p,*v,0);p[:2]*=-1;v[:2]*=-1;b=n.attack_shot_quality(*p,*v,1)
        assert np.isfinite(a) and 0<=a<=1 and a==pytest.approx(b,abs=1e-6)


def frame(pos=(0,0,17),vel=(0,0,0),forward=(1,0,0),ground=True,jumped=False):
    x=np.zeros(32,np.float32);x[:3]=pos;x[3:6]=vel;x[9:12]=forward;x[12:15]=[0,0,1];x[16]=ground;x[17]=jumped;return x.tolist()


def test_jump_reward_requires_elevated_target_and_is_not_paid_for_holding_jump():
    for ball,expected in [([600,0,350],True),([600,0,94],False),([-600,0,350],False)]:
        t=n.MoveTrace();t.probe(frame(),ball,False,0)
        r=t.probe(frame(pos=(0,0,30),vel=(300,0,300),ground=False,jumped=True),ball,False,1)
        assert bool(r[0]>0)==expected
        assert t.probe(frame(pos=(20,0,45),vel=(300,0,280),ground=False,jumped=True),ball,False,2)[0]==0


def test_useful_flip_needs_acceleration_toward_ball_and_cooldown():
    t=n.MoveTrace();ball=[1500,0,94];t.probe(frame(vel=(500,0,0),ground=False,jumped=True),ball,False,0)
    r=t.probe(frame(vel=(1000,0,0),ground=False,jumped=True),ball,True,1);assert r[1]>.1
    assert t.probe(frame(vel=(1050,0,0),ground=False,jumped=True),ball,True,2)[1]==0
    t2=n.MoveTrace();t2.probe(frame(vel=(500,0,0),ground=False,jumped=True),ball,False,0)
    assert t2.probe(frame(vel=(-500,0,0),ground=False,jumped=True),ball,True,1)[1]==0


def test_recovery_needs_backflip_and_completed_upright_forward_motion():
    ball=[-1600,0,94];t=n.MoveTrace();t.probe(frame(vel=(-700,0,0)),ball,False,0)
    t.probe(frame(pos=(0,0,30),vel=(-700,0,300),ground=False,jumped=True),ball,False,1)
    t.probe(frame(pos=(-10,0,100),vel=(-1200,0,200),ground=False,jumped=True),ball,True,12)
    r=t.probe(frame(pos=(-500,0,17),vel=(-1000,0,0),forward=(-1,0,0)),ball,False,130)
    assert r[2]==pytest.approx(.3)
    assert t.probe(frame(pos=(-510,0,17),vel=(-1000,0,0),forward=(-1,0,0)),ball,False,131)[2]==0
    t=n.MoveTrace();t.probe(frame(vel=(-700,0,0)),ball,False,0)
    t.probe(frame(vel=(-700,0,300),ground=False,jumped=True),ball,False,1)
    assert t.probe(frame(vel=(-700,0,0),forward=(-1,0,0)),ball,False,130)[2]==0


@needs_meshes
def test_kickoff_variants_have_exact_mirrored_poses_and_equal_boost_after_resets():
    c=cfg();e=batch(c,n=2,kickoffs=True)
    expected=[(0,-4608),(-2048,-2560),(2048,-2560),(-256,-3840),(256,-3840)]
    for k,(x,y) in enumerate(expected):
        e.scenario(k);w=e.observe()['world'];np.testing.assert_allclose(w[:,1,:2],np.tile([x,y],(2,1)));np.testing.assert_allclose(w[:,2,:2],np.tile([-x,-y],(2,1)))
        np.testing.assert_allclose(w[:,1:,15],33);assert e.inspect(0)['scenario_id']==k


@needs_meshes
def test_goal_mouth_proxy_matches_simple_physical_scoring_and_wide_miss():
    for vx,should_score in [(0,True),(1200,False)]:
        e=batch(cfg(),n=1,kickoffs=True);w=e.observe()['world'][0];w[0,:3]=[0,3000,94];w[0,3:6]=[vx,2000,0];w[1,:3]=[-3000,-3000,17];w[2,:3]=[3000,-3000,17];e.set_ground(0,w)
        scored=False
        for _ in range(25):
            r=e.step(np.full((1,2),8,np.int64));scored|=bool(r['terminated'][0])
            if scored:break
        assert scored==should_score


@needs_meshes
def test_attack_profile_changes_rewards_without_changing_forced_scene_physics():
    a=batch(cfg(),n=2,seed=76123,kickoffs=True);c=cfg();c['rewards']['profile']='skills_v1';b=batch(c,n=2,seed=76123,kickoffs=True)
    for env in (a,b):env.scenario(0)
    rng=np.random.default_rng(19)
    for _ in range(80):
        ac=rng.integers(0,90,(2,2),dtype=np.int64);x=a.step(ac);y=b.step(ac);np.testing.assert_array_equal(x['world'],y['world'])
        assert x['attack_info'].shape==(2,10) and np.isfinite(x['rewards']).all()


def test_fork_preserves_actor_optimizer_parent_and_refuses_unknown_existing_folder(tmp_path):
    c=config('laptop_config.json');c['rewards']['profile']='skills_v1';c['network']['critic_detach']=True;c['skills']={'auxiliary_initial':.1,'auxiliary_decay_transitions':10000000,'auto_evaluate_every':250000}
    m=ActorCritic(**c['network']);o=torch.optim.Adam(m.parameters(),lr=.00002)
    data={'model':m.state_dict(),'config':c,'optimizer':o.state_dict(),'learning_transitions':13148160,'updates':227,'history':[],'wandb_id':'old'}
    p=tmp_path/'skills01';p.mkdir();save_checkpoint(p/'latest.pt',data);before=sha(p/'latest.pt');target=tmp_path/'attack01';setup(p,target)
    out=torch.load(target/'latest.pt',weights_only=False);assert model_hash(out['model'])==model_hash(data['model'])
    assert out['optimizer']['param_groups']==data['optimizer']['param_groups'];assert out['wandb_id'] is None and out['config']['attack']['start_learning_transitions']==13148160
    assert sha(target/'reward_parent.pt')==before and sha(p/'latest.pt')==before
    setup(p,target) # idempotent resume, no overwrite
    bad=tmp_path/'unknown';bad.mkdir()
    with pytest.raises(FileExistsError):setup(p,bad)


@needs_meshes
def test_identical_actors_get_half_score_in_each_context_and_pins_survive_later_evals(tmp_path):
    c=cfg();c['network']={'width':32,'heads':4,'blocks':1};c['device']='cpu';c['torch_threads']=1
    model=ActorCritic(**c['network']);payload={'model':model.state_dict(),'config':c,'learning_transitions':100}
    save_checkpoint(tmp_path/'latest.pt',payload);save_checkpoint(tmp_path/'reward_parent.pt',payload)
    result=evaluate(tmp_path,games_per_context=4,seconds=2,seed=1817233,contexts=('center','diagonal_left','open_play'))
    assert all(v['score_rate']==.5 for v in result['contexts'].values())
    assert result['macro_score_rate']==.5 and len(result['games'])==12
    best=json.loads((tmp_path/'match_best.json').read_text());pin=tmp_path/best['open_play']['actor_path'];before=sha(pin)
    result['contexts']['open_play']['score_rate']=.4;pin_candidate(tmp_path,result,Path('later.json'))
    assert pin.exists() and sha(pin)==before


def index(p=0,r=0,j=0):
    target=np.array([0,0,p,0,r,j,0,int(bool(j and (p or r)))],np.float32)
    return int(np.flatnonzero(np.all(ACTIONS==target,axis=1))[0])


@needs_meshes
def test_actual_half_flip_is_rewarded_once_by_physics_detector():
    e=batch(cfg(),n=1,kickoffs=True);w=e.observe()['world'][0]
    w[0,:3]=[0,-2600,94];w[0,3:6]=0;w[1,:3]=[0,0,17];w[1,3:6]=[0,-800,0];w[1,9:12]=[0,1,0];w[1,12:15]=[0,0,1];w[2,:3]=[3000,3000,17];w[2,3:6]=0;e.set_ground(0,w)
    total=0
    # A controlled demonstration tests the detector; it is never called by a policy.
    for k in range(50):
        a=8
        if 1<=k<3:a=index(j=1)
        elif 4<=k<8:a=index(p=1,j=1)
        elif 8<=k<14:a=index(p=-1,r=1)
        elif 14<=k<22:a=index(r=1)
        raw=e.step(np.array([[a,8]],np.int64));total+=raw['attack_info'][0,3]
    assert total==pytest.approx(.3,abs=1e-5)


@needs_meshes
def test_elevated_ball_contact_bonus_is_earned_by_actual_jump_not_air_time_alone():
    totals=[]
    for jump in (False,True):
        e=batch(cfg(),n=1,kickoffs=True);w=e.observe()['world'][0]
        w[0,:3]=[0,400,250];w[0,3:6]=[0,100,300];w[1,:3]=[0,0,17];w[1,3:6]=[0,600,0];w[1,9:12]=[0,1,0];w[1,12:15]=[0,0,1];w[2,:3]=[3000,3000,17];w[2,3:6]=0;e.set_ground(0,w)
        score=0
        for k in range(18):
            a=index(j=1) if jump and 1<=k<5 else 8
            raw=e.step(np.array([[a,8]],np.int64));score+=raw['attack_info'][0,4]
        totals.append(score)
    assert totals[0]==0 and totals[1]>0


@needs_meshes
def test_pin_uses_evaluated_snapshot_even_if_latest_changes(tmp_path):
    from attentionforge.offense import selected_pin
    c=cfg();c['network']={'width':32,'heads':4,'blocks':1};c['device']='cpu';c['torch_threads']=1
    m=ActorCritic(**c['network']);old={'model':m.state_dict(),'config':c,'learning_transitions':10};save_checkpoint(tmp_path/'latest.pt',old);save_checkpoint(tmp_path/'reward_parent.pt',old)
    result=evaluate(tmp_path,games_per_context=4,seconds=1,seed=501281,contexts=('open_play',))
    snapshot=torch.load(tmp_path/'latest.pt',weights_only=False)
    for tensor in snapshot['model'].values():
        if torch.is_floating_point(tensor):tensor.add_(.1)
    snapshot['learning_transitions']=20;save_checkpoint(tmp_path/'latest.pt',snapshot)
    result['contexts']['open_play']['score_rate']=.75;result['macro_score_rate']=.75
    with pytest.raises(ValueError):pin_candidate(tmp_path,result,Path('late.json'))
    pin_candidate(tmp_path,result,Path('correct_snapshot.json'),payload=old)
    selected=selected_pin(tmp_path,'open_play');kept=torch.load(selected,weights_only=False)
    assert kept['learning_transitions']==10 and model_hash(kept['model'])==result['candidate_actor_state_sha256']


@needs_meshes
def test_training_rehearsal_uses_only_physics_successes_and_legal_actions():
    from attentionforge.movement_school import collect
    data,record=collect(cfg())
    assert data is not None and all(x['successful_arenas']>0 for x in record.values())
    x,l,y=data;assert x.shape[1:]==(43,40) and np.isfinite(x).all()
    assert np.take_along_axis(l,y[:,None],axis=1).all()
    # These sources are the only deployment adapters; neither invokes the tutor.
    root=Path(__file__).resolve().parents[1]
    for name in ('rlbot4_agent.py','rlbot5_agent.py'):
        assert 'movement_school' not in (root/'attentionforge'/name).read_text()


@needs_meshes
def test_isolated_probes_do_not_report_scripted_moves_for_noop_network():
    from attentionforge.offense import skill_probes
    class Noop(torch.nn.Module):
        def __init__(self):super().__init__();self.p=torch.nn.Parameter(torch.zeros(()))
        def forward(self,x,l):
            z=torch.full((len(x),90),-100.);z[:,8]=1.;return z,torch.zeros(len(x))
    m=Noop();result=skill_probes(m,cfg(),n=4,seconds=2)
    for task,row in result['tasks'].items():
        assert row['jump_used_fraction']==0 and row['air_contact_fraction']==0 and row['backflip_recovery_fraction']==0 and row['useful_flip_fraction']==0
    assert result['tasks']['finishing']['goal_fraction']==0 and m.training
