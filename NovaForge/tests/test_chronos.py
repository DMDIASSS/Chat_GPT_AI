import copy
import json
from pathlib import Path
from argparse import Namespace
import numpy as np
import pytest
import torch
from nova.chronos import CHRONOS_CONTRACT,ChronosEnv,ChronosSnapshot
from nova.chronos_training import new_chronos_model,export_chronos_actor,load_network
from nova.models import save_ppo
from nova.core import check_model
from nova.training import load_config
from nova.environment import ArenaEnv
from nova.giga_teachers import GigaTeacher,TABLE,build_features,native_action_mask


def settings():
    cfg=load_config(Path(__file__).resolve().parents[1]/'configs/chronos.json')
    cfg.update(workers=1,device='cpu');cfg['league']['weights']={'scorer':1.}
    cfg['env'].update(episode_seconds=.2,no_touch_seconds=1)
    cfg['ppo'].update(n_steps=8,batch_size=8,n_epochs=1)
    cfg['chronos']['critic_warmup_updates']=1
    return cfg


@pytest.mark.parametrize('side',[0,1])
def test_pretrained_chronos_policy_and_native_delayed_trajectory_match(side,request):
    if not request.config.getoption('--chronos'):pytest.skip('Use --chronos after fetching actual Chronos assets')
    torch.set_num_threads(1);cfg=settings();cfg['env'].update(episode_seconds=20,no_touch_seconds=21)
    env=ChronosEnv(cfg,opponent='scorer',scenario='kickoff',side=side)
    reference=ArenaEnv(cfg,opponent='scorer',scenario='kickoff',side=side)
    try:
        model=new_chronos_model(cfg,env)
        obs,_=env.reset(seed=233);reference.reset(seed=233)
        teacher=GigaTeacher('chronos');teacher.reset(reference.state,reference.agent,np.random.default_rng(233))
        for _ in range(120):
            action=int(model.predict(obs,deterministic=True)[0]);assert obs[225+action]==1
            obs,_,terminal,truncated,info=env.step(action)
            for _ in range(2):
                _,_,ref_terminal,ref_truncated,ref_info=reference.step_controls(teacher.controls_for_ticks(reference.state))
                if ref_terminal or ref_truncated:break
            assert terminal==ref_terminal and truncated==ref_truncated
            np.testing.assert_array_equal(env.arena.state.ball.position,reference.state.ball.position)
            np.testing.assert_array_equal(env.arena.state.cars[env.arena.agent].physics.position,reference.state.cars[reference.agent].physics.position)
            np.testing.assert_array_equal(env.held,teacher.held)
            if terminal or truncated:
                assert info['outcome']==ref_info['outcome'] and info['touches']==ref_info['touches']
                break
        with torch.no_grad():assert model.policy.anchor_kl(torch.from_numpy(obs)[None,:]).item()==pytest.approx(0,abs=1e-7)
    finally:env.close();reference.close()


def test_critic_warmup_then_real_actor_update_and_checkpoint_roundtrip(tmp_path,monkeypatch):
    from nova.chronos import ChronosPPO
    torch.set_num_threads(1);cfg=settings();env=ChronosEnv(cfg,opponent='scorer',scenario='kickoff')
    try:
        model=new_chronos_model(cfg,env,initialize=False)
        model.policy.anchor.load_state_dict(model.policy.actor.state_dict())
        actor={k:v.clone() for k,v in model.policy.actor.state_dict().items()}
        anchor={k:v.clone() for k,v in model.policy.anchor.state_dict().items()}
        critic={k:v.clone() for k,v in model.policy.value_net.state_dict().items()}
        optimizer_ids={id(p) for group in model.policy.optimizer.param_groups for p in group['params']}
        assert all(id(p) not in optimizer_ids and not p.requires_grad for p in model.policy.anchor.parameters())
        model.learn(8)
        assert all(torch.equal(v,actor[k]) for k,v in model.policy.actor.state_dict().items())
        assert any(not torch.equal(v,critic[k]) for k,v in model.policy.value_net.state_dict().items())
        model.learn(8,reset_num_timesteps=False)
        assert any(not torch.equal(v,actor[k]) for k,v in model.policy.actor.state_dict().items())
        assert all(torch.equal(v,anchor[k]) for k,v in model.policy.anchor.state_dict().items())
        path=tmp_path/'full.zip';save_ppo(model,path,contract=CHRONOS_CONTRACT)
        with pytest.raises(ValueError,match='contract'):check_model(path)
        check_model(path,CHRONOS_CONTRACT)
        loaded=ChronosPPO.load(path,device='cpu')
        assert loaded.chronos_updates==2 and loaded.num_timesteps==16
        assert loaded.actor_lr==model.actor_lr and loaded.anchor_coef==model.anchor_coef
        assert len(loaded.policy.optimizer.state)>0
        obs,_=env.reset(seed=733)
        assert int(loaded.predict(obs,deterministic=True)[0])==int(model.predict(obs,deterministic=True)[0])
        export_chronos_actor(model,tmp_path/'actor.lt')
        snapshot=ChronosSnapshot(tmp_path/'actor.lt');snapshot.reset(env.arena.state,env.arena.agent,np.random.default_rng(1))
        assert snapshot.controls_for_ticks(env.arena.state).shape==(4,8)
        with torch.no_grad():
            x=torch.from_numpy(obs[:225])[None,:]
            torch.testing.assert_close(load_network(tmp_path/'actor.lt')(x),model.policy.actor(x),rtol=0,atol=0)
        # The v5 package must contain distinct combined/native archives on Windows too.
        import tomllib
        from nova import chronos_tools
        run=tmp_path/'runs/export_test';(run/'checkpoints').mkdir(parents=True)
        saved=run/'checkpoints/step_000000000000.zip'
        path.replace(saved);Path(str(path)+'.json').replace(Path(str(saved)+'.json'))
        (run/'latest.json').write_text(json.dumps({'path':str(saved.relative_to(run))}))
        monkeypatch.setattr(chronos_tools,'ROOT',tmp_path)
        chronos_tools.export_chronos(Namespace(run='export_test',initial=False))
        package=next(p for p in (tmp_path/'exports').iterdir() if p.is_dir())
        assert {p.name for p in package.iterdir()}>={'actor.lt','SHARED_HEAD.lt','POLICY.lt','bot.bot.toml','bot.py'}
        assert len({p.name.lower() for p in package.iterdir()})==len(list(package.iterdir()))
        assert tomllib.loads((package/'bot.bot.toml').read_text())['settings']['agent_id'].startswith('DMDIASSS/novachronos_')
    finally:env.close()


def test_live_clock_delays_applies_and_resets_without_loading_weights(cfg):
    from nova.chronos_live import ChronosClock
    env=ArenaEnv(cfg,opponent='scripted',scenario='kickoff')
    try:
        env.reset(seed=233);state=env.state
        valid=native_action_mask(state.cars[env.agent]);choice=int(np.flatnonzero(valid)[0])
        class Constant(torch.nn.Module):
            def forward(self,x):
                y=torch.full((len(x),90),-100.);y[:,choice]=100.;return y
        _,mirror=build_features(state,env.agent,np.zeros(8),np.random.default_rng(1),'chronos')
        expected=TABLE[choice].copy()
        if mirror:expected[[1,3,4]]*=-1
        clock=ChronosClock();rng=np.random.default_rng(1)
        for frame in range(7):
            state.tick_count=frame;np.testing.assert_array_equal(clock.controls(state,env.agent,Constant(),rng),np.zeros(8))
        state.tick_count=7;np.testing.assert_array_equal(clock.controls(state,env.agent,Constant(),rng),expected)
        state.tick_count=8;np.testing.assert_array_equal(clock.controls(state,env.agent,Constant(),rng),expected)
        state.tick_count=1;np.testing.assert_array_equal(clock.controls(state,env.agent,Constant(),rng),np.zeros(8))
    finally:env.close()


def test_eight_tick_potential_shaping_telescopes_and_does_not_pay_for_contact():
    cfg=settings();cfg['env'].update(episode_seconds=20,no_touch_seconds=21)
    env=ChronosEnv(cfg,opponent='scorer',scenario='kickoff',side=0)
    try:
        obs,_=env.reset(seed=22);initial=env.arena.potential(env.arena.state);discount=1.;total=0.
        for _ in range(5):
            action=int(np.flatnonzero(obs[225:]>0)[0])
            obs,reward,term,trunc,info=env.step(action)
            assert not term and not trunc
            total+=discount*reward;discount*=cfg['ppo']['gamma']
        assert total==pytest.approx(discount*env.arena.potential(env.arena.state)-initial,abs=1e-6)
        state=copy.deepcopy(env.arena.state);other=copy.deepcopy(state)
        other.cars[env.arena.agent].ball_touches=100
        a=env.arena._reward(state,state,0,False);b=env.arena._reward(state,other,0,False)
        assert a==b and set(env.arena.last_reward_parts)=={'goal','potential'}
    finally:env.close()


def test_incomplete_checkpoint_is_quarantined_and_resume_uses_complete_generation(tmp_path):
    from nova.chronos_training import complete_generation,recover_chronos
    from nova.core import write_model_meta
    folder=tmp_path/'checkpoints';folder.mkdir()
    good=folder/'step_000000000032.zip';good.write_bytes(b'complete test checkpoint')
    write_model_meta(good,contract=CHRONOS_CONTRACT,timesteps=32)
    bad=folder/'step_000000000064.zip';bad.write_bytes(b'interrupted save')
    assert recover_chronos(tmp_path)==good
    assert json.loads((tmp_path/'latest.json').read_text())['step']==32
    assert complete_generation(good) is True
    assert complete_generation(bad) is False
    assert not bad.exists() and next(folder.glob('*.incomplete-*')).read_bytes()==b'interrupted save'


@pytest.mark.parametrize('side',[0,1])
@pytest.mark.parametrize('scenario',['kickoff','shot','defense','dribble','recovery','aerial','wall'])
def test_v5_packet_features_and_masks_match_simulator_and_keep_stable_ids(cfg,side,scenario):
    from rlbot.flat import (GamePacket,MatchInfo,MatchPhase,PlayerInfo,Physics,Vector3,Rotator,
        AirState,BoxShape,ControllerState,Vector2,BallInfo,BoostPadState,BoostPad,FieldInfo)
    from rlgym.rocket_league.common_values import BOOST_LOCATIONS
    from nova.chronos_live import ChronosBot
    env=ArenaEnv(cfg,opponent='scripted',scenario=scenario,side=side)
    def physics(source):
        return Physics(location=Vector3(*source.position),rotation=Rotator(*source.euler_angles),
            velocity=Vector3(*source.linear_velocity),angular_velocity=Vector3(*source.angular_velocity))
    try:
        env.reset(seed=233);state=env.state
        state.boost_pad_timers[:]=np.arange(34,dtype=np.float32)%5
        cars=list(state.cars)
        players=[]
        for index,key in enumerate(cars):
            car=state.cars[key]
            players.append(PlayerInfo(physics=physics(car.physics),hitbox=BoxShape(118.00738,84.19941,36.159073),
                hitbox_offset=Vector3(13.875,0,20.755),last_input=ControllerState(),dodge_dir=Vector2(),
                player_id=900+index,team=car.team_num,boost=car.boost_amount,
                air_state=AirState.OnGround if car.on_ground else AirState.InAir,
                has_jumped=car.has_jumped,has_dodged=car.has_flipped,has_double_jumped=car.has_double_jumped,
                dodge_timeout=-1,demolished_timeout=-1))
        packet=GamePacket(players=players,balls=[BallInfo(physics=physics(state.ball))],
            boost_pads=[BoostPadState(is_active=v==0,timer=float(v)) for v in state.boost_pad_timers],
            match_info=MatchInfo(frame_num=120,seconds_elapsed=1,match_phase=MatchPhase.Active))
        field=FieldInfo(boost_pads=[BoostPad(location=Vector3(*pos)) for pos in BOOST_LOCATIONS])
        class Runtime:
            field_info=field
            from rlbot.flat import MatchConfiguration
            match_config=MatchConfiguration()
        live=Runtime();ChronosBot._create_state(live);live.game_state.update(packet)
        own_index=cars.index(env.agent);agent=players[own_index].player_id
        previous=np.asarray([1,-1,0,1,-1,0,1,0],dtype=np.float32)
        expected,mirror=build_features(state,env.agent,previous,np.random.default_rng(3),'chronos')
        actual,live_mirror=build_features(live.game_state,agent,previous,np.random.default_rng(3),'chronos')
        np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-6)
        assert live_mirror==mirror
        np.testing.assert_array_equal(native_action_mask(live.game_state.cars[agent]),native_action_mask(state.cars[env.agent]))
        original=live.game_state.cars[agent]
        later=GamePacket(players=players,balls=packet.balls,boost_pads=packet.boost_pads,
            match_info=MatchInfo(frame_num=121,seconds_elapsed=121/120,match_phase=MatchPhase.Active))
        live.game_state.update(later)
        assert live.game_state.cars[agent] is original
        class Clock:
            def controls(self,game,controlled,network,rng):
                assert controlled==agent
                return np.zeros(8)
        live.indices={own_index};live.last_frame=None;live.clock=Clock();live.network=None;live.rng=None
        assert set(ChronosBot.get_outputs(live,later))=={own_index}
    finally:env.close()


def test_selfplay_reloads_manifest_if_inactive_snapshot_is_pruned_during_load(cfg,tmp_path,monkeypatch):
    from nova.core import atomic_json
    import nova.environment as module
    manifest=tmp_path/'league.json'
    atomic_json(manifest,{'snapshots':[{'step':32,'path':'old.lt'}]})
    opponent=object();calls=[]
    def load(kind,path):
        calls.append((kind,Path(path).name))
        if Path(path).name=='old.lt':
            atomic_json(manifest,{'snapshots':[{'step':64,'path':'new.lt'}]})
            raise FileNotFoundError('Snapshot pruned after worker read the previous manifest')
        return opponent
    monkeypatch.setattr(module,'make_opponent',load)
    env=ArenaEnv(cfg,league_manifest=manifest,opponent='latest',snapshot_kind='chronos_snapshot')
    try:
        env._choose_opponent()
        assert calls==[('chronos_snapshot','old.lt'),('chronos_snapshot','new.lt')]
        assert env.opponent is opponent and env.opponent_label=='latest:64'
    finally:env.close()
