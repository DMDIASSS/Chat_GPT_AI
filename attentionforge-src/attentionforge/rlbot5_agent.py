"""RLBot v5 public-packet adapter and one-tick action-delay clock.
Deployed policy is TorchScript, with no tutor, search or scripted kickoff.
"""
from pathlib import Path
import json,math,logging
import numpy as np
import torch
try:
    from .observation import encode_reference as encode,ACTIONS
except ImportError:
    from observation import encode_reference as encode,ACTIONS


def physics(row,p):
    row[:3]=[p.location.x,p.location.y,p.location.z];row[3:6]=[p.velocity.x,p.velocity.y,p.velocity.z];row[6:9]=[p.angular_velocity.x,p.angular_velocity.y,p.angular_velocity.z]
    r=p.rotation;cp=math.cos(r.pitch);sp=math.sin(r.pitch);cy=math.cos(r.yaw);sy=math.sin(r.yaw);cr=math.cos(r.roll);sr=math.sin(r.roll)
    row[9:12]=[cp*cy,cp*sy,sp];row[12:15]=[-cr*cy*sp-sr*sy,-cr*sy*sp+sr*cy,cp*cr]


def packet_observation(packet,index,locations,previous):
    from rlbot.flat import AirState
    order=[i for t in (0,1) for i,c in enumerate(packet.players) if c.team==t]
    blue=sum(c.team==0 for c in packet.players)
    if len(order)!=blue*2 or blue not in (1,2,3):raise ValueError('Balanced Soccar teams required')
    world=np.zeros((1,len(order)+1,32),np.float32);physics(world[0,0],packet.balls[0].physics)
    for a,i in enumerate(order):
        c=packet.players[i];row=world[0,a+1];physics(row,c.physics)
        row[15:21]=[c.boost,c.air_state==AirState.OnGround,c.has_jumped,c.has_double_jumped or c.has_dodged,c.is_supersonic,c.demolished_timeout>0]
        if i==index:row[21:29]=previous
    pads=np.asarray([[[float(p.is_active),p.timer] for p in packet.boost_pads]],np.float32)
    x,l=encode(world,pads,locations);a=order.index(index);return x[:,a],l[:,a]

class PolicyClock:
    def __init__(self,model,cfg,locations):
        self.model=model;self.cfg=cfg;self.locations=locations;self.reset()
    def reset(self):
        self.previous=np.zeros(8,np.float32);self.current=self.previous.copy();self.pending=self.previous.copy();self.apply=10**18;self.next=0;self.last=-1;self.decisions=0
    def controls(self,packet,index):
        frame=int(packet.match_info.frame_num)
        if frame<self.last:self.reset()
        self.last=frame
        if frame>=self.apply:self.current=self.pending.copy();self.apply=10**18
        if frame>=self.next:
            x,l=packet_observation(packet,index,self.locations,self.previous)
            with torch.inference_mode():logits,_=self.model(torch.from_numpy(x),torch.from_numpy(l))
            self.pending=ACTIONS[int(logits.argmax(-1))].copy();self.previous=self.pending.copy();self.apply=frame+self.cfg['action_delay'];self.next=frame+self.cfg['tick_skip'];self.decisions+=1
            if self.cfg['action_delay']==0:self.current=self.pending.copy();self.apply=10**18
        return self.current.copy()

def main():
    from rlbot.managers.hivemind import Hivemind
    from rlbot.flat import ControllerState,MatchPhase
    root=Path(__file__).resolve().parent;cfg=json.loads((root/'model_config.json').read_text())
    torch.set_num_threads(1);model=torch.jit.load(str(root/'actor.lt'),map_location='cpu').eval()
    import sys
    if '--diagnose' in sys.argv:
        x=torch.zeros(2,43,40);x[:,0,39]=1;x[:,1,39]=2
        with torch.inference_mode():a,v=model(x,torch.ones(2,90,dtype=torch.bool))
        assert a.shape==(2,90) and torch.isfinite(a).all() and torch.isfinite(v).all()
        print('V5_MODEL_SDK_DIAGNOSE_PASS: actor.lt loaded, finite logits, SDK import. No live connection tested.');return
    class AttentionSkills(Hivemind):
        def __init__(self):super().__init__(json.loads((root/'runtime_v5.json').read_text())['agent_id']);self.clocks={}
        def initialize(self):
            self.locations=np.asarray([[p.location.x,p.location.y,p.location.z,float(p.is_full_boost)] for p in self.field_info.boost_pads],np.float32)
            if self.locations.shape!=(34,4):raise ValueError('Standard Soccar with 34 pads required')
            self._logger.info('ATTENTION_SKILLS_READY: actor.lt loaded; Octane, tick_skip=%s delay=%s',cfg['tick_skip'],cfg['action_delay'])
        def get_outputs(self,packet):
            if not packet.balls or packet.match_info.match_phase not in (MatchPhase.Active,MatchPhase.Kickoff):
                self.clocks.clear();return {i:ControllerState() for i in self.indices}
            result={}
            for i in self.indices:
                if i not in self.clocks:self.clocks[i]=PolicyClock(model,cfg,self.locations)
                c=self.clocks[i].controls(packet,i);result[i]=ControllerState(*[float(x) for x in c[:5]],*[bool(x) for x in c[5:]])
            return result
    AttentionSkills().run(wants_match_communications=False,wants_ball_predictions=False)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,handlers=[logging.FileHandler(Path(__file__).with_name('startup.log'),encoding='utf8'),logging.StreamHandler()]);main()
