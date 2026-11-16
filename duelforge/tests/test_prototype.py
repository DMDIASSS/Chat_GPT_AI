import copy,importlib.util,json,math,os,subprocess,sys,zipfile
from pathlib import Path
from types import SimpleNamespace as S
import numpy as np
import pytest,torch
from duelforge.runtime import config,batch,save,load,sha,lock
from duelforge.observation import ACTIONS,encode
from duelforge.train import gae,train
from duelforge.model import ActorCritic
from duelforge import _native


def small():
    c=config();c.update(device='cpu',n_envs=4,torch_threads=1,width=32);c['ppo'].update(steps=8,epochs=1,batch_size=32);c['wandb']['enabled']=False;c['league']['snapshot_every']=32;c['auto_evaluate_every']=10**9;return c


def test_action_and_native_encoder_parity_including_air_and_spent_flips():
    np.testing.assert_array_equal(ACTIONS,_native.action_table());c=small();e=batch(c,n=4);rng=np.random.default_rng(19)
    for _ in range(120):
        r=e.observe();a,l=encode(r['world'],r['pads'],e.pad_locations());np.testing.assert_allclose(a,r['obs'],atol=2e-6,rtol=2e-6);np.testing.assert_array_equal(l,r['mask']);assert l.any(-1).all()
        ac=np.array([[rng.choice(np.flatnonzero(m)) for m in row] for row in l]);e.step(ac)


def test_rng_does_not_depend_on_worker_count():
    c=small();a=batch(c,n=8,seed=9827);c['native_threads']=3;b=batch(c,n=8,seed=9827);rng=np.random.default_rng(9)
    for _ in range(90):
        ac=rng.integers(0,90,(8,2),dtype=np.int64);x=a.step(ac);y=b.step(ac)
        for name in ('obs','world','rewards','info'):np.testing.assert_array_equal(x[name],y[name])


def test_kickoff_symmetry_equal_boost_all_five_variants():
    e=batch(small(),n=3)
    for scene in range(5):
        e.scene(scene);w=e.observe()['world'];np.testing.assert_allclose(w[:,1,:2],-w[:,2,:2]);np.testing.assert_allclose(w[:,1:,15],33);assert np.any(np.abs(w[:,1,:2])>1000)


def test_delay_holds_old_controls_and_exact_remaining_tick_budget():
    e=batch(small(),n=1);e.scene(0);r=e.step(np.array([[16,8]],np.int64),np.array([7],np.int64));assert r['info'][0,3]==7;np.testing.assert_array_equal(r['world'][0,1,21:29],0)
    e.scene(0);r=e.step(np.array([[16,8]],np.int64));np.testing.assert_array_equal(r['world'][0,1,21:29],ACTIONS[16]);assert r['info'][0,3]==8
    r=e.step(np.array([[16,8]],np.int64),np.array([0],np.int64));assert r['info'][0,3]==0;np.testing.assert_array_equal(r['rewards'],0)


def test_native_reward_parts_match_reference_goals_contacts_and_timeouts():
    from tools.reward_reference import components
    c=small();e=batch(c,n=4,seconds=1);prev=e.observe()['world'];rng=np.random.default_rng(2);seen_timeout=False
    for _ in range(60):
        r=e.step(rng.integers(0,90,(4,2),dtype=np.int64));w=r['final_world'];g=r['info'][:,0]
        for j in range(4):
            ref=components(prev[j,0,:3],w[j,0,:3],prev[j,0,3:6],w[j,0,3:6],r['info'][j,1:3]>0,None if g[j]==0 else 0 if g[j]>0 else 1,gamma=c['ppo']['gamma'],terminal=bool(r['terminated'][j]),impulse_weight=.05)
            expected=np.array([[d['goal'],d['goal_potential'],d['touch_impulse']] for d in ref]);np.testing.assert_allclose(r['reward_parts'][j],expected,atol=3e-7,rtol=1e-4)
        np.testing.assert_allclose(r['rewards'],r['reward_parts'].sum(-1),atol=1e-7);seen_timeout|=bool(r['truncated'].any());prev=r['world']
    assert seen_timeout


def test_goal_terminal_retains_final_state_then_resets():
    e=batch(small(),n=1);e.scene(0);w=e.observe()['world'][0];w[0,:3]=[0,5050,94];w[0,3:6]=[0,2500,0];w[1,:3]=[-3000,-3000,17];w[2,:3]=[3000,-3000,17];e.inject(0,w)
    for _ in range(10):
        r=e.step(np.full((1,2),8,np.int64))
        if r['terminated'][0]:break
    assert r['terminated'][0];np.testing.assert_array_equal(r['reward_parts'][0,:,0],[1,-1]);assert r['final_world'][0,0,1]>5120 and abs(r['world'][0,0,1])<1


def test_gae_distinct_timeout_rows_goals_and_rollout_tail():
    r=np.array([[[1.,2.]],[[3.,4.]],[[5.,6.]]],np.float32);v=np.zeros_like(r);te=np.zeros_like(r,bool);tr=te.copy();tr[0,0,0]=True;tr[1,0,1]=True;te[2,0,0]=True;tv=np.zeros_like(r);tv[0,0,0]=10;tv[1,0,1]=100
    a,ret=gae(r,v,np.array([[7.,9.]],np.float32),te,tr,tv,.9,0.)
    np.testing.assert_allclose(a,[[[10,2]],[[3,94]],[[5,14.1]]],atol=1e-5)
    a,_=gae(np.zeros((2,1,1),np.float32),np.zeros((2,1,1),np.float32),np.ones((1,1),np.float32),np.zeros((2,1,1),bool),np.zeros((2,1,1),bool),np.zeros((2,1,1),np.float32),1.,1.)
    np.testing.assert_array_equal(a,1)


def test_train_resume_history_rows_excluded_and_checkpoint_really_resumes(tmp_path):
    c=small();c['league']['history_fraction']=.5;c['episode_seconds']=.2;c['no_touch_seconds']=.2
    folder=tmp_path/'run';train(folder,cfg=c,minutes=1,max_updates=3);first=load(folder/'latest.pt');identity=sha(folder/'initial.pt')
    assert first['learning_transitions']<3*8*4*2 and first['optimizer_examples']>=first['learning_transitions'];assert len(first['history'])<=c['league']['max_history']
    train(folder,minutes=1,max_updates=1);second=load(folder/'latest.pt');assert second['updates']==first['updates']+1 and second['learning_transitions']>first['learning_transitions'];assert sha(folder/'initial.pt')==identity
    for state in second['optimizer']['state'].values():assert torch.isfinite(state['exp_avg']).all()
    changed=copy.deepcopy(c);changed['rewards']['impulse']=0
    with pytest.raises(ValueError):train(folder,changed,minutes=1,max_updates=1)


def test_run_lock_excludes_second_trainer(tmp_path):
    with lock(tmp_path):
        with pytest.raises(RuntimeError):
            with lock(tmp_path):pass


def test_snapshot_loader_does_not_consume_global_torch_rng(tmp_path):
    from duelforge.runtime import model
    c=small();m=ActorCritic(32);save(tmp_path/'latest.pt',{'model':m.state_dict(),'config':c,'learning_transitions':0});before=torch.get_rng_state();model(tmp_path);torch.testing.assert_close(torch.get_rng_state(),before)


def test_evaluation_identical_models_balanced_colors_exact_time_and_pin(tmp_path):
    from duelforge.evaluate import evaluate
    c=small();m=ActorCritic(32);payload={'model':m.state_dict(),'config':c,'learning_transitions':100};save(tmp_path/'latest.pt',payload);save(tmp_path/'initial.pt',payload)
    out=evaluate(tmp_path,4,1.13,seed=9911,contexts=['center','open_play']);assert out['overall']['score_rate']==.5;assert len(out['games'])==8;assert all(x['seconds']==round(1.13*120)/120 for x in out['games']);assert out['overall']['score_interval_95'][0]<.5<out['overall']['score_interval_95'][1]
    best=json.loads((tmp_path/'validation_best.json').read_text());p=tmp_path/best['actor_path'];assert p.is_file() and sha(p)==best['actor_sha256'];before=sha(p);payload['learning_transitions']=200;save(tmp_path/'latest.pt',payload);assert sha(p)==before


def test_confidence_uses_seed_blocks_and_handles_all_draws():
    from duelforge.evaluate import summary
    rows=[{'context':'match','pair':i,'color':c,'outcome':0,'goals_for':0,'goals_against':0} for i in range(30) for c in (0,1)]
    s=summary(rows);assert s['score_rate']==.5 and s['score_interval_95'][0]<.5<s['score_interval_95'][1]
    rows=[{'context':'match','pair':i//2,'color':i%2,'outcome':1 if i<1100 else -1,'goals_for':1 if i<1100 else 0,'goals_against':0 if i<1100 else 1} for i in range(2000)]
    assert summary(rows)['score_interval_95'][0]>.5


def test_watch_creates_actual_frame_record_and_safe_inspector(tmp_path):
    from duelforge.watch import watch
    c=small();m=ActorCritic(32);payload={'model':m.state_dict(),'config':c,'learning_transitions':10};save(tmp_path/'latest.pt',payload);save(tmp_path/'initial.pt',payload)
    out=watch(tmp_path,seconds=2,frames=20,headless=True);assert (out/'inspect.html').is_file() and (out/'contact_diagnostics.json').is_file()
    with np.load(out/'frames.npz',allow_pickle=False) as d:
        assert d['world'].shape==(20,3,32);assert d['actions'].shape==(20,2);assert d['obs_blue'].shape==(20,109);assert np.isfinite(d['world']).all()
    text=(out/'inspect.html').read_text();assert 'application/json' in text and 'Ball angular velocity' in text and 'window.fetch' not in text


def test_export_source_script_action_agreement_sdk_load_and_immutable_output(tmp_path):
    from duelforge.export import export
    c=small();m=ActorCritic(32);payload={'model':m.state_dict(),'config':c,'learning_transitions':371991};save(tmp_path/'latest.pt',payload)
    out=export(tmp_path);meta=json.loads((out/'identity.json').read_text());assert meta['action_agreement']==1 and meta['source_export_logits_max_abs_difference']==0
    assert (out/'bot.portable.bot.toml').is_file() and (out/'actor.pt').is_file() and (out/'actor.lt').is_file()
    pytest.importorskip('rlbot')
    result=subprocess.run([sys.executable,str(out/'run_v5.py'),'--diagnose'],capture_output=True,text=True,timeout=30);assert result.returncode==0,result.stdout+result.stderr
    with pytest.raises(FileExistsError):export(tmp_path)


def test_nexto_vector_features_and_actions_match_pinned_upstream():
    from duelforge.nexto import ROOT,FILES,observations,Nexto
    path=ROOT/'assets/nexto';source=path/'nexto_obs.py'
    if not source.exists():pytest.skip('Optional pinned Nexto assets not installed')
    assert sha(source)==FILES['nexto_obs.py'][1]
    text='from __future__ import annotations\n'+source.read_text();text=text.replace('from rlgym_compat.common_values import BLUE_TEAM, ORANGE_TEAM','BLUE_TEAM=0\nORANGE_TEAM=1').replace('from rlgym_compat.game_state import GameState, PlayerData','')
    scope={};exec(compile(text,str(source),'exec'),scope)
    e=batch(small(),n=8);raw=e.observe();loc=e.pad_locations()
    for _ in range(5):raw=e.step(np.full((8,2),16,np.int64))
    def phys(c,invert=False):
        sg=np.array([-1,-1,1] if invert else [1,1,1]);f=c[9:12]*sg;u=c[12:15]*sg;return S(position=c[:3]*sg,linear_velocity=c[3:6]*sg,angular_velocity=c[6:9]*sg,rotation_mtx=lambda:np.column_stack((f,np.cross(u,f),u)))
    states=[]
    for w,p in zip(raw['world'],raw['pads']):states.append(S(blue_score=0,orange_score=0,boost_pads=p[:,0],ball=phys(w[0]),inverted_ball=phys(w[0],True),players=[S(car_id=a+1,team_num=a,car_data=phys(w[a+1]),inverted_car_data=phys(w[a+1],True),is_demoed=bool(w[a+1,20]),on_ground=bool(w[a+1,16]),ball_touched=False,has_flip=bool(w[a+1,29]),boost_amount=w[a+1,15]/100) for a in (0,1)]))
    field=S(boost_pads=[S(location=S(x=x,y=y,z=z),is_full_boost=bool(big)) for x,y,z,big in loc],num_boosts=34)
    builder=scope['NextoObsBuilder'](field_info=field);encoded=np.array([scope['encode_gamestate'](s) for s in states]);up=builder.batched_build_obs(encoded);builder.add_actions(up,[raw['world'][:,a+1,21:29] for a in (0,1)])
    net=Nexto()
    for color in (0,1):
        ours=observations(raw['world'],raw['pads'],loc,color)
        for a,b in zip(ours,up[color]):np.testing.assert_allclose(a,b,atol=2e-6,rtol=2e-6)
        with torch.inference_mode():
            x=net.model(tuple(torch.from_numpy(a) for a in ours));y=net.model(tuple(torch.as_tensor(a,dtype=torch.float32) for a in up[color]))
        torch.testing.assert_close(x[0],y[0],rtol=1e-4,atol=2e-5);assert torch.equal(x[0].argmax(-1),y[0].argmax(-1))


def packet_from_world(world,pads,locations,frame=0,phase=None):
    from rlbot.flat import GamePacket,PlayerInfo,BallInfo,BoostPadState,Physics,Vector3,Rotator,MatchInfo,AirState,MatchPhase
    def physics(c):
        f=c[9:12];up=c[12:15];right=np.cross(up,f);pitch=math.asin(np.clip(f[2],-1,1));yaw=math.atan2(f[1],f[0]);roll=math.atan2(-right[2],up[2])
        return Physics(location=Vector3(*map(float,c[:3])),velocity=Vector3(*map(float,c[3:6])),angular_velocity=Vector3(*map(float,c[6:9])),rotation=Rotator(pitch,yaw,roll))
    players=[]
    for a,c in enumerate(world[1:]):players.append(PlayerInfo(physics=physics(c),team=a,boost=float(c[15]),air_state=AirState.OnGround if c[16] else AirState.InAir,has_jumped=bool(c[17]),has_double_jumped=bool(c[18]),has_dodged=False,dodge_timeout=max(0.,1.25-float(c[30])) if c[17] else -1.,is_supersonic=bool(c[19]),demolished_timeout=1. if c[20] else 0.))
    boosts=[BoostPadState(is_active=bool(p[0]),timer=0. if p[0] else max(0.,(10 if locations[j,3] else 4)-float(p[1]))) for j,p in enumerate(pads)]
    return GamePacket(players=players,balls=[BallInfo(physics=physics(world[0]))],boost_pads=boosts,match_info=MatchInfo(frame_num=frame,seconds_elapsed=frame/120,match_phase=phase or MatchPhase.Active))


def test_real_v5_sdk_packet_to_native_feature_action_parity_with_cooldown_conversion():
    pytest.importorskip('rlbot');from duelforge.rlbot5_agent import packet_observation
    e=batch(small(),n=1);e.scene(0);r=e.observe();loc=e.pad_locations();rng=np.random.default_rng(19);actor=ActorCritic(32).eval()
    for k in range(50):
        if k:r=e.step(rng.integers(0,90,(1,2),dtype=np.int64))
        packet=packet_from_world(r['world'][0],r['pads'][0],loc,frame=k*8)
        for a in (0,1):
            x,l=packet_observation(packet,a,loc,r['world'][0,a+1,21:29]);# Rotator -> matrix roundtrip near a vertical car costs ~8e-6 in FP32 features.
            np.testing.assert_allclose(x[0],r['obs'][0,a],atol=1e-5,rtol=1e-5);np.testing.assert_array_equal(l[0],r['mask'][0,a])
            with torch.inference_mode():
                p,_=actor(torch.from_numpy(x),torch.from_numpy(l));q,_=actor(torch.from_numpy(r['obs'][:,a]),torch.from_numpy(r['mask'][:,a]));torch.testing.assert_close(p,q,atol=1e-5,rtol=1e-4);assert torch.equal(p.argmax(-1),q.argmax(-1))


def test_v5_clock_duplicate_frames_seven_tick_delay_and_match_reset():
    pytest.importorskip('rlbot');from duelforge.rlbot5_agent import PolicyClock
    from rlbot.flat import MatchPhase
    class Fixed(torch.nn.Module):
        def forward(self,x,l):
            logits=torch.full((len(x),90),-100.);logits[:,16]=100.;return logits,torch.zeros(len(x))
    e=batch(small(),n=1);e.scene(0);r=e.observe();loc=e.pad_locations();clock=PolicyClock(Fixed(),config(),loc)
    for frame in range(7):
        packet=packet_from_world(r['world'][0],r['pads'][0],loc,frame=frame);np.testing.assert_array_equal(clock.controls(packet,0),0)
    packet=packet_from_world(r['world'][0],r['pads'][0],loc,frame=7);np.testing.assert_array_equal(clock.controls(packet,0),ACTIONS[16]);clock.controls(packet,0);assert clock.decisions==1
    packet=packet_from_world(r['world'][0],r['pads'][0],loc,frame=8);clock.controls(packet,0);assert clock.decisions==2
    packet=packet_from_world(r['world'][0],r['pads'][0],loc,frame=0,phase=MatchPhase.Kickoff);np.testing.assert_array_equal(clock.controls(packet,0),0);assert clock.decisions==1


def test_v5_boost_elapsed_timer_converts_to_native_remaining_cooldown():
    pytest.importorskip('rlbot');from duelforge.rlbot5_agent import packet_observation
    e=batch(small(),n=1);r=e.observe();locations=e.pad_locations();r['pads'][0,:,0]=0;r['pads'][0,:,1]=np.where(locations[:,3]>.5,7.75,2.25)
    native,mask=_native.encode(r['world'],r['pads'],locations);packet=packet_from_world(r['world'][0],r['pads'][0],locations)
    for a in (0,1):
        x,l=packet_observation(packet,a,locations,r['world'][0,a+1,21:29]);np.testing.assert_allclose(x,native[:,a],atol=1e-6);np.testing.assert_array_equal(l,mask[:,a])


def test_fork_preserves_parent_and_fails_atomically_on_missing_history(tmp_path):
    from duelforge.cli import fork
    c=small();parent=tmp_path/'parent';train(parent,c,minutes=1,max_updates=1);identity=sha(parent/'latest.pt')
    target=tmp_path/'nested'/'child';fork(parent,target)
    assert sha(parent/'latest.pt')==identity and sha(target/'fork_parent.pt')==identity
    a,b=load(parent/'latest.pt'),load(target/'latest.pt')
    assert a['learning_transitions']==b['learning_transitions'] and a['updates']==b['updates']
    for k in a['model']:torch.testing.assert_close(a['model'][k],b['model'][k])
    a['history']=['missing.pt'];save(parent/'latest.pt',a)
    with pytest.raises(FileNotFoundError):fork(parent,tmp_path/'incomplete')
    assert not (tmp_path/'incomplete').exists() and not list(tmp_path.glob('.fork_*'))


def test_pilot_pause_routes_to_active_run_and_stops_further_blocks(tmp_path,monkeypatch):
    import duelforge.pilot as pilot
    import duelforge.cli as cli
    import duelforge.train as training
    import duelforge.evaluate as evaluation
    monkeypatch.setattr(pilot,'ROOT',tmp_path);monkeypatch.setattr(cli,'ROOT',tmp_path);calls=[]
    def bounded_train(folder,cfg,minutes):
        calls.append(folder.name);folder.mkdir(parents=True);cli.pause(tmp_path/'unused')
    def unexpected_eval(*args,**kwargs):raise AssertionError('Paused pilot must not run evaluation')
    monkeypatch.setattr(training,'train',bounded_train);monkeypatch.setattr(evaluation,'evaluate',unexpected_eval)
    pilot.run_pilot(minutes=.1,block_minutes=.05,seeds=(41011,))
    assert calls==['pilot_41011_impulse_00'] and (tmp_path/'runs'/calls[0]/'STOP').is_file()
    assert json.loads((tmp_path/'experiments/pilot001/active.json').read_text())['status']=='paused_or_complete'


def test_frozen_opponent_allocation_validation():
    from duelforge.runtime import validate
    c=small();c['league']['history_fraction']=.5;c['league']['nexto_fraction']=.5
    with pytest.raises(ValueError):validate(c)
    c['league']['nexto_fraction']=.2;validate(c)
