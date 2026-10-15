"""Exercise the exported bot with real v5 packet types, without opening a match."""
import json
import math
from pathlib import Path
import time
import torch
from rlbot import flat
from bot import Freestyle
from runtime import PAD_LOCATIONS


def main():
    pads=[flat.BoostPad(location=flat.Vector3(*map(float,p)),is_full_boost=p[2]>72)for p in PAD_LOCATIONS]
    bot=Freestyle.__new__(Freestyle)
    bot.index=0;bot.field_info=flat.FieldInfo(boost_pads=pads);bot.initialize()
    previous=flat.ControllerState();nonzero=0;latencies=[]
    for tick in range(48):
        frame=1200+tick;now=frame/120;air=tick>=24
        position=flat.Vector3(0,-1000,450 if air else 17)
        car=flat.PlayerInfo(player_id=1,team=0,physics=flat.Physics(location=position,
            rotation=flat.Rotator(yaw=math.pi/2),velocity=flat.Vector3(0,500,0)),
            boost=80,air_state=flat.AirState.InAir if air else flat.AirState.OnGround,
            has_jumped=air,dodge_timeout=.5 if air else -1,demolished_timeout=-1,last_input=previous)
        packet=flat.GamePacket(players=[car],balls=[flat.BallInfo(physics=flat.Physics(
            location=flat.Vector3(0,-870,510 if air else 100),velocity=flat.Vector3(0,500,0)))],
            boost_pads=[flat.BoostPadState(is_active=True)for _ in range(34)],
            match_info=flat.MatchInfo(seconds_elapsed=now,frame_num=frame,match_phase=flat.MatchPhase.Active,
                                      world_gravity_z=-650,game_speed=1))
        packet=flat.GamePacket.unpack(packet.pack())
        start=time.perf_counter();previous=bot.get_output(packet);latencies.append((time.perf_counter()-start)*1000)
        values=[getattr(previous,k)for k in ('throttle','steer','pitch','yaw','roll','jump','boost','handbrake')]
        assert all(math.isfinite(float(v))and abs(float(v))<=1 for v in values)
        nonzero+=any(values)
    report={'status':'PASS','rlbot_packet_schema':'0.19.0','packets':48,'nonzero_control_packets':nonzero,
            'max_callback_ms':max(latencies),'cpu_policy_parameters':sum(p.numel()for p in bot.policy.parameters()),
            'scope':'synthetic packet/inference smoke test; Rocket League match was not run'}
    (Path(__file__).parent/'diagnostic.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
