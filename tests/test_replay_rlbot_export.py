"""Real TorchScript export and packet/control parity without launching a match."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace as NS
from pathlib import Path
import numpy as np
import pytest
import torch
from replay_rlbot_core import PacketObserver,ReplayController,BOOST_LOCATIONS
from export_replay_rlbot import export
from slater_v041_core import atomic_json,sha256
from test_replay_runtime import model_book,state_fixture
from replay_il_runtime import RuntimePlanner


def vec(array):return NS(x=float(array[0]),y=float(array[1]),z=float(array[2]))


def packet_fixture(state):
    order=np.arange(33,-1,-1)
    field=NS(num_boosts=34,boost_pads=[NS(location=vec(BOOST_LOCATIONS[i])) for i in order])
    def physics(value):
        pitch,yaw,roll=value.euler_angles
        return NS(location=vec(value.position),velocity=vec(value.linear_velocity),angular_velocity=vec(value.angular_velocity),
                  rotation=NS(pitch=float(pitch),yaw=float(yaw),roll=float(roll)))
    cars=[NS(physics=physics(c.physics),team=c.team_num,boost=c.boost_amount,has_wheel_contact=c.on_ground,
             is_demolished=c.demo_respawn_timer>0,jumped=False,double_jumped=c.has_double_jumped) for c in state.cars.values()]
    packet=NS(num_cars=len(cars),game_cars=cars,game_ball=NS(physics=physics(state.ball)),
        game_boosts=[NS(is_active=state.boost_pad_timers[i]<=1e-6) for i in order],
        game_info=NS(seconds_elapsed=0.,is_kickoff_pause=False,is_round_active=True,is_match_ended=False))
    return packet,field


@pytest.mark.parametrize('players',[2,4,6])
@pytest.mark.parametrize('anchor_height',[None,0.])
def test_rlbot_packet_observations_match_training_for_both_teams_and_pad_order(model_book,players,anchor_height):
    model,book=model_book;state=state_fixture(players)
    for i,car in enumerate(state.cars.values()):
        car.physics.euler_angles=np.array([.2*i,.8*i,-.3*i],np.float32)
        car.physics.angular_velocity=np.array([.3,-.2,.8],np.float32)
        car.boost_amount=30+i*5;car.has_flipped=False;car.has_double_jumped=False;car.air_time_since_jump=0.
    state.boost_pad_timers[::3]=2.
    packet,field=packet_fixture(state)
    if anchor_height is not None:
        for pad in field.boost_pads:pad.location.z=anchor_height
    observer=PacketObserver(field);planner=RuntimePlanner(model,book,candidates=2)
    previous=np.array([1,.2,0,.1,0,0,1,0],np.float32)
    try:
        for index in (0,players-1):
            ours=list(state.cars)[index]
            actual=observer.observe(packet,index,previous);expected=planner.observation(state,{ours:previous},ours)
            for a,b in zip(actual,expected):np.testing.assert_allclose(a,b,atol=2e-6,rtol=0)
    finally:planner.close()


def test_boost_matching_still_rejects_duplicate_or_wrong_xy_positions():
    _,field=packet_fixture(state_fixture())
    field.boost_pads[0].location.x+=100
    with pytest.raises(ValueError,match='X/Y layout'):PacketObserver(field)
    _,field=packet_fixture(state_fixture())
    field.boost_pads[0].location=field.boost_pads[1].location
    with pytest.raises(ValueError,match='X/Y layout'):PacketObserver(field)


def test_chunk_clock_keeps_edges_previous_controls_and_does_not_fabricate_missed_history():
    calls=[]
    class Observer:
        def reset(self):pass
        def observe(self,p,index,previous):
            calls.append(previous.copy());return np.zeros((1,32),np.float32),np.zeros((41,24),np.float32),np.zeros(41,np.float32)
    class Kernel:
        def encode(self,obs):return torch.ones(1,128)
        def decode(self,history):return torch.tensor([[1.,0.]]),torch.zeros(1,3)
    book=np.zeros((2,32,8),np.float32);book[0,:,0]=1;book[0,2:4,5]=1;book[0,4:6,6]=1
    controller=ReplayController(Kernel(),book,Observer())
    packet,_=packet_fixture(state_fixture())
    for tick in range(17):
        packet.game_info.seconds_elapsed=tick/120
        np.testing.assert_array_equal(controller.output(packet,0),book[0,tick%8])
    assert len(calls)==3 and len(controller.features)==3
    np.testing.assert_array_equal(calls[1],book[0,7])
    packet.game_info.seconds_elapsed=36/120;controller.output(packet,0)
    assert len(controller.features)==1
    packet.game_info.is_round_active=False
    np.testing.assert_array_equal(controller.output(packet,0),np.zeros(8))


def test_complete_export_reloads_model_in_isolated_folder_and_preserves_source(tmp_path,model_book,monkeypatch):
    model,book=model_book;source=tmp_path/'source';source.mkdir()
    torch.save({'config':model.config,'model':model.state_dict()},source/'best.pt');np.save(source/'tokens.npy',book)
    atomic_json(source/'selected.json',{'sha256':sha256(source/'best.pt')});atomic_json(source/'tokenizer.json',{'book_sha256':sha256(source/'tokens.npy')})
    paths=list(source.iterdir())+list((Path(__file__).resolve().parents[1]/'replay_il').glob('*.py'))
    before={p:sha256(p) for p in paths};target=export(source,'ReplayTest',tmp_path/'exports')
    assert {p:sha256(p) for p in paths}==before
    assert (target/'bot.cfg').is_file() and sha256(target/'tokens.npy')==before[source/'tokens.npy']
    with pytest.raises(FileExistsError):export(source,'ReplayTest',tmp_path/'exports')
    # A separate interpreter gets only the exported folder, not project imports.
    # Only RLBot's external BaseAgent/controller interface is stubbed.
    packet,field=packet_fixture(state_fixture())
    for pad in field.boost_pads:pad.location.z=0.
    payload=json.dumps({'packet':packet,'field':field},default=lambda v:v.item() if isinstance(v,np.generic) else vars(v))
    (target/'fixture.json').write_text(payload)
    script='''
import json,sys
from pathlib import Path
from types import SimpleNamespace as NS,ModuleType
base=ModuleType('rlbot.agents.base_agent');base.BaseAgent=type('BaseAgent',(),{});base.SimpleControllerState=lambda **kwargs:NS(**kwargs)
for name in ('rlbot','rlbot.agents'):sys.modules[name]=ModuleType(name)
sys.modules['rlbot.agents.base_agent']=base
from bot import ReplayBot
data=json.loads(Path('fixture.json').read_text(),object_hook=lambda d:NS(**d))
agent=ReplayBot();agent.index=0;agent.get_field_info=lambda:data.field;agent.initialize_agent()
for tick in range(17):
 data.packet.game_info.seconds_elapsed=tick/120
 result=agent.get_output(data.packet)
 assert not agent.reported_error and -1<=result.throttle<=1
assert 'replay_il' not in sys.modules and 'RocketSim' not in sys.modules
print('SELF_CONTAINED_EXPORT_OK')
'''
    env=os.environ.copy();env['PYTHONPATH']=''
    # Reproduce the shipped 3D-height rejection, then repair this very export.
    core=target/'replay_rlbot_core.py';fixed=core.read_text()
    old=fixed.replace('np.asarray(BOOST_LOCATIONS)[:,None,:2]-pads[None,:,:2]',
                      'np.asarray(BOOST_LOCATIONS)[:,None]-pads[None,:]')
    assert old!=fixed;core.write_text(old)
    metadata=json.loads((target/'EXPORT_INFO.json').read_text());metadata['runtime_sha256'][core.name]=sha256(core)
    atomic_json(target/'EXPORT_INFO.json',metadata)
    broken=subprocess.run([sys.executable,'-c',script],cwd=target,env=env,text=True,capture_output=True,timeout=30)
    assert broken.returncode!=0 and 'boost X/Y layout' in broken.stderr
    protected={p:sha256(target/p) for p in ('policy.pt','tokens.npy')}
    from repair_replay_rlbot import repair
    repair(target);repair(target) # Repair is repeatable and never re-exports weights.
    assert {p:sha256(target/p) for p in protected}==protected
    assert (target/'replay_rlbot_core.py.before_boost_xy_fix').read_text()==old
    result=subprocess.run([sys.executable,'-c',script],cwd=target,env=env,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'SELF_CONTAINED_EXPORT_OK' in result.stdout


def test_repair_refuses_tampered_exports_before_writing(tmp_path):
    from repair_replay_rlbot import repair,RUNTIME_FILES
    for name in RUNTIME_FILES:(tmp_path/name).write_bytes(b'original')
    metadata={'format':'replay-chunk-rlbot-v4-v1','runtime_sha256':{n:sha256(tmp_path/n) for n in RUNTIME_FILES}}
    atomic_json(tmp_path/'EXPORT_INFO.json',metadata)
    (tmp_path/'tokens.npy').write_bytes(b'changed')
    before={p:sha256(p) for p in tmp_path.iterdir()}
    with pytest.raises(ValueError,match='Export file changed'):repair(tmp_path)
    assert {p:sha256(p) for p in tmp_path.iterdir()}==before
