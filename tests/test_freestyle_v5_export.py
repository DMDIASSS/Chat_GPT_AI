"""Portable weights, native feature parity, and actual RLBot v5 packet timing."""
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tomllib

import numpy as np
import pytest
import torch

import export_freestyle_rlbot_v5 as exporter
from freestyle_rlbot_v5 import runtime as r
from freestyle_rlbot_v5.live import PacketAdapter, LiveController, rotation
from slater_v041_core import sha256
import slater_freestyle as freestyle

ROOT = Path(__file__).resolve().parents[1]


def player(rng, car_id=1, team=0):
    f, right, up = rotation(SimpleNamespace(pitch=float(rng.uniform(-1.5, 1.5)), yaw=float(rng.uniform(-3, 3)), roll=float(rng.uniform(-3, 3))))
    return {'carId': car_id, 'team': team, 'pos': rng.uniform((-4000, -5000, 20), (4000, 5000, 1800)).tolist(),
        'vel': rng.uniform(-1800, 1800, 3).tolist(), 'angVel': rng.uniform(-5, 5, 3).tolist(),
        'forward': f.tolist(), 'right': right.tolist(), 'up': up.tolist(), 'boost': float(rng.choice((0, 40, 100))),
        'isOnGround': bool(rng.integers(2)), 'hasJumped': bool(rng.integers(2)),
        'hasDoubleJumped': bool(rng.integers(2)), 'hasFlipped': bool(rng.integers(2)),
        'isFlipping': False, 'isJumping': False, 'isDemoed': False, 'isSupersonic': True,
        'airTime': float(rng.uniform(0, 8)), 'airTimeSinceJump': float(rng.choice((0, .2, 1.25, 2))),
        'jumpTime': .1, 'flipTime': .2, 'handbrakeVal': .25, 'demoRespawnTimer': 0,
        'ballTouchedStep': bool(rng.integers(2)), 'prevAction': r.ACTIONS[int(rng.integers(94))].tolist(),
        'worldContact': {'hasContact': bool(rng.integers(2)), 'contactNormal': [0, 0, 1]}}


def samples(count=96):
    rng = np.random.default_rng(992714)
    result = []
    for i in range(count):
        players = [player(rng, k+1, (k+i)%2) for k in range(1+i%6)]
        state = {'players': players, 'ball': {'pos': rng.uniform((-4000, -5000, 93), (4000, 5000, 1900)).tolist(),
            'vel': rng.uniform(-2500, 2500, 3).tolist(), 'angVel': rng.uniform(-5, 5, 3).tolist()},
            'boostPads': rng.integers(0, 2, 34).astype(bool).tolist(), 'boostPadTimers': rng.uniform(0, 10, 34).tolist(),
            'goalScored': bool(i%3 == 0), 'lastTouchCarID': 1 if i%2 else -1, 'deltaTime': 1/30}
        chain = {'lastTouch': .5, 'lastNoseTouch': .6, 'carry': .1, 'bestCarry': .6, 'carryDistance': 350,
            'wall': True, 'pop': bool(i%2), 'wallAt': .2, 'popAt': .4, 'noseTouches': i%8,
            'pinch': bool(i%3), 'board': bool(i%4), 'retouch': bool(i%2), 'ownBoard': False, 'recovered': True, 'wallDashes': i%5}
        result.append({'state': state, 'player_id': 1, 'context': {'stage': i%10, 'difficulty': .75,
            'elapsed': (i*11+100)/120, 'episodeSeconds': 12, 'chain': chain}})
    return result


@pytest.fixture
def source(tmp_path, monkeypatch):
    torch.set_num_threads(1)
    runs = tmp_path/'runs'; out = tmp_path/'exports'
    monkeypatch.setattr(exporter, 'RUNS', runs); monkeypatch.setattr(exporter, 'OUTPUT', out)
    run = runs/'freestyle_rewards02'; checkpoint = run/'checkpoints/12345'; checkpoint.mkdir(parents=True)
    config = freestyle.defaults()['native']; config.update(width=64, depth=1)
    actor = torch.nn.Sequential(torch.nn.Linear(512, 64), torch.nn.LayerNorm(64), torch.nn.ReLU(), torch.nn.Linear(64, 94)).eval()
    torch.jit.trace(actor, torch.zeros(1, 512)).save(str(checkpoint/'POLICY.lt'))
    marker = {'schema': 1, 'update': 600, 'timesteps': 12345, 'source_sha': 'native-source'}
    (checkpoint/'FREESTYLE_COMPLETE.json').write_text(json.dumps(marker))
    (checkpoint/'FREESTYLE_STATE.json').write_text(json.dumps({**marker, 'reward_version': 2, 'stage': 'contact_pop', 'difficulty': .75}))
    (run/'config.json').write_text(json.dumps(config))
    (run/'protocol.json').write_text(json.dumps({'schema': 'slater-freestyle-v1', 'identity': {'backend_sha': freestyle.backend_identity()}}))
    return SimpleNamespace(run=run, checkpoint=checkpoint, actor=actor)


def test_export_preserves_source_and_has_callable_policy_and_valid_v5_config(source):
    before = {p.name: sha256(p) for p in source.checkpoint.iterdir()}
    output = exporter.export(name='Freestyle600')
    info = json.loads((output/'EXPORT_INFO.json').read_text())
    assert info['parameter_tensors_identical'] and info['portable_actions_identical'] and info['portable_max_logit_error'] == 0
    model = torch.jit.load(str(output/'policy.pt')); obs = torch.randn(7, 512)
    assert torch.equal(model(obs), source.actor(obs))
    config = tomllib.loads((output/'bot.toml').read_text())
    assert config['settings']['run_command'] == '.\\.venv\\Scripts\\python.exe bot.py'
    assert config['settings']['agent_id'].startswith('dmdias/freestyle-')
    assert (output/'INSTALL.bat').is_file() and output.with_suffix('.zip').is_file()
    assert {p.name: sha256(p) for p in source.checkpoint.iterdir()} == before
    with pytest.raises(FileExistsError): exporter.export(name='Freestyle600')


def test_missing_unsaved_update_and_incomplete_checkpoint_are_not_substituted(source):
    with pytest.raises(FileNotFoundError): exporter.export(update=253)
    incomplete = source.run/'checkpoints/99999'; incomplete.mkdir()
    (incomplete/'POLICY.lt').write_bytes(b'incomplete')
    assert exporter.checkpoints(source.run)[-1][0] == 600
    (source.checkpoint/'FREESTYLE_COMPLETE.json').unlink()
    with pytest.raises(FileNotFoundError): exporter.export()


def test_architecture_mismatch_fails_closed(source):
    config = json.loads((source.run/'config.json').read_text()); config['width'] = 128
    (source.run/'config.json').write_text(json.dumps(config))
    with pytest.raises(RuntimeError): exporter.export()


def test_real_native_observations_masks_logits_and_actions_match(tmp_path):
    binary = ROOT/'data/isolated/freestyle_export_reference/freestyle-export-reference'
    parent = ROOT/'data/isolated/freestyle/runs/cloud_dll_bridge01'; checkpoint = parent/'checkpoints/10080'
    if not binary.is_file() or not checkpoint.is_dir(): pytest.skip('Optional native export reference unavailable')
    from GigaLearn_Project.Native_Backend.native_setup import meshes
    cases = samples(); inputs = tmp_path/'cases.json'; inputs.write_text(json.dumps(cases)); output = tmp_path/'reference.json'
    result = subprocess.run([str(binary), str(inputs), str(checkpoint), str(parent/'config.json'), str(meshes()), str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout+result.stderr
    native = json.loads(output.read_text()); np.testing.assert_array_equal(native['actions'], r.ACTIONS)
    actor = exporter.load_actor(checkpoint, json.loads((parent/'config.json').read_text()))
    max_error = 0
    for sample, expected in zip(cases, native['cases']):
        obs = r.observation(sample['state'], sample['player_id'], sample['context'])
        mask = r.action_mask(sample['state']['players'][0])
        np.testing.assert_allclose(obs, expected['observation'], rtol=2e-6, atol=2e-6)
        np.testing.assert_array_equal(mask, np.asarray(expected['mask'], bool))
        with torch.inference_mode(): scores = actor(torch.from_numpy(obs)[None])[0].numpy()
        max_error = max(max_error, float(np.max(np.abs(scores-expected['logits']))))
        np.testing.assert_allclose(scores, expected['logits'], rtol=2e-5, atol=1e-5)
        assert int(np.where(mask, scores, -1e10).argmax()) == expected['action']
    assert max_error < 1e-5


@pytest.fixture
def sdk(): return pytest.importorskip('rlbot.flat', reason='Optional RLBot v5 SDK required')


def field_info(sdk, reverse=False):
    pads = [sdk.BoostPad(location=sdk.Vector3(*map(float, p)), is_full_boost=p[2] > 72) for p in r.PAD_LOCATIONS]
    return sdk.FieldInfo(boost_pads=pads[::-1] if reverse else pads)


def packet(sdk, frame=0, phase=3, ball=(0, 0, 93), velocity=(0, 0, 0), positions=((0, -1000, 17),)):
    players = [sdk.PlayerInfo(player_id=i+1, team=0, physics=sdk.Physics(location=sdk.Vector3(*map(float, p)), rotation=sdk.Rotator(yaw=float(np.pi/2))),
        boost=80, demolished_timeout=-1, dodge_timeout=-1, air_state=sdk.AirState.OnGround) for i, p in enumerate(positions)]
    return sdk.GamePacket(players=players, balls=[sdk.BallInfo(physics=sdk.Physics(location=sdk.Vector3(*map(float, ball)), velocity=sdk.Vector3(*map(float, velocity))))],
        boost_pads=[sdk.BoostPadState(is_active=True) for _ in range(34)],
        match_info=sdk.MatchInfo(seconds_elapsed=frame/120, frame_num=frame, match_phase=sdk.MatchPhase(phase), world_gravity_z=-650, game_speed=1))


def live_config(scripted=False):
    return {'stage': 0, 'difficulty': .75, 'episode_seconds': 12, 'tick_skip': 4, 'action_delay': 1, 'scripted_kickoff': scripted}


def test_actual_v5_packets_hold_actions_and_release_after_replay(sdk):
    calls = []
    action = int(np.flatnonzero((r.ACTIONS[:, 0] == 1)&(r.ACTIONS[:, 1] == 0)&(r.ACTIONS[:, 5] == 0)&(r.ACTIONS[:, 6] == 1))[0])
    def infer(obs, mask): calls.append(obs); assert mask[action]; return action
    bot = LiveController(infer, field_info(sdk), live_config())
    p = packet(sdk); p = sdk.GamePacket.unpack(p.pack())
    assert not bot.act(p, 0).any()
    assert not bot.act(p, 0).any() and len(calls) == 1
    for frame in range(1, 9):
        result = bot.act(packet(sdk, frame=frame), 0)
        assert result[0] == 1 and result[6] == 1
    assert len(calls) == 3
    assert not bot.act(packet(sdk, frame=9, phase=5), 0).any()
    bot.act(packet(sdk, frame=10), 0)
    assert bot.act(packet(sdk, frame=11), 0)[0] == 1


def test_scripted_kickoff_selects_one_taker_then_hands_back_to_policy(sdk):
    def infer(obs, mask): return int(np.flatnonzero(mask)[0])
    bots = [LiveController(infer, field_info(sdk), live_config(True)) for _ in range(2)]
    positions = ((2048, -2560, 17), (-2048, -2560, 17))
    results = [b.act(packet(sdk, frame=1, phase=2, positions=positions), i) for i, b in enumerate(bots)]
    assert sum(x[0] > 0 for x in results) == 1 and results[0][0] == 1
    for i, b in enumerate(bots):
        b.act(packet(sdk, frame=100, ball=(400, 0, 93), velocity=(200, 0, 0), positions=positions), i)
        assert b.kickoff.started is None and b.pending is not None


def test_v5_boost_timers_map_to_remaining_cooldown(sdk):
    field = field_info(sdk, reverse=True); adapter = PacketAdapter(field); p = packet(sdk)
    p = sdk.GamePacket(players=p.players, balls=p.balls, match_info=p.match_info,
        boost_pads=[sdk.BoostPadState(is_active=False, timer=1.5) for _ in range(34)])
    state = adapter.read(p)
    assert state['boostPadTimers'][3] == 8.5 and state['boostPadTimers'][0] == 2.5


@pytest.mark.parametrize('jumped,dodged,timeout,expected', [(True,False,.7,True),(True,True,-1,False),(False,False,-1,True)])
def test_v5_jump_dodge_and_reset_availability(sdk,jumped,dodged,timeout,expected):
    p=packet(sdk)
    car=sdk.PlayerInfo(player_id=1,team=0,boost=0,physics=sdk.Physics(location=sdk.Vector3(0,0,450)),
        air_state=sdk.AirState.InAir,has_jumped=jumped,has_dodged=dodged,dodge_timeout=timeout,demolished_timeout=-1)
    p=sdk.GamePacket(players=[car],balls=p.balls,boost_pads=p.boost_pads,match_info=p.match_info)
    state=PacketAdapter(field_info(sdk)).read(p)
    own=state['players'][0]
    assert r.available(own)==expected
    mask=r.action_mask(own)
    assert bool(mask[r.ACTIONS[:,5]>0].any())==expected
    assert not mask[r.ACTIONS[:,6]>0].any()
    obs=r.observation(state,1,{'stage':0,'difficulty':.75,'elapsed':0,'episodeSeconds':12})
    assert not obs[62:72].any()  # Optional simulator contact evidence is masked.


def test_touch_is_accumulated_to_policy_boundary_and_not_recounted(sdk):
    adapter=PacketAdapter(field_info(sdk));adapter.read(packet(sdk))
    def touched(frame):
        p=packet(sdk,frame=frame)
        car=sdk.PlayerInfo(player_id=1,team=0,physics=p.players[0].physics,air_state=sdk.AirState.OnGround,
            latest_touch=sdk.Touch(game_seconds=1/120,ball_index=0),demolished_timeout=-1)
        return sdk.GamePacket(players=[car],balls=p.balls,boost_pads=p.boost_pads,match_info=p.match_info)
    assert adapter.read(touched(1))['players'][0]['ballTouchedStep']
    assert adapter.read(touched(4),decision=True)['players'][0]['ballTouchedStep']
    assert not adapter.read(touched(5))['players'][0]['ballTouchedStep']


def test_nonfinite_input_is_rejected_instead_of_clipped_to_a_plausible_state():
    sample=samples(1)[0];sample['state']['players'][0]['vel'][0]=float('inf')
    with pytest.raises(ValueError,match='Nonfinite'):
        r.observation(sample['state'],1,sample['context'])
