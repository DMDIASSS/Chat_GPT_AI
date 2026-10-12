import importlib.util,sys,types
from pathlib import Path
from types import SimpleNamespace as S
import numpy as np
import pytest
from export_native_rlbot_v4 import export_native
from slater_native_actor import checkpoint_identity

SOURCE=Path('data/isolated/gigalearn_native/runs/cloud_windows_link_fix01/checkpoints/4832')

def vec(x=0,y=0,z=0):return S(x=x,y=y,z=z)
def body(x=0,y=0,z=17,yaw=0):return S(location=vec(x,y,z),velocity=vec(),angular_velocity=vec(),rotation=S(pitch=0,yaw=yaw,roll=0))

@pytest.mark.parametrize('scripted',[True,False])
def test_export_and_packet_inference(tmp_path,monkeypatch,scripted):
    if not SOURCE.exists():pytest.skip('Native integration checkpoint unavailable')
    before=checkpoint_identity(SOURCE)
    target=export_native(SOURCE/'POLICY.lt','NativeTest',tmp_path,scripted_kickoff=scripted)
    assert checkpoint_identity(SOURCE)==before
    assert checkpoint_identity(target/'checkpoint')['files']==before['files']
    with pytest.raises(FileExistsError):export_native(SOURCE,'NativeTest',tmp_path)
    base=types.ModuleType('rlbot.agents.base_agent');base.BaseAgent=object;base.SimpleControllerState=lambda **kw:S(**kw)
    monkeypatch.setitem(sys.modules,'rlbot',types.ModuleType('rlbot'));monkeypatch.setitem(sys.modules,'rlbot.agents',types.ModuleType('rlbot.agents'))
    monkeypatch.setitem(sys.modules,'rlbot.agents.base_agent',base)
    monkeypatch.syspath_prepend(str(target))
    spec=importlib.util.spec_from_file_location('native_actor',target/'native_actor.py');actor=importlib.util.module_from_spec(spec);spec.loader.exec_module(actor)
    monkeypatch.setitem(sys.modules,'native_actor',actor)
    spec=importlib.util.spec_from_file_location('exported_bot',target/'bot.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    assert mod.SCRIPTED_KICKOFF is scripted
    locations=np.load(target/'boost_locations.npy')
    bot=mod.NativeBot();bot.index=0;bot.get_field_info=lambda:S(num_boosts=34,boost_pads=[S(location=vec(*v),is_full_boost=v[2]>72) for v in locations])
    bot.initialize_agent()
    cars=[S(team=i,physics=body(0,(-1 if i==0 else 1)*4608,yaw=np.pi/2 if i==0 else -np.pi/2),boost=33,
            has_wheel_contact=True,is_demolished=False,jumped=False,double_jumped=False) for i in range(2)]
    p=S(num_cars=2,game_cars=cars,game_ball=S(physics=body(0,0,93)),game_boosts=[S(is_active=True,timer=0) for _ in range(34)],game_info=S(seconds_elapsed=0,is_kickoff_pause=True))
    for tick in range(180):
        p.game_info.seconds_elapsed=tick/120
        controls=bot.get_output(p)
        assert np.isfinite([controls.throttle,controls.steer,controls.pitch,controls.yaw,controls.roll]).all()
        if scripted and tick==0:assert controls.throttle==1 and controls.boost
    if not scripted:assert bot.clock.kickoff_index==-1
    p.game_info.seconds_elapsed=0;bot.get_output(p)
