"""Standalone RLBot packet observations and causal chunk execution; no training."""
from collections import deque
import math
import numpy as np
import torch
try:
    from replay_nexto_obs import NextoObsBuilder,BOOST_LOCATIONS,rotation_to_quaternion
except ModuleNotFoundError:
    from vendor.nexto.nexto_obs import NextoObsBuilder,BOOST_LOCATIONS,rotation_to_quaternion


def vector(value):return np.array([value.x,value.y,value.z],np.float64)


def rotation(value):
    cp,sp=math.cos(value.pitch),math.sin(value.pitch);cy,sy=math.cos(value.yaw),math.sin(value.yaw)
    cr,sr=math.cos(value.roll),math.sin(value.roll)
    return np.array([[cp*cy,cy*sp*sr-cr*sy,-cr*cy*sp-sr*sy],
        [cp*sy,sy*sp*sr+cr*cy,-cr*sy*sp+sr*cy],[sp,-cp*sr,cp*cr]],np.float64)


class PacketObserver:
    def __init__(self,field):
        pads=np.array([vector(field.boost_pads[i].location) for i in range(field.num_boosts)])
        if pads.shape!=(34,3):raise ValueError('Replay export requires standard Soccar with 34 boost pads')
        # FieldInfo reports pickup anchors at different heights from the legacy
        # training features. Identify pads on the field plane; keep canonical
        # training Z coordinates inside the builder, not packet anchor heights.
        distances=np.linalg.norm(np.asarray(BOOST_LOCATIONS)[:,None,:2]-pads[None,:,:2],axis=-1)
        self.pad_order=distances.argmin(1)
        if len(set(self.pad_order))!=34 or distances[np.arange(34),self.pad_order].max()>10:
            raise ValueError('Arena boost X/Y layout differs from the training observation contract')
        self.pad_xy_error=float(distances[np.arange(34),self.pad_order].max())
        self.builder=NextoObsBuilder(n_players=6,tick_skip=8);self.jumps={}

    def reset(self):self.jumps.clear()

    def observe(self,packet,index,previous):
        if not 1<=packet.num_cars<=6 or not 0<=index<packet.num_cars:raise ValueError('Replay model supports at most six cars')
        if any(packet.game_cars[i].team not in (0,1) for i in range(packet.num_cars)):raise ValueError('Unsupported car team')
        ordered=sorted(range(packet.num_cars),key=lambda i:(packet.game_cars[i].team,str(i)))
        row=np.zeros(55+38*len(ordered),np.float64)
        row[3:37]=[bool(packet.game_boosts[int(i)].is_active) for i in self.pad_order]
        ball=packet.game_ball.physics
        row[37:40]=vector(ball.location);row[40:43]=vector(ball.velocity);row[43:46]=vector(ball.angular_velocity)
        now=float(packet.game_info.seconds_elapsed)
        for position,car_index in enumerate(ordered):
            car=packet.game_cars[car_index];physics=car.physics;offset=55+38*position
            start=self.jumps.get(car_index)
            if car.has_wheel_contact or car.is_demolished or not car.jumped:start=None
            elif start is None:start=now
            self.jumps[car_index]=start
            has_flip=not bool(car.double_jumped) and (start is None or now-start<1.25)
            row[offset:offset+2]=position,car.team
            row[offset+2:offset+5]=vector(physics.location)
            row[offset+5:offset+9]=rotation_to_quaternion(rotation(physics.rotation))
            row[offset+9:offset+12]=vector(physics.velocity);row[offset+12:offset+15]=vector(physics.angular_velocity)
            row[offset+33:offset+35]=bool(car.is_demolished),bool(car.has_wheel_contact)
            row[offset+36:offset+38]=has_flip,float(car.boost)/100.
        if not np.isfinite(row).all():raise ValueError('Non-finite RLBot observation')
        ours=ordered.index(index);observations=self.builder.batched_build_obs(row[None])
        self.builder.add_actions(observations,np.asarray(previous,np.float64),ours)
        q,kv,mask=observations[ours]
        return q[0].astype(np.float32),kv[0].astype(np.float32),np.where(mask[0]>0,-10000.,mask[0]).astype(np.float32)


class ReplayController:
    def __init__(self,kernel,book,observer,*,history=8,device='cpu'):
        self.kernel=kernel;self.book=np.asarray(book,np.float32);self.observer=observer
        self.history=history;self.device=torch.device(device);self.features=deque(maxlen=history)
        if self.book.ndim!=3 or self.book.shape[1:]!=(32,8) or not np.isfinite(self.book).all():raise ValueError('Invalid replay action vocabulary')
        self.reset()

    def reset(self):
        self.features.clear();self.observer.reset();self.previous=np.zeros(8,np.float32)
        self.last_tick=None;self.decision_tick=None;self.selected=None;self.kickoff=None

    @torch.inference_mode()
    def output(self,packet,index):
        info=packet.game_info;now=float(info.seconds_elapsed)
        if not math.isfinite(now):raise ValueError('Invalid packet clock')
        tick=math.floor(now*120+.5);kickoff=bool(info.is_kickoff_pause)
        if (self.last_tick is not None and (tick<self.last_tick or tick-self.last_tick>16)) or (kickoff and self.kickoff is False):self.reset()
        self.kickoff=kickoff;self.last_tick=tick
        if not bool(info.is_round_active) or bool(info.is_match_ended) or packet.game_cars[index].is_demolished:
            self.reset();return self.previous.copy()
        if self.decision_tick is None or tick-self.decision_tick>=8:
            view=self.observer.observe(packet,index,self.previous)
            tensors=tuple(torch.as_tensor(x[None],device=self.device) for x in view)
            feature=self.kernel.encode(tensors)[0].detach();self.features.append(feature)
            features=list(self.features);features=[features[0]]*(self.history-len(features))+features
            logits,values=self.kernel.decode(torch.stack(features)[None])
            if logits.shape!=(1,len(self.book)) or not torch.isfinite(logits).all() or not torch.isfinite(values).all():
                raise ValueError('Replay policy returned invalid outputs')
            self.selected=int(logits[0].argmax());self.decision_tick=tick
        # Replan every eight ticks, retaining exact per-tick button/control edges.
        offset=min(7,max(0,tick-self.decision_tick))
        self.previous=self.book[self.selected,offset].copy()
        return self.previous.copy()
