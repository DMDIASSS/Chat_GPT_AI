"""Standalone RLBot v4 packet conversion; exported with its own feature module.

v4 exposes less jump information than v5. Flip availability is inferred from
wheel contact/jumped/double_jumped and elapsed airtime; live games are required
for ceiling/flip-reset validation. v5 remains the preferred precise adapter.
"""
from pathlib import Path
from types import SimpleNamespace as NS
import hashlib
import json
import math
import numpy as np
import torch


def xyz(vector):return np.array([vector.x,vector.y,vector.z],dtype=np.float32)


def physics(source):
    pitch,yaw,roll=source.rotation.pitch,source.rotation.yaw,source.rotation.roll
    cp,sp,cy,sy,cr,sr=math.cos(pitch),math.sin(pitch),math.cos(yaw),math.sin(yaw),math.cos(roll),math.sin(roll)
    rotation=np.array([[cp*cy,cy*sp*sr-cr*sy,-cr*cy*sp-sr*sy],
        [cp*sy,sy*sp*sr+cr*cy,-cr*sy*sp+sr*cy],[sp,-cp*sr,cp*cr]],dtype=np.float32)
    return NS(position=xyz(source.location),linear_velocity=xyz(source.velocity),
        angular_velocity=xyz(source.angular_velocity),rotation_mtx=rotation)


class PacketState:
    def __init__(self,boost_locations):
        self.locations=np.asarray(boost_locations);self.air_start={};self.last_frame=None;self.pad_order=None
    def decode(self,packet,field):
        frame=int(packet.game_info.frame_num)
        if self.last_frame is not None and frame<self.last_frame:self.air_start.clear()
        self.last_frame=frame
        if self.pad_order is None:
            if field.num_boosts!=len(self.locations):raise ValueError('Expected standard Soccar boost pads')
            self.pad_order=[]
            for i in range(field.num_boosts):
                distances=np.linalg.norm(self.locations[:,:2]-xyz(field.boost_pads[i].location)[:2],axis=1)
                if distances.min()>2:raise ValueError('Unsupported map boost locations')
                self.pad_order.append(int(distances.argmin()))
        timers=np.zeros(len(self.locations),np.float32)
        for source,destination in enumerate(self.pad_order):timers[destination]=packet.game_boosts[source].timer
        cars={};now=float(packet.game_info.seconds_elapsed)
        for i in range(packet.num_cars):
            car=packet.game_cars[i];ground=bool(car.has_wheel_contact)
            if ground or not car.jumped:self.air_start.pop(i,None)
            elif i not in self.air_start:self.air_start[i]=now
            flip=ground or (not car.double_jumped and (not car.jumped or now-self.air_start.get(i,now)<1.25))
            cars[i]=NS(physics=physics(car.physics),team_num=int(car.team),boost_amount=float(car.boost),
                on_ground=ground,has_flip=flip,has_jumped=bool(car.jumped),is_demoed=bool(car.is_demolished))
        return NS(tick_count=frame,ball=physics(packet.game_ball.physics),cars=cars,boost_pad_timers=timers)


def make_agent(model_path,clock_class,boost_locations):
    # Importing the v4 SDK is deliberately deferred: it must never replace the
    # project's v5 SDK inside its training environment.
    from rlbot.agents.base_agent import BaseAgent,SimpleControllerState
    class NovaChronos(BaseAgent):
        def initialize_agent(self):
            torch.set_num_threads(1);path=Path(model_path)
            meta=json.loads(Path(str(path)+'.json').read_text())
            if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('Actor integrity mismatch')
            self.network=torch.jit.load(str(path),map_location='cpu').eval()
            self.clock=clock_class();self.state=PacketState(boost_locations)
            self.rng=np.random.default_rng(631099);self.field=self.get_field_info()
        def get_output(self,packet):
            if packet.num_cars!=2 or not packet.game_info.is_round_active:
                self.clock.reset();return SimpleControllerState()
            state=self.state.decode(packet,self.field)
            if {c.team_num for c in state.cars.values()}!={0,1}:return SimpleControllerState()
            controls=self.clock.controls(state,self.index,self.network,self.rng)
            return SimpleControllerState(*[float(v) for v in controls[:5]],*[bool(v) for v in controls[5:]])
    return NovaChronos
