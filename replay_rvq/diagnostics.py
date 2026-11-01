"""Observe issued actions and stationary episodes without changing controls."""
from collections import deque
import math,time
import numpy as np


def chunk_summary(sequence):
    sequence=np.asarray(sequence)
    def part(values):
        return {'throttle_mean':float(values[:,0].mean()),
            'throttle_abs_max':float(np.abs(values[:,0]).max()),
            'steer_mean':float(values[:,1].mean()),
            'jump_ticks':int((values[:,5]>.5).sum()),
            'boost_ticks':int((values[:,6]>.5).sum()),
            'handbrake_ticks':int((values[:,7]>.5).sum())}
    prefix=part(sequence[:8]);later=part(sequence[8:])
    return {'executed_first8':prefix,'unexecuted_last24':later,
        'drive_only_after_executed_prefix':prefix['throttle_abs_max']<.1 and prefix['boost_ticks']==0
            and (later['throttle_abs_max']>.2 or later['boost_ticks']>0)}


class MotionAudit:
    def __init__(self):
        self.history=deque(maxlen=80);self.last_time=None;self.stationary_since=None
        self.last_episode=None
        self.was_active=None;self.last_inactive_trace=None
        self.clock_progress_wall=None
        self.previous_buttons=[False]*3;self.button_edges={name:{'press':0,'release':0} for name in ('jump','boost','handbrake')}

    def observe(self,packet,index,action,*,decisions,source,error=None,neutral_reason=None):
        now=float(packet.game_info.seconds_elapsed);car=packet.game_cars[index]
        physics=car.physics
        speed=math.sqrt(sum(float(getattr(physics.velocity,axis))**2 for axis in ('x','y','z')))
        position=[float(getattr(physics.location,axis)) for axis in ('x','y','z')]
        action=[float(x) for x in action]
        if not math.isfinite(now+speed+sum(position)+sum(action)):raise ValueError('Invalid motion audit inputs')
        wall=time.monotonic()
        if self.clock_progress_wall is None or now!=self.last_time:self.clock_progress_wall=wall
        for j,name in enumerate(('jump','boost','handbrake')):
            pressed=action[5+j]>.5
            if pressed!=self.previous_buttons[j]:self.button_edges[name]['press' if pressed else 'release']+=1
            self.previous_buttons[j]=pressed
        if self.last_time is not None and (now<self.last_time or now-self.last_time>1):
            self.history.clear();self.stationary_since=None
        active=bool(packet.game_info.is_round_active) and not packet.game_info.is_match_ended and not car.is_demolished
        if self.was_active and not active:self.last_inactive_trace=list(self.history)
        self.was_active=active
        if active and speed<25:
            if self.stationary_since is None:self.stationary_since=now
        else:self.stationary_since=None
        if not self.history or now-self.history[-1]['time']>=.1:
            def vector(value):return [float(getattr(value,axis)) for axis in ('x','y','z')]
            cars=[]
            for i in range(packet.num_cars):
                observed=packet.game_cars[i];pose=observed.physics
                cars.append({'index':i,'team':int(observed.team),'position':vector(pose.location),'velocity':vector(pose.velocity),
                    'rotation':[float(getattr(pose.rotation,axis)) for axis in ('pitch','yaw','roll')],
                    'boost':float(observed.boost),'wheel_contact':bool(observed.has_wheel_contact),
                    'demolished':bool(observed.is_demolished)})
            self.history.append({'time':now,'action':action,'decisions':int(decisions),'controlled_car':int(index),
                'cars':cars,'ball_position':vector(packet.game_ball.physics.location),'ball_velocity':vector(packet.game_ball.physics.velocity)})
        self.last_time=now
        duration=max(0.,now-self.stationary_since) if self.stationary_since is not None else 0.
        start=self.stationary_since if self.stationary_since is not None else now-3
        window=[row for row in self.history if row['time']>=max(now-3,start)]
        drive=sum(abs(row['action'][0])>.2 or row['action'][6]>.5 for row in window)/max(1,len(window))
        status='runtime_error' if error else 'inactive_or_demolished' if not active else 'moving_or_brief_wait'
        if active and duration>=2 and not error:
            status='stationary_with_drive_commands' if drive>=.5 else 'stationary_with_low_drive_commands'
        report={'status':status,'stationary_seconds':duration,'speed_uu_per_second':speed,
            'position':position,'issued_action':action,'action_order':['throttle','steer','pitch','yaw','roll','jump','boost','handbrake'],
            'source':source,'decisions_in_recent_window':int(decisions-window[0]['decisions']) if window else 0,
            'drive_command_fraction_recent_window':drive,'handbrake':bool(action[7]),
            'button_edges':{name:dict(counts) for name,counts in self.button_edges.items()},
            'runtime_error':error,'neutral_reason':neutral_reason,
            'wall_seconds_without_packet_clock_progress':max(0.,wall-self.clock_progress_wall),
            'recent_trace':list(self.history),
            'last_inactive_trace':self.last_inactive_trace,
            'note':'Stationary is an observation, not proof of a bug or tactical error. Controls are never modified.'}
        if active and duration>=2:
            self.last_episode={**report,'game_seconds':now}
        report['last_stationary_episode']=self.last_episode
        return report
