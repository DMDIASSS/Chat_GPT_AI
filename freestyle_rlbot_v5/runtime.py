"""Freestyle flat512/stall94 inference contract. No training or RLBot dependency."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import numpy as np

OBS_SCHEMA = 'slater_freestyle_flat512_v1'
ACTION_SCHEMA = 'slater_freestyle_94_stall_v1'
STAGES = ('contact_pop', 'air_carry', 'reset_acquire', 'reset_use', 'multi_reset',
          'pinch_proxy', 'double_tap_proxy', 'psycho_proxy', 'wall_recovery', 'walldash_proxy')
PAD_LOCATIONS = np.asarray([
    (0,-4240,70),(-1792,-4184,70),(1792,-4184,70),(-3072,-4096,73),(3072,-4096,73),
    (-940,-3308,70),(940,-3308,70),(0,-2816,70),(-3584,-2484,70),(3584,-2484,70),
    (-1788,-2300,70),(1788,-2300,70),(-2048,-1036,70),(0,-1024,70),(2048,-1036,70),
    (-3584,0,73),(-1024,0,70),(1024,0,70),(3584,0,73),(-2048,1036,70),(0,1024,70),
    (2048,1036,70),(-1788,2300,70),(1788,2300,70),(-3584,2484,70),(3584,2484,70),
    (0,2816,70),(-940,3310,70),(940,3308,70),(-3072,4096,73),(3072,4096,73),
    (-1792,4184,70),(1792,4184,70),(0,4240,70)], dtype=np.float32)


def unit(value):
    value = np.asarray(value, dtype=np.float32)
    length = float(np.linalg.norm(value))
    return value / length if length > 1e-5 else np.zeros(3, np.float32)


def available(player):
    return bool(player.get('isOnGround', False) or
                (not player.get('hasFlipped', False) and not player.get('hasDoubleJumped', False)
                 and player.get('airTimeSinceJump', 0) < 1.25))


def action_table():
    actions = []
    for throttle in (-1, 0, 1):
        for steer in (-1, 0, 1):
            for boost in (0, 1):
                for brake in (0, 1):
                    if boost and throttle != 1:
                        continue
                    actions.append((throttle, steer, 0, steer, 0, 0, boost, brake))
    ground_count = len(actions)
    for pitch in (-1, 0, 1):
        for yaw in (-1, 0, 1):
            for roll in (-1, 0, 1):
                for jump in (0, 1):
                    for boost in (0, 1):
                        if jump and yaw or pitch == roll == jump == 0:
                            continue
                        brake = int(jump and (pitch != 0 or yaw != 0 or roll != 0))
                        actions.append((boost, yaw, pitch, yaw, roll, jump, boost, brake))
    ground = np.zeros(94, bool); air = ground.copy()
    for i, action in enumerate(actions):
        ground[i] = i < ground_count
        air[i] = i > ground_count and not action[5]
        if i < ground_count and action[0] == action[6] and (action[3] != 0) == bool(action[7]):
            air[i] = True
    for yaw in (-1, 1):
        for boost in (0, 1):
            actions.append((boost, yaw, 0, yaw, -yaw, 1, boost, 1))
    return np.asarray(actions, np.float32), ground, air


ACTIONS, GROUND_MASK, AIR_MASK = action_table()


def action_mask(player):
    mask = (GROUND_MASK if player.get('isOnGround') else AIR_MASK).copy()
    contact = player.get('worldContact', {})
    turtled = contact.get('hasContact', False) and contact.get('contactNormal', (0, 0, 0))[2] > .9
    if available(player) or turtled:
        mask |= ACTIONS[:, 5] != 0
    if player.get('boost', 0) <= 0:
        mask &= ACTIONS[:, 6] == 0
    if not mask.any():
        raise RuntimeError('No valid Freestyle control actions')
    return mask


def observation(state, player_id, context):
    """Mirror FreestyleObs.h with simulator-only fields explicitly masked."""
    players, ball = state['players'], state['ball']
    if not 1 <= len(players) <= 6 or len(state['boostPads']) != 34 or len(state['boostPadTimers']) != 34:
        raise ValueError('Freestyle needs 1..6 players and 34 standard Soccar pads')
    p = next(p for p in players if p['carId'] == player_id)
    pos = np.asarray(p['pos'], np.float32); vel = np.asarray(p['vel'], np.float32)
    bp = np.asarray(ball['pos'], np.float32); bv = np.asarray(ball['vel'], np.float32)
    basis = np.asarray([p['forward'], p['right'], p['up']], np.float32)
    sign = 1 if p['team'] == 0 else -1
    flip = np.asarray((sign, sign, 1), np.float32)
    values = []

    def add(value): values.append(float(value))
    def vec(value, scale=1):
        for v in np.asarray(value, np.float32) * np.float32(scale): add(v)
    def local(value): return basis @ np.asarray(value, np.float32)
    def clip(value): return float(np.clip(value, 0, 1))

    vec(bp * flip, 1/6000); vec(bv * flip, 1/6000); vec(np.asarray(ball['angVel']) * flip, 1/6)
    for key, scale in (('pos',1/6000),('vel',1/2300),('angVel',1/5.5),('forward',1),('right',1),('up',1)):
        vec(np.asarray(p[key]) * flip, scale)
    delta, relative_vel = bp-pos, bv-vel
    vec(delta * flip, 1/6000); vec(relative_vel * flip, 1/6000)
    vec(local(delta), 1/2300); vec(local(relative_vel), 1/2300)
    vec(local(vel), 1/2300); vec(local(p['angVel']), 1/5.5)
    for v in (p['boost']/100, p['isOnGround'], p['hasJumped'], p['hasDoubleJumped'],
              p['hasFlipped'], p['isFlipping'], p['isJumping'], available(p), p['isDemoed'],
              p['isSupersonic'], clip(p['airTime']/5), clip(p['airTimeSinceJump']/1.25),
              clip(p['jumpTime']/.2), clip(p['flipTime']/1.5), p['handbrakeVal'],
              clip(p['demoRespawnTimer']/3), p['ballTouchedStep']): add(v)
    # Always use the dropout path trained by the native backend; no fake wheel/reset flags.
    vec(np.zeros(3)); vec(np.zeros(3)); vec(np.zeros(3)); add(0)
    for v in ((4096-abs(pos[0]))/4096, (5120-abs(pos[1]))/5120, pos[2]/2044,
              (2044-pos[2])/2044, abs(pos[0])>3750 and pos[2]>150, abs(pos[1])>4800 and pos[2]>650): add(v)
    vec(local(np.asarray((0,sign*5120,320))-pos),1/6000)
    vec(local(np.asarray((0,-sign*5120,320))-pos),1/6000)
    for v in p['prevAction']: add(v)
    for stage in range(10): add(stage == context['stage'])
    elapsed, duration = context['elapsed'], context['episodeSeconds']
    add(context['difficulty']); add(clip(elapsed/duration)); add(clip((duration-elapsed)/duration))
    c = context.get('chain', {})
    for v in (clip((elapsed-c.get('lastTouch',-100))/2),clip((elapsed-c.get('lastNoseTouch',-100))/2),
              c.get('carry',0)/3,c.get('bestCarry',0)/3,c.get('carryDistance',0)/2000,
              c.get('wall',False),c.get('pop',False),clip((elapsed-c.get('wallAt',-100))/3),
              clip((elapsed-c.get('popAt',-100))/3),clip(c.get('noseTouches',0)/4),
              0,0,0,0,c.get('pinch',False),c.get('board',False),c.get('retouch',False),
              c.get('ownBoard',False),c.get('recovered',False),clip(c.get('wallDashes',0)/3)): add(v)
    for pad in range(34):
        physical = pad if sign > 0 else 33-pad
        vec(local(PAD_LOCATIONS[physical]-pos),1/6000)
        add(state['boostPads'][physical]); add(clip(state['boostPadTimers'][physical]/10))
    others = sorted((x for x in players if x['carId'] != player_id),
                    key=lambda x:(x['team'] != p['team'],x['carId']))
    for i in range(5):
        start = len(values)
        if i < len(others):
            q = others[i]; qp=np.asarray(q['pos']); qv=np.asarray(q['vel'])
            add(1); add(1 if q['team']==p['team'] else -1)
            vec(local(qp-pos),1/6000);vec(local(qv-vel),1/2300)
            vec(local(q['forward']));vec(local(q['up']));vec(local(q['angVel']),1/5.5)
            for v in (q['boost']/100,q['isOnGround'],available(q),q['isDemoed'],
                      clip(q['demoRespawnTimer']/3),q['ballTouchedStep'],
                      np.linalg.norm(qp-bp)/6000,np.linalg.norm(qv)/2300,
                      q['hasJumped'],q['hasDoubleJumped'],q['hasFlipped'],q['isFlipping'],
                      clip(q['airTime']/5),q['isSupersonic'],q['handbrakeVal']): add(v)
        values.extend([0.] * (33-(len(values)-start)))
    for horizon in (.15,.35,.7):
        predicted = bp + bv*np.float32(horizon) + np.asarray((0,0,-325*horizon*horizon),np.float32)
        predicted_vel = bv + np.asarray((0,0,-650*horizon),np.float32)
        vec(local(predicted-pos),1/6000);vec(local(predicted_vel-vel),1/6000)
    add(np.linalg.norm(delta)/6000);add(np.dot(basis[0],unit(delta)));add(-np.dot(basis[2],unit(delta)))
    add(clip((2044-bp[2])/2044));add(state['goalScored']);add(state['lastTouchCarID']==player_id)
    if len(values)>512: raise RuntimeError('Freestyle observation overflow')
    values.extend([0.]*(512-len(values)))
    result=np.asarray(values,np.float32)
    if not np.isfinite(result).all(): raise ValueError('Nonfinite live observation')
    return np.clip(result,-4,4)


class History:
    """Observable reward-chain history. Simulator-only resets stay masked."""
    def __init__(self, timings=None):
        self.chain = {}; self.previous = None; self.started = None
        self.timings=timings or {}

    def reset(self, now):
        self.chain={};self.previous=None;self.started=now

    def update(self, state, player_id, now, difficulty):
        c=self.chain;p=next(p for p in state['players']if p['carId']==player_id);b=state['ball']
        pos=np.asarray(p['pos']);vel=np.asarray(p['vel']);bp=np.asarray(b['pos']);bv=np.asarray(b['vel'])
        dt=state['deltaTime'];elapsed=now-self.started
        old=self.previous;old_ball=old['ball']if old else b
        delta=bp-pos;direction=unit(delta);distance=np.linalg.norm(delta);sign=1 if p['team']==0 else -1
        free=not p['isOnGround'] and not p['worldContact']['hasContact'] and pos[2]>180
        wall=abs(pos[0])>3750 and pos[2]>150 and p['worldContact']['hasContact'] and abs(p['up'][0])>.6
        active=c.get('active',False) or sum(abs(x)for x in p['prevAction'])>.05;c['active']=active
        if 'recoveryNeeded' not in c:
            c['recoveryNeeded']=not p['isOnGround'] or p['up'][2]<.5
            c['recoveryStart']=0 if c['recoveryNeeded'] else -100
        if p['ballTouchedStep'] and active:
            wall_before=c.get('wall',False);previous_wall=c.get('wallAt',-100)
            c['lastTouch']=elapsed
            if abs(bp[0])>3850 and bp[2]>140 and wall and bv[2]>60:
                c.update(wall=True,wallAt=elapsed)
            if wall_before and not c.get('pop') and elapsed-previous_wall<2.5 and bp[2]>250 and bp[0]*bv[0]<0 and abs(bv[0])>180:
                c.update(pop=True,popAt=elapsed)
            if not c.get('pop') and old and old_ball['pos'][2]<180 and pos[2]<200 and bv[2]>80 and bv[2]-old_ball['vel'][2]>60:
                c.update(pendingLift=True,liftAt=elapsed,liftStartHeight=old_ball['pos'][2])
            if free and bp[2]>300:
                c['lastAirTouch']=elapsed
                if c.get('pop') and .08<elapsed-c.get('popAt',-100)<2.5:c['popRetouch']=True
                if np.dot(p['forward'],direction)>.45 and abs(np.dot(p['right'],delta))<110 and np.dot(p['up'],delta)>-40 and elapsed-c.get('lastNoseTouch',-100)>=self.timings.get('touch_spacing',.12):
                    c['lastNoseTouch']=elapsed;c['noseTouches']=c.get('noseTouches',0)+1
        if c.get('pendingLift') and not c.get('pop') and elapsed-c['liftAt']<=.8 and state['lastTouchCarID']==player_id and bp[2]>110 and bp[2]-c['liftStartHeight']>=30+70*difficulty:
            c.update(pop=True,popAt=elapsed,pendingLift=False)
        carry=active and free and bp[2]>300 and distance<240 and np.linalg.norm(bv-vel)<650 and elapsed-c.get('lastNoseTouch',-100)<self.timings.get('carry_touch_deadline',.35) and sign*bv[1]>120 and np.dot(p['forward'],direction)>.3
        c['carry']=c.get('carry',0)+dt if carry else 0
        if carry:
            c['bestCarry']=max(c.get('bestCarry',0),c['carry'])
            c['carryDistance']=c.get('carryDistance',0)+max(0,sign*(bp[1]-c.get('lastBall',bp)[1]))
        if p['ballTouchedStep'] and active and not c.get('pinch'):
            ground=bp[2]<120 and pos[2]>bp[2]+25 and np.linalg.norm(delta[:2])<140 and vel[2]-old_ball['vel'][2]<-150
            side=abs(bp[0])>3960 and abs(pos[0])<abs(bp[0])-25 and bp[0]*bv[0]<0
            ceiling=bp[2]>1930 and pos[2]<bp[2]-25 and np.linalg.norm(delta[:2])<140 and bv[2]<-300
            if (ground or side or ceiling) and np.dot(vel-old_ball['vel'],direction)>200 and distance<220 and np.linalg.norm(bv-old_ball['vel'])>1000 and np.linalg.norm(bv)>2000 and sign*bv[1]>120:
                c['pinch']=True
        if old and not c.get('board') and c.get('lastTouch',-100)>=0 and elapsed-c['lastTouch']<2.5 and abs(bp[1])>4880 and bp[2]>700 and abs(bp[0])<1200 and old_ball['vel'][1]*bv[1]<0 and abs(old_ball['vel'][1])>200:
            c.update(board=True,boardAt=elapsed,ownBoard=sign*bp[1]<0)
        if p['ballTouchedStep'] and active and c.get('board') and not c.get('retouch') and elapsed-c['boardAt']<3 and free and sign*bv[1]>120:c['retouch']=True
        if c.get('recoveryNeeded') and not c.get('recovered') and elapsed-c['recoveryStart']<4 and p['isOnGround'] and np.linalg.norm(p['angVel'])<2 and np.linalg.norm(vel)>150 and active and ((pos[2]<100 and p['up'][2]>.75)or wall):c['recovered']=True
        if wall:
            if p['prevAction'][5]>.5 and not c.get('lastJump',False):c.update(wallLaunchAt=elapsed,wallSpeedBefore=float(np.linalg.norm(vel)))
            if old:
                prev=next(q for q in old['players']if q['carId']==player_id)
                if p['hasFlipped']and not prev['hasFlipped']and elapsed-c.get('wallLaunchAt',-100)<.7 and np.linalg.norm(vel)-c.get('wallSpeedBefore',0)>100 and active:
                    c['wallDashes']=c.get('wallDashes',0)+1;c['wallLaunchAt']=-100
        c['lastJump']=p['prevAction'][5]>.5;c['lastBall']=bp.copy()
        self.previous=state
