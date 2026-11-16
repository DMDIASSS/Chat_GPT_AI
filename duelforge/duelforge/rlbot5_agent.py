"""RLBot v5 packet/clock adapter. The model alone controls the exported car."""
from pathlib import Path
import json,math,logging
import numpy as np
import torch
try:from .observation import encode,ACTIONS
except ImportError:from observation import encode,ACTIONS

def physics(row,p):
    row[:3]=[p.location.x,p.location.y,p.location.z];row[3:6]=[p.velocity.x,p.velocity.y,p.velocity.z];row[6:9]=[p.angular_velocity.x,p.angular_velocity.y,p.angular_velocity.z]
    r=p.rotation;cp,sp=math.cos(r.pitch),math.sin(r.pitch);cy,sy=math.cos(r.yaw),math.sin(r.yaw);cr,sr=math.cos(r.roll),math.sin(r.roll)
    row[9:12]=[cp*cy,cp*sy,sp];row[12:15]=[-cr*cy*sp-sr*sy,-cr*sy*sp+sr*cy,cp*cr]

def packet_observation(packet,index,locations,previous):
    from rlbot.flat import AirState
    order=[i for team in (0,1) for i,c in enumerate(packet.players) if c.team==team]
    if len(order)!=2 or len({packet.players[i].team for i in order})!=2:raise ValueError('DuelForge prototype export is standard Soccar 1v1 only')
    world=np.zeros((1,3,32),np.float32);physics(world[0,0],packet.balls[0].physics)
    for a,i in enumerate(order):
        c=packet.players[i];q=world[0,a+1];physics(q,c.physics);ground=c.air_state==AirState.OnGround
        spent=c.has_double_jumped or c.has_dodged
        can=ground or (not spent and (not c.has_jumped or c.dodge_timeout>0))
        q[15:21]=[c.boost,ground,c.has_jumped,spent,c.is_supersonic,c.demolished_timeout>0];q[29]=can
        if i==index:q[21:29]=previous
    # RLBot timer counts UP since pickup; RocketSim cooldown counts DOWN.
    pads=np.asarray([[[float(p.is_active),0. if p.is_active else max(0.,(10. if locations[j,3] else 4.)-p.timer)] for j,p in enumerate(packet.boost_pads)]],np.float32)
    obs,mask=encode(world,pads,locations);a=order.index(index);return obs[:,a],mask[:,a]

class PolicyClock:
    def __init__(self,model,cfg,locations):self.model=model;self.cfg=cfg;self.locations=locations;self.reset()
    def reset(self):
        self.previous=np.zeros(8,np.float32);self.current=self.previous.copy();self.pending=self.previous.copy();self.apply=10**18;self.next=0;self.last=-1;self.decisions=0;self.last_time=-1;self.last_kickoff=False
    def controls(self,packet,index):
        from rlbot.flat import MatchPhase
        frame=int(packet.match_info.frame_num);clock=float(packet.match_info.seconds_elapsed);kickoff=packet.match_info.match_phase==MatchPhase.Kickoff
        if frame<self.last or clock<self.last_time or (kickoff and not self.last_kickoff):self.reset()
        self.last=frame;self.last_time=clock;self.last_kickoff=kickoff
        if frame>=self.apply:self.current=self.pending.copy();self.previous=self.current.copy();self.apply=10**18
        if frame>=self.next:
            x,l=packet_observation(packet,index,self.locations,self.previous)
            with torch.inference_mode():logits,_=self.model(torch.from_numpy(x),torch.from_numpy(l))
            self.pending=ACTIONS[int(logits.argmax(-1))].copy();self.apply=frame+self.cfg['action_delay'];self.next=frame+self.cfg['tick_skip'];self.decisions+=1
            if self.cfg['action_delay']==0:self.current=self.pending.copy();self.previous=self.current.copy();self.apply=10**18
        return self.current.copy()


def main():
    from rlbot.managers.hivemind import Hivemind
    from rlbot.flat import ControllerState,MatchPhase
    root=Path(__file__).resolve().parent;cfg=json.loads((root/'model_config.json').read_text());identity=json.loads((root/'identity.json').read_text())
    import hashlib,sys
    if hashlib.sha256((root/'actor.lt').read_bytes()).hexdigest()!=identity['actor_lt_sha256']:raise ValueError('Export actor hash differs from identity record')
    torch.set_num_threads(1);actor=torch.jit.load(str(root/'actor.lt'),map_location='cpu').eval()
    if '--diagnose' in sys.argv:
        with torch.inference_mode():logits,v=actor(torch.zeros(2,109),torch.ones(2,90,dtype=torch.bool))
        assert logits.shape==(2,90) and torch.isfinite(logits).all() and torch.isfinite(v).all();print('DUELFORGE_V5_MODEL_SDK_LOAD_PASS; no live match connection tested');return
    class DuelForge(Hivemind):
        def __init__(self):super().__init__(identity['agent_id']);self.clocks={}
        def initialize(self):
            self.locations=np.asarray([[p.location.x,p.location.y,p.location.z,float(p.is_full_boost)] for p in self.field_info.boost_pads],np.float32)
            if self.locations.shape!=(34,4):raise ValueError('34-pad Soccar field required')
            self._logger.info('DUELFORGE_READY: actor.lt loaded; Octane; skip8 delay7; model %s',identity['actor_lt_sha256'][:12])
        def get_outputs(self,packet):
            if not packet.balls or packet.match_info.match_phase not in (MatchPhase.Active,MatchPhase.Kickoff):
                self.clocks.clear();return {i:ControllerState() for i in self.indices}
            result={}
            for i in self.indices:
                if i not in self.clocks:self.clocks[i]=PolicyClock(actor,cfg,self.locations)
                c=self.clocks[i].controls(packet,i);result[i]=ControllerState(*[float(x) for x in c[:5]],*[bool(x) for x in c[5:]])
            return result
    DuelForge().run(wants_match_communications=False,wants_ball_predictions=False)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,handlers=[logging.FileHandler(Path(__file__).with_name('startup.log'),encoding='utf8'),logging.StreamHandler()]);main()
