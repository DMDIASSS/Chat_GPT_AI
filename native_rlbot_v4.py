"""RLBot v4 native deployment. Packet jump/contact state is an approximation."""
from pathlib import Path
import math
import numpy as np
import torch
from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from native_actor import NativeActor, infer, nexto_actions
from slater_nexto_scheduler_v038b import NextoV4Clock

HERE=Path(__file__).resolve().parent
SCRIPTED_KICKOFF=True

def vector(v):return [v.x,v.y,v.z]

def physics(p):
    r=p.rotation;cp,sp=math.cos(r.pitch),math.sin(r.pitch);cy,sy=math.cos(r.yaw),math.sin(r.yaw);cr,sr=math.cos(r.roll),math.sin(r.roll)
    # Columns are forward/right/up; native archive packets store transposed matrices.
    rot=np.array([[cp*cy,cy*sp*sr-cr*sy,-cr*cy*sp-sr*sy],
                  [cp*sy,sy*sp*sr+cr*cy,-cr*sy*sp+sr*cy],
                  [sp,-cp*sr,cp*cr]])
    return dict(pos=vector(p.location),vel=vector(p.velocity),ang=vector(p.angular_velocity),rot=rot.T.reshape(-1).tolist())

class NativeBot(BaseAgent):
    def initialize_agent(self):
        torch.set_num_threads(1)
        self.actor=NativeActor(HERE/'checkpoint');self.clock=NextoV4Clock(hardcoded=SCRIPTED_KICKOFF,stochastic=False)
        self.previous=np.zeros(8,dtype=np.float32);self.held=self.previous.copy();self.pending=self.previous.copy()
        self.last_time=None;self.tick=0;self.jumps={}
        field=self.get_field_info();locations=np.load(HERE/'boost_locations.npy')
        pads=np.array([vector(field.boost_pads[i].location) for i in range(field.num_boosts)])
        if len(pads)!=34:raise ValueError('Native export supports standard Soccar boost pads only')
        self.pad_order=np.linalg.norm(locations[:,None]-pads[None,:],axis=-1).argmin(1)
        if len(set(self.pad_order))!=34:raise ValueError('Unsupported arena boost layout')
        self.pad_durations=np.array([10 if field.boost_pads[int(i)].is_full_boost else 4 for i in self.pad_order])

    def native_packet(self,p):
        now=p.game_info.seconds_elapsed;cars=[]
        for i in range(p.num_cars):
            c=p.game_cars[i];start=self.jumps.get(i)
            if c.has_wheel_contact or c.is_demolished or not c.jumped:start=None
            elif start is None:start=now
            self.jumps[i]=start
            cars.append(dict(id=i+1,team=c.team,**physics(c.physics),boost=float(c.boost),ground=bool(c.has_wheel_contact),
                jumped=bool(c.jumped),double_jumped=bool(c.double_jumped),flipped=bool(c.double_jumped),
                air_time=0.0 if start is None else max(0,now-start),demo=bool(c.is_demolished),
                world_contact=False,contact_normal=[0,0,0],previous=self.previous.tolist() if i==self.index else [0]*8))
        if len(cars) not in (2,4,6):raise ValueError('Native export supports 1v1, 2v2 and 3v3 only')
        timers=[0.0 if p.game_boosts[int(i)].is_active else max(0.0,float(d)-p.game_boosts[int(i)].timer)
                for i,d in zip(self.pad_order,self.pad_durations)]
        return dict(ball=physics(p.game_ball.physics),cars=cars,timers=timers)

    def get_output(self,p):
        now=p.game_info.seconds_elapsed
        if self.last_time is not None and now<self.last_time:
            self.tick=0;self.jumps.clear();self.previous=np.zeros(8,dtype=np.float32);self.held=self.previous.copy();self.pending=self.previous.copy()
            self.clock=NextoV4Clock(hardcoded=SCRIPTED_KICKOFF,stochastic=False)
        elapsed=1 if self.last_time is None else max(0,round((now-self.last_time)*120));self.last_time=now
        if elapsed:
            state=self.native_packet(p)
            positions=np.array([c['pos'][:2] for c in state['cars']]);teams=np.array([c['team'] for c in state['cars']])
            for _ in range(elapsed):
                state['cars'][self.index]['previous']=self.previous.tolist()
                if self.tick%8==0:self.pending=nexto_actions()[infer(self.actor,state,self.index+1)].copy()
                if self.tick%8==1:self.held=self.pending.copy()
                frame=self.clock.frame(is_kickoff_pause=p.game_info.is_kickoff_pause,ball_xy=state['ball']['pos'][:2],
                    positions=positions,teams=teams,index=self.index,infer=lambda prev,beta:(0,self.held))
                self.previous=frame.controls.copy();self.tick+=1
        a=self.previous
        return SimpleControllerState(throttle=float(a[0]),steer=float(a[1]),pitch=float(a[2]),yaw=float(a[3]),roll=float(a[4]),
                                     jump=bool(a[5]),boost=bool(a[6]),handbrake=bool(a[7]))
