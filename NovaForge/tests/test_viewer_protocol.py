"""Opt-in native sender check. Normal training checks never claim its fixed UDP ports."""
import importlib.metadata
import json
import subprocess
import sys
import pytest


def test_camera_sender_emits_length_prefixed_flatbuffer_packets(tmp_path,request):
    if not request.config.getoption('--viewer-udp'):
        pytest.skip('Native UDP check is opt-in: stop viewers/senders, then use --viewer-udp')
    if importlib.metadata.version('rlviser-py')!='0.6.14':
        pytest.skip('Run 31_SETUP_RLVISER.bat to install the camera-compatible sender')
    code=r'''
import socket,json,sys
import rlviser_py as vis
import RocketSim as rs
import rlgym.rocket_league.sim as sim
from pathlib import Path
rs.init(str(Path(sim.__file__).parent/'collision_meshes'))
receiver=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
check=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
# Windows permits overlapping UDP binds unless exclusivity is requested. Match
# the sender's wildcard bind, not just 127.0.0.1, before calling Rust's unwrap().
if sys.platform=='win32':
    for sock in (receiver,check):sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
try:
    receiver.bind(('0.0.0.0',45243));check.bind(('0.0.0.0',34254))
except OSError:
    print(json.dumps({'skip':'viewer UDP ports already in use'}));raise SystemExit(0)
check.close();receiver.settimeout(3)
arena=rs.Arena(rs.GameMode.SOCCAR);car=arena.add_car(rs.Team.BLUE)
vis.render(0,120,rs.GameMode.SOCCAR,[p.get_state().is_active for p in arena.get_boost_pads()],
    arena.ball.get_state(),[(car.id,car.team,car.get_config(),car.get_state())])
vis.quit();tags=[]
for _ in range(3):
    frame=receiver.recv(65536)
    assert len(frame)>8 and int.from_bytes(frame[:8],'big')==len(frame)-8
    payload=frame[8:];root=int.from_bytes(payload[:4],'little')
    table=root-int.from_bytes(payload[root:root+4],'little',signed=True)
    assert 0<=table<len(payload) and root<len(payload)
    field=int.from_bytes(payload[table+4:table+6],'little')
    tags.append(payload[root+field])
print(json.dumps({'tags':tags}))
'''
    process=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,capture_output=True,text=True,timeout=20)
    # Another sender can claim the fixed port after the preflight socket closes.
    # Only that exact native bind conflict is a skip; protocol errors still fail.
    if process.returncode and 'AddrInUse' in process.stderr and ('10048' in process.stderr or 'Address already in use' in process.stderr):
        pytest.skip('Another sender claimed the viewer UDP port during the native check')
    assert process.returncode==0,process.stderr
    result=json.loads(process.stdout.strip().splitlines()[-1])
    if result.get('skip'):pytest.skip(result['skip'])
    assert result['tags']==[1,5,2]
