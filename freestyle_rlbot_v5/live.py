"""RLBot v5 packets -> explicit Freestyle observations and timed controls."""
from __future__ import annotations
import math
import numpy as np

try:
    from .runtime import ACTIONS, PAD_LOCATIONS, History, observation, action_mask
except ImportError:
    from runtime import ACTIONS, PAD_LOCATIONS, History, observation, action_mask


def vector(v): return np.asarray((v.x,v.y,v.z),np.float32)


def rotation(r):
    cp,sp,cy,sy,cr,sr=math.cos(r.pitch),math.sin(r.pitch),math.cos(r.yaw),math.sin(r.yaw),math.cos(r.roll),math.sin(r.roll)
    return (np.asarray((cp*cy,cp*sy,sp),np.float32),
            np.asarray((cy*sp*sr-cr*sy,sy*sp*sr+cr*cy,-cp*sr),np.float32),
            np.asarray((-cr*cy*sp-sr*sy,-cr*sy*sp+sr*cy,cp*cr),np.float32))


def controls(c):
    return np.asarray((c.throttle,c.steer,c.pitch,c.yaw,c.roll,c.jump,c.boost,c.handbrake),np.float32)


class PacketAdapter:
    def __init__(self, field_info):
        if len(field_info.boost_pads)!=34:
            raise ValueError('Freestyle export supports standard Soccar arenas with 34 boost pads')
        locations=np.asarray([(p.location.x,p.location.y)for p in field_info.boost_pads])
        self.pad_indices=np.argmin(np.linalg.norm(PAD_LOCATIONS[:,None,:2]-locations[None,:,:],axis=2),axis=1)
        if len(set(self.pad_indices))!=34 or any(np.linalg.norm(PAD_LOCATIONS[i,:2]-locations[j])>5 for i,j in enumerate(self.pad_indices)):
            raise ValueError('Boost pad layout does not match the training arena')
        self.field_info=field_info;self.memory={};self.touches=set();self.touch_tokens={};self.last_frame=None

    def reset(self):
        self.memory.clear();self.touches.clear();self.touch_tokens.clear();self.last_frame=None

    def read(self, packet, decision=False):
        now=float(packet.match_info.seconds_elapsed);frame=int(packet.match_info.frame_num)
        dt=max(0,(frame-self.last_frame)/120) if self.last_frame is not None else 0
        self.last_frame=frame
        ids=[int(p.player_id)for p in packet.players]
        if len(set(ids))!=len(ids):ids=list(range(1,len(ids)+1))
        players=[];latest=(-1,-1)
        for index,p in enumerate(packet.players):
            car_id=ids[index];m=self.memory.setdefault(car_id,{})
            air=int(p.air_state);ground=air==0
            if ground:m['air_start']=now
            m.setdefault('air_start',now)
            if air==1 and m.get('air_state')!=1:m['jump_start']=now
            if m.get('air_state')==1 and air!=1:m['jump_end']=now
            if ground:m.pop('jump_end',None);m.pop('jump_start',None)
            if p.has_jumped and air!=1:
                since=max(0,now-m['jump_end']) if 'jump_end'in m else max(0,1.25-float(p.dodge_timeout))
            else:since=0
            # An expired timeout must disable dodges even when joining midair.
            if p.has_jumped and p.dodge_timeout<0 and not p.has_dodged and not p.has_double_jumped:
                since=max(1.25,since)
            m['brake']=float(np.clip(m.get('brake',0)+(5 if p.last_input.handbrake else -2)*dt,0,1))
            f,r,u=rotation(p.physics.rotation);position=vector(p.physics.location)
            turtled=not ground and position[2]<70 and u[2]<-.6 and abs(p.physics.velocity.z)<100
            normal=u if ground else np.asarray((0,0,1)if turtled else (0,0,0),np.float32)
            touch=p.latest_touch
            token=float(touch.game_seconds)if touch is not None and touch.ball_index==0 else -1
            if token>latest[0]:latest=(token,car_id)
            if car_id in self.touch_tokens and token>self.touch_tokens[car_id]:self.touches.add(car_id)
            self.touch_tokens[car_id]=token
            player={'carId':car_id,'team':int(p.team),'pos':position,'vel':vector(p.physics.velocity),
                'angVel':vector(p.physics.angular_velocity),'forward':f,'right':r,'up':u,
                'boost':float(p.boost),'isOnGround':ground,'hasJumped':bool(p.has_jumped),
                'hasDoubleJumped':bool(p.has_double_jumped),'hasFlipped':bool(p.has_dodged),
                'isFlipping':air==3,'isJumping':air==1,'isDemoed':p.demolished_timeout>0,
                'isSupersonic':bool(p.is_supersonic),'airTime':0 if ground else now-m['air_start'],
                'airTimeSinceJump':since,'jumpTime':min(.2,max(0,now-m.get('jump_start',now))),
                'flipTime':float(p.dodge_elapsed)if p.has_dodged else 0,
                'handbrakeVal':m['brake'],'demoRespawnTimer':max(0,float(p.demolished_timeout)),
                'ballTouchedStep':car_id in self.touches,'prevAction':controls(p.last_input),
                'worldContact':{'hasContact':ground or turtled,'contactNormal':normal}}
            players.append(player);m['air_state']=air
        ball=packet.balls[0].physics
        active=[];timers=[]
        for physical in self.pad_indices:
            p=packet.boost_pads[physical];active.append(bool(p.is_active))
            cooldown=10 if self.field_info.boost_pads[physical].is_full_boost else 4
            timers.append(0 if p.is_active else max(0,cooldown-float(p.timer)))
        result={'players':players,'ball':{'pos':vector(ball.location),'vel':vector(ball.velocity),'angVel':vector(ball.angular_velocity)},
                'boostPads':active,'boostPadTimers':timers,'goalScored':int(packet.match_info.match_phase)==4,
                'lastTouchCarID':latest[1],'deltaTime':dt,'now':now,'frame':frame}
        if decision:self.touches.clear()
        return result


class Kickoff:
    """Own basic kickoff routine, with one taker per team and a bounded handoff."""
    def __init__(self):self.started=None;self.flip_at=None;self.taker=False
    def reset(self):self.started=None;self.flip_at=None;self.taker=False

    def act(self, state, index, phase):
        ball=np.asarray(state['ball']['pos']);bv=np.asarray(state['ball']['vel']);now=state['now']
        if phase==2 and self.started is None and np.linalg.norm(ball[:2])<=150 and np.linalg.norm(bv)<=100:
            self.started=now;p=state['players'][index];sign=1 if p['team']==0 else -1
            same=[(i,q)for i,q in enumerate(state['players'])if q['team']==p['team']and not q['isDemoed']]
            minimum=min(np.linalg.norm(q['pos'][:2]-ball[:2])for _,q in same)
            ties=[(i,q)for i,q in same if np.linalg.norm(q['pos'][:2]-ball[:2])<=minimum+50]
            self.taker=index==min(ties,key=lambda iq:(-sign*iq[1]['pos'][0],iq[0]))[0]
        if self.started is None:return None
        if now-self.started>4.0 or np.linalg.norm(ball[:2])>150 or np.linalg.norm(bv)>100:
            self.reset();return None
        if not self.taker:return np.zeros(8,np.float32)
        p=state['players'][index];delta=ball-p['pos']
        angle=math.atan2(float(np.dot(p['right'],delta)),float(np.dot(p['forward'],delta)))
        action=np.asarray((1,np.clip(angle*3,-1,1),0,0,0,0,abs(angle)<.35 and p['boost']>0,0),np.float32)
        if self.flip_at is None and np.linalg.norm(delta)<700 and abs(angle)<.2:self.flip_at=now
        if self.flip_at is not None:
            elapsed=now-self.flip_at
            if elapsed<.08:action[5]=1
            elif .13<=elapsed<.25:action[5]=1;action[2]=-1
            elif elapsed<.65:action[2]=1
        return action


class LiveController:
    def __init__(self, infer, field_info, config):
        self.infer=infer;self.adapter=PacketAdapter(field_info);self.config=config
        self.history=History(config.get('reward_timings'));self.kickoff=Kickoff();self.frame=None;self.previous_phase=None
        self.held=np.zeros(8,np.float32);self.pending=None;self.next_decision=0;self.last_decision_time=None

    def act(self, packet, index):
        phase=int(packet.match_info.match_phase);now=float(packet.match_info.seconds_elapsed);frame=int(packet.match_info.frame_num)
        if len(packet.balls)!=1 or not 0<=index<len(packet.players) or len(packet.players)>6 or phase not in (2,3):
            self.history.reset(now);self.kickoff.reset();self.adapter.reset();self.pending=None
            self.frame=None;self.previous_phase=phase;self.held=np.zeros(8,np.float32)
            return self.held.copy()
        if self.frame==frame:return self.held.copy()
        reset=self.frame is None or frame<self.frame or self.previous_phase not in (2,3)
        if self.history.started is not None and now-self.history.started>=self.config['episode_seconds']:reset=True
        if reset:
            self.history.reset(now);self.adapter.reset();self.pending=None;self.next_decision=frame;self.last_decision_time=now
        self.frame=frame;self.previous_phase=phase
        # Every packet updates touch/resource history; only policy boundaries consume touches.
        decide=frame>=self.next_decision
        state=self.adapter.read(packet,decision=decide)
        if self.pending is not None and frame>=self.pending[0]:
            self.held=self.pending[1];self.pending=None
        if self.config['scripted_kickoff']:
            scripted=self.kickoff.act(state,index,phase)
            if scripted is not None:
                self.held=scripted;self.pending=None;self.next_decision=frame
                self.last_decision_time=now
                return self.held.copy()
        if not decide:return self.held.copy()
        state['deltaTime']=max(0,now-self.last_decision_time);self.last_decision_time=now
        own=state['players'][index];own_id=own['carId']
        self.history.update(state,own_id,now,self.config['difficulty'])
        context={'stage':self.config['stage'],'difficulty':self.config['difficulty'],
                 'elapsed':now-self.history.started,'episodeSeconds':self.config['episode_seconds'],'chain':self.history.chain}
        obs=observation(state,own_id,context);mask=action_mask(own)
        chosen=int(self.infer(obs,mask))
        if not 0<=chosen<94 or not mask[chosen]:raise RuntimeError('Policy selected an invalid action')
        action=ACTIONS[chosen].copy();delay=self.config['action_delay']
        if delay:self.pending=(frame+delay,action)
        else:self.held=action
        self.next_decision=frame+self.config['tick_skip']
        return self.held.copy()
