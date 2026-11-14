"""RLBot v4 deployment. Uses public packet state and the training encoder."""
from pathlib import Path
import json,math
import numpy as np
import torch
from rlbot.agents.base_agent import BaseAgent,SimpleControllerState
from observation import encode,ACTIONS

class AttentionBot(BaseAgent):
    def initialize_agent(self):
        root=Path(__file__).resolve().parent
        torch.set_num_threads(1);self.model=torch.jit.load(str(root/'actor.pt'),map_location='cpu').eval();self.cfg=json.loads((root/'model_config.json').read_text());self.prev=np.zeros(8,np.float32);self.current=SimpleControllerState();self.pending=self.current;self.next_time=0.;self.apply_time=float('inf');self.last_time=-1.
        fi=self.get_field_info();self.locations=np.array([[p.location.x,p.location.y,p.location.z,float(p.is_full_boost)] for p in fi.boost_pads[:fi.num_boosts]],np.float32)
        if self.locations.shape!=(34,4):raise ValueError('AttentionForge supports standard Soccar with 34 pads only')
    @staticmethod
    def physics(row,p):
        row[:3]=[p.location.x,p.location.y,p.location.z];row[3:6]=[p.velocity.x,p.velocity.y,p.velocity.z];row[6:9]=[p.angular_velocity.x,p.angular_velocity.y,p.angular_velocity.z]
        r=p.rotation;cp=math.cos(r.pitch);sp=math.sin(r.pitch);cy=math.cos(r.yaw);sy=math.sin(r.yaw);cr=math.cos(r.roll);sr=math.sin(r.roll)
        row[9:12]=[cp*cy,cp*sy,sp];row[12:15]=[-cr*cy*sp-sr*sy,-cr*sy*sp+sr*cy,cp*cr]
    def get_output(self,packet):
        now=packet.game_info.seconds_elapsed
        if now<self.last_time:self.next_time=now;self.apply_time=float('inf');self.prev[:]=0
        self.last_time=now
        if now+1e-5>=self.apply_time:self.current=self.pending;self.apply_time=float('inf')
        if now+1e-5>=self.next_time:
            blue=[i for i in range(packet.num_cars) if packet.game_cars[i].team==0];orange=[i for i in range(packet.num_cars) if packet.game_cars[i].team==1];order=blue+orange
            if len(blue)!=len(orange) or len(blue) not in (1,2,3):return SimpleControllerState()
            world=np.zeros((1,len(order)+1,32),np.float32);self.physics(world[0,0],packet.game_ball.physics)
            for a,i in enumerate(order):
                car=packet.game_cars[i];row=world[0,a+1];self.physics(row,car.physics);row[15:21]=[car.boost,car.has_wheel_contact,car.jumped,car.double_jumped,car.is_super_sonic,car.is_demolished]
                if i==self.index:row[21:29]=self.prev
            pads=np.array([[[float(p.is_active),p.timer] for p in packet.game_boosts[:34]]],np.float32)
            ob,lm=encode(world,pads,self.locations);ego=order.index(self.index)
            with torch.no_grad():logits,_=self.model(torch.from_numpy(ob[:,ego]),torch.from_numpy(lm[:,ego]))
            c=ACTIONS[int(logits.argmax(-1))];self.prev=c.copy();self.pending=SimpleControllerState(throttle=float(c[0]),steer=float(c[1]),pitch=float(c[2]),yaw=float(c[3]),roll=float(c[4]),jump=bool(c[5]),boost=bool(c[6]),handbrake=bool(c[7]))
            self.apply_time=now+self.cfg['action_delay']/120;self.next_time=now+self.cfg['tick_skip']/120
            if self.cfg['action_delay']==0:self.current=self.pending;self.apply_time=float('inf')
        return self.current
