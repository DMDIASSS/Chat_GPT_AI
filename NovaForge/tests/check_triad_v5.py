"""Actual exported v5 process over TCP: handshake, InitComplete and controls.

A loopback core protocol harness, not a running Rocket League game.
"""
import json,os,socket,struct,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from rlbot import flat as f
from rlgym.rocket_league.common_values import BOOST_LOCATIONS


def exact(sock,n):
 data=b''
 while len(data)<n:
  block=sock.recv(n-len(data))
  if not block:raise EOFError('Bot exited before completing the protocol test')
  data+=block
 return data

def receive(sock):return f.InterfacePacket.unpack(exact(sock,int.from_bytes(exact(sock,2),'big'))).message

def send(sock,item):
 data=f.CorePacket(item).pack();sock.sendall(len(data).to_bytes(2,'big')+data)


def main():
 import tomllib,shlex
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--selector');args=parser.parse_args()
 from nova.triad import export
 root=Path(__file__).resolve().parents[1]
 with tempfile.TemporaryDirectory() as temp:
  folder=export(selector_path=args.selector,destination_parent=Path(temp)/'exports')
  settings=tomllib.loads((folder/'bot.bot.toml').read_text())['settings']
  command=settings['run_command'] if os.name=='nt' else shlex.split(settings['run_command_linux'])
  assert not (folder/'.venv').exists()
  # TOML executable/arguments agree with this generated command on both OSes.
  assert str(sys.executable) in settings['run_command'] and 'run_triad.py' in settings['run_command']
  with socket.socket() as server:
   server.bind(('127.0.0.1',0));server.listen(1);server.settimeout(45)
   env=dict(os.environ,RLBOT_SERVER_IP='127.0.0.1',RLBOT_SERVER_PORT=str(server.getsockname()[1]),RLBOT_AGENT_ID='test/triad')
   with (folder/'process.log').open('w') as log:
    process=subprocess.Popen(command,cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT)
    try:
     conn,_=server.accept()
     with conn:
      conn.settimeout(60);hello=receive(conn);assert isinstance(hello,f.ConnectionSettings) and hello.agent_id=='test/triad'
      players=[f.PlayerConfiguration(variety=f.CustomBot(name='Triad',agent_id='test/triad'),team=0,player_id=900),
       f.PlayerConfiguration(variety=f.CustomBot(name='Opponent',agent_id='test/other'),team=1,player_id=901)]
      send(conn,f.MatchConfiguration(player_configurations=players))
      send(conn,f.FieldInfo(boost_pads=[f.BoostPad(location=f.Vector3(*v)) for v in BOOST_LOCATIONS]))
      send(conn,f.ControllableTeamInfo(team=0,controllables=[f.ControllableInfo(index=0,identifier=900)]))
      while not isinstance(receive(conn),f.InitComplete):pass
      received=0;nonzero=False
      for frame in (0,4,7,8,15,16):
       cars=[f.PlayerInfo(physics=f.Physics(location=f.Vector3(0,y,17),rotation=f.Rotator(0,yaw,0),velocity=f.Vector3(),angular_velocity=f.Vector3()),
        hitbox=f.BoxShape(131.49236,80.521,30.3) if i==0 else f.BoxShape(118.00738,84.19941,36.159073),hitbox_offset=f.Vector3(),
        air_state=f.AirState.OnGround,dodge_timeout=-1,demolished_timeout=-1,last_input=f.ControllerState(),dodge_dir=f.Vector2(),
        player_id=900+i,team=i,boost=33) for i,(y,yaw) in enumerate([(-4608,np.pi/2),(4608,-np.pi/2)])]
       packet=f.GamePacket(players=cars,balls=[f.BallInfo(physics=f.Physics(location=f.Vector3(0,0,93.15),rotation=f.Rotator(),velocity=f.Vector3(),angular_velocity=f.Vector3()))],
        boost_pads=[f.BoostPadState(is_active=True) for _ in BOOST_LOCATIONS],match_info=f.MatchInfo(frame_num=frame,seconds_elapsed=frame/120,match_phase=f.MatchPhase.Active))
       send(conn,packet)
       while True:
        msg=receive(conn)
        if isinstance(msg,f.PlayerInput):
         assert msg.player_index==0;received+=1
         nonzero|=abs(msg.controller_state.throttle)>0 or msg.controller_state.boost
         break
      assert received==6 and nonzero
      send(conn,f.DisconnectSignal())
     process.wait(timeout=15);assert process.returncode==0
     print('TRIAD_V5_TCP_HANDSHAKE_INIT_AND_CONTROLS_PASS')
    except BaseException:
     process.kill();process.wait();print((folder/'process.log').read_text());raise

if __name__=='__main__':main()
