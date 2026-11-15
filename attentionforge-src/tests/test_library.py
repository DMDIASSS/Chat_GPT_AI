import copy,json,time
from pathlib import Path
from types import SimpleNamespace as S
import numpy as np
import pytest
import torch
from attentionforge.library_rewards import LibraryRewards,PRESET,NAMES,goal_probability
from attentionforge.runtime import batch,config,save_checkpoint,sha
from attentionforge.library import setup
from attentionforge.gpu_profile import model_hash
from attentionforge.model import ActorCritic
from test_contracts import native as needs_meshes


def upstream():
    pytest.importorskip('rlgym_tools')
    from rlgym.rocket_league.reward_functions import GoalReward
    from rlgym_tools.rocket_league.reward_functions.advanced_touch_reward import AdvancedTouchReward
    from rlgym_tools.rocket_league.reward_functions.velocity_player_to_ball_reward import VelocityPlayerToBallReward
    from rlgym_tools.rocket_league.reward_functions.goal_prob_reward import GoalViewReward
    from rlgym_tools.rocket_league.reward_functions.aerial_distance_reward import AerialDistanceReward
    return [GoalReward(),AdvancedTouchReward(touch_reward=.05,acceleration_reward=.5,use_touch_count=False),VelocityPlayerToBallReward(include_negative_values=False),GoalViewReward(gamma=.995),AerialDistanceReward()]


def state(w,tick,hits=(0,0),goal=0):
    cars={a:S(team_num=a,is_blue=a==0,ball_touches=int(hits[a]),physics=S(position=w[a+1,:3].copy(),linear_velocity=w[a+1,3:6].copy())) for a in (0,1)}
    return S(ball=S(position=w[0,:3].copy(),linear_velocity=w[0,3:6].copy()),cars=cars,tick_count=tick,goal_scored=bool(goal),scoring_team=0 if goal>0 else 1)


def world(rng,n=3):
    w=np.zeros((n,3,32));w[:,:,:3]=rng.uniform([-3000,-4500,94],[3000,4500,1500],(n,3,3));w[:,:,3:6]=rng.uniform(-2000,2000,(n,3,3));return w


def test_exact_outputs_against_all_five_upstream_classes_across_hits_goals_and_resets():
    rng=np.random.default_rng(793);w=world(rng);calc=LibraryRewards(w,PRESET,.995)
    refs=[upstream() for _ in w];ticks=np.zeros(len(w),int);weights=[10,1,.2,1,2]
    for j,classes in enumerate(refs):
        for cls in classes:cls.reset([0,1],state(w[j],0),{})
    for step in range(100):
        final=w.copy();final[:,:,:3]+=rng.normal(0,90,(3,3,3));final[:,:,2]=rng.uniform(100,1100,(3,3));final[:,:,3:6]+=rng.normal(0,150,(3,3,3))
        hits=rng.random((3,2))<.3;g=np.array([1 if step%19==0 else 0,-1 if step%23==0 else 0,0]);tr=np.array([False,False,step%17==0]);elapsed=rng.integers(1,9,3);ticks+=elapsed
        # Include landing, consecutive aerial hits and two simultaneous touch labels.
        if step%5==0:final[:,1,2]=17
        nextworld=final.copy();done=(g!=0)|tr;nextworld[done]=world(rng,int(done.sum()))
        info=np.zeros((3,8));info[:,0]=g;info[:,1:3]=hits;info[:,7]=elapsed
        raw={'final_world':final,'world':nextworld,'terminated':g!=0,'truncated':tr,'info':info}
        rewards,parts=calc.step(raw)
        for j,classes in enumerate(refs):
            s=state(final[j],ticks[j],hits[j],g[j]);expect=np.zeros((2,5))
            for k,cls in enumerate(classes):
                r=cls.get_rewards([0,1],s,{0:bool(g[j]),1:bool(g[j])},{0:bool(tr[j]),1:bool(tr[j])},{})
                expect[:,k]=[r[a]*weights[k] for a in (0,1)]
            np.testing.assert_allclose(parts[j],expect,atol=2e-6,rtol=2e-5)
            np.testing.assert_allclose(rewards[j],expect.sum(1),atol=3e-6,rtol=2e-5)
            if done[j]:
                ticks[j]=0
                for cls in classes:cls.reset([0,1],state(nextworld[j],0),{})
        w=nextworld


def test_empty_jumping_and_airtime_without_ball_touches_has_no_aerial_bonus():
    w=world(np.random.default_rng(1),1);calc=LibraryRewards(w,PRESET,.995);final=w.copy();final[:,1:,2]+=500
    r,p=calc.step({'world':final,'final_world':final,'info':np.array([[0,0,0,0,0,0,0,8]]),'terminated':np.array([False]),'truncated':np.array([False])})
    np.testing.assert_array_equal(p[:,:,1],0);np.testing.assert_array_equal(p[:,:,4],0)


def test_goal_view_color_symmetry_and_finite_degenerate_guards():
    w=world(np.random.default_rng(7),500)[:,0,:3];mirrored=w.copy();mirrored[:,:2]*=-1
    np.testing.assert_allclose(goal_probability(mirrored),1-goal_probability(w),atol=1e-10)
    assert np.isfinite(goal_probability(np.array([[801.505,5215.5,91.25]]))).all()
    c=copy.deepcopy(PRESET);c['control_progress']=1
    with pytest.raises(ValueError):LibraryRewards(world(np.random.default_rng(3)),c,.995)


def cfg():
    c=config('laptop_config.json');c['rewards']=copy.deepcopy(PRESET);return c


@needs_meshes
def test_wrapper_preserves_native_physics_and_erases_old_custom_reward_telemetry():
    c=cfg();x=batch(c,n=3,seed=77);base=copy.deepcopy(c);base['rewards']={'profile':'rlgym_simple_v1','goal':0,'approach':0,'touch':0,'control_progress':0};y=batch(base,n=3,seed=77)
    rng=np.random.default_rng(5)
    for k in range(40):
        ac=rng.integers(0,90,(3,2),dtype=np.int64);a=x.step(ac);b=y.step(ac)
        for name in ('world','pads','final_world','terminated','truncated'):np.testing.assert_array_equal(a[name],b[name])
        np.testing.assert_allclose(a['rewards'],a['library_info'].sum(-1),rtol=2e-6,atol=1e-7)
        for name in ('reward_info','skill_info','attack_info'):assert np.all(a[name]==0)
    for name in ('skills','attack'):
        c=cfg();c[name]={'enabled':True}
        with pytest.raises(ValueError):batch(c,n=1)
    c=cfg();c['team_size']=2
    with pytest.raises(ValueError):batch(c,n=1)


@needs_meshes
def test_physical_goal_and_post_reset_reward_use_terminal_state_and_new_initial_state():
    e=batch(cfg(),n=1,seed=417,kickoffs=True);e.scenario(0);w=e.observe()['world'][0]
    w[0,:3]=[0,5050,94];w[0,3:6]=[0,2500,0];w[1,:3]=[-3000,-3000,17];w[2,:3]=[3000,-3000,17];e.set_ground(0,w)
    for _ in range(10):
        r=e.step(np.full((1,2),8,np.int64))
        if r['terminated'][0]:break
    assert r['terminated'][0];np.testing.assert_array_equal(r['library_info'][0,:,0],[10,-10]);assert abs(r['world'][0,0,1])<1
    after=e.step(np.full((1,2),8,np.int64));assert abs(after['library_info'][0,0,3])<1e-5
    np.testing.assert_array_equal(after['library_info'][:,:,1],0)


def test_fork_copies_full_optimizer_and_actor_without_custom_auxiliaries_or_source_changes(tmp_path):
    c=config('laptop_config.json');c['skills']={'auxiliary_initial':.1};c['attack']={'rehearsal':True};m=ActorCritic(**c['network']);o=torch.optim.Adam(m.parameters(),lr=.00002)
    # Real moments and step counts, not just an empty optimizer.
    m.critic.weight.sum().backward();o.step()
    data={'model':m.state_dict(),'config':c,'optimizer':o.state_dict(),'learning_transitions':13000000,'updates':201,'history':[],'wandb_id':'old'}
    source=tmp_path/'skills01';source.mkdir();save_checkpoint(source/'latest.pt',data);before=sha(source/'latest.pt');target=tmp_path/'library01';setup(source,target)
    d=torch.load(target/'latest.pt',weights_only=False);assert model_hash(d['model'])==model_hash(data['model']);assert d['optimizer']['param_groups']==data['optimizer']['param_groups']
    for key,values in data['optimizer']['state'].items():
        for name,tensor in values.items():torch.testing.assert_close(d['optimizer']['state'][key][name],tensor)
    assert config(target/'config.json')==d['config']
    assert not any(k in d['config'] for k in ('skills','attack'));assert d['config']['library']['auxiliary_losses'] is False;assert d['wandb_id'] is None
    assert sha(source/'latest.pt')==before==sha(target/'reward_parent.pt');setup(source,target)
    with pytest.raises(FileExistsError):setup(source,source)


@needs_meshes
def test_library_evaluation_uses_pinned_parent_and_cannot_substitute_changed_weights(tmp_path):
    from attentionforge.offense import evaluate
    c=cfg();c['network']={'width':32,'heads':4,'blocks':1};c['device']='cpu';c['torch_threads']=1
    m=ActorCritic(**c['network']);d={'model':m.state_dict(),'config':c,'learning_transitions':100};save_checkpoint(tmp_path/'latest.pt',d);save_checkpoint(tmp_path/'reward_parent.pt',d)
    from attentionforge.runtime import atomic_json
    atomic_json(tmp_path/'library_provenance.json',{'parent_sha256':sha(tmp_path/'reward_parent.pt')})
    result=evaluate(tmp_path,4,1,seed=77421,contexts=('center','diagonal_left','open_play'));assert result['macro_score_rate']==.5
    d['learning_transitions']=101;save_checkpoint(tmp_path/'reward_parent.pt',d)
    with pytest.raises(ValueError):evaluate(tmp_path,4,1,contexts=('center',))


@needs_meshes
def test_normal_launcher_path_reads_json_and_runs_reward_only_ppo_and_contact_monitor(tmp_path):
    from attentionforge.skills import checkpoint
    from attentionforge.library import run
    c=config('laptop_config.json');c['network']={'width':32,'heads':4,'blocks':1};c['device']='cpu';c['torch_threads']=1;c['n_envs']=2
    c['ppo'].update(steps=8,epochs=1,batch_size=32);c['wandb']['enabled']=False
    m=ActorCritic(**c['network']);o=torch.optim.Adam(m.parameters(),lr=c['ppo']['learning_rate']);payload=checkpoint(m,o,c,0)
    source=tmp_path/'skills01';source.mkdir();save_checkpoint(source/'latest.pt',payload);before=sha(source/'latest.pt');target=tmp_path/'library01';setup(source,target)
    d=torch.load(target/'latest.pt',weights_only=False);d['config']['library']['validation_every']=16
    save_checkpoint(target/'latest.pt',d);(target/'config.json').write_text(json.dumps(d['config']))
    run(target,max_updates=1)
    result=torch.load(target/'latest.pt',weights_only=False);assert result['learning_transitions']==32
    assert (target/'library_initial_contact.json').exists() and (target/'library_validation.jsonl').exists()
    metrics=json.loads((target/'metrics.jsonl').read_text().splitlines()[-1]);assert len([k for k in metrics if k.startswith('reward_library/')])==10
    assert not any(k.startswith(('skills/','attack/')) for k in metrics)
    assert sha(source/'latest.pt')==before
