"""Physical curriculum checks. Streaks require varied cases; timeout is not a save."""
import copy,random,struct
from pathlib import Path
import numpy as np
from slater_native_eval import Controller
from slater_mechanics_core import MechanicTracker,wilson_lower
from slater_mechanics_env import configure_mechanic
from mechanics_scenarios import set_car,set_ball
STAGES=('touch_warmup','ground_score','replay_attack','replay_save','kickoff','boost_pickup','wall_roll','wall_pop','air_carry','air_finish','wall_to_air_finish','reset_acquire','reset_use','reset_finish','reset_double_tap')

def setup(state,stage,ours,enemy,seed,difficulty=0):
    rng=np.random.default_rng(seed);sign=1 if state.cars[ours].team_num==0 else -1;us=state.cars[ours];op=state.cars[enemy]
    if stage=='kickoff':return
    if stage in ('air_carry','air_finish','reset_acquire','reset_use','reset_finish','reset_double_tap'):
        configure_mechanic(state,'air_dribble' if stage=='air_carry' else 'reset_finish' if stage=='reset_double_tap' else stage,ours,enemy,seed,difficulty);return
    bp=np.array([rng.uniform(-600,600),rng.uniform(-1200,1200),93.]);cp=bp-[0,sign*(250+rng.uniform(0,500)*difficulty),76]
    if stage in ('wall_roll','wall_pop','wall_to_air_finish'):
        side=rng.choice((-1,1));bp=np.array([side*(3900 if stage=='wall_pop' else 3200),rng.uniform(-1200,1200),500 if stage=='wall_pop' else 93.]);cp=bp-[side*250,0,bp[2]-17]
    set_ball(state.ball,bp,[0,0,200 if stage=='wall_pop' else 0]);set_car(us,cp,bp,boost=80,on_ground=True)
    if stage=='boost_pickup':
        side=rng.choice((-1,1));set_car(us,[side*2600,-sign*3600,17],[side*3072,-sign*4096,17],boost=5,on_ground=True)
    if stage=='wall_pop':
        side=np.sign(bp[0]);set_car(us,[side*3980,bp[1],bp[2]-170],[side*3980,bp[1],bp[2]+200],up=[-side,0,0],boost=80,on_ground=False);us.physics.linear_velocity=np.array([0,0,350])
    set_car(op,[-2500,-sign*3500,17],bp,boost=50,on_ground=True)

class Tracker:
    def __init__(self,stage,state,ours,enemy):
        self.stage=stage;self.ours=ours;self.sign=1 if state.cars[ours].team_num==0 else -1;self.touch=False;self.wall=False;self.pop=False;self.boost=False;self.clear=False;self.backboard=False;self.retouch=False;self.seconds=0;self.first_touch=None;self.active=False
        mapped='air_finish' if stage=='wall_to_air_finish' else 'air_dribble' if stage=='air_carry' else 'reset_finish' if stage=='reset_double_tap' else stage
        self.mechanic=MechanicTracker(mapped,state,ours,enemy) if mapped in ('air_dribble','air_finish','reset_acquire','reset_use','reset_finish') else None
    def tick(self,before,after,controls):
        self.seconds+=1/120;self.active|=bool(np.any(controls));c=after.cars[self.ours];touch=bool(c.ball_touches)
        if self.first_touch is None and any(p.ball_touches for p in after.cars.values()):self.first_touch=touch
        self.touch|=touch;self.boost|=c.boost_amount-before.cars[self.ours].boost_amount>5
        if touch and abs(after.ball.position[0])>3300:self.wall=True
        if self.wall and touch and after.ball.position[2]>300 and abs(before.ball.position[0])>3700 and after.ball.position[0]*after.ball.linear_velocity[0]<0 and abs(after.ball.linear_velocity[0])>150:self.pop=True
        if self.touch and self.sign*after.ball.linear_velocity[1]>200 and (self.sign*after.ball.position[1]>-3800 or abs(after.ball.position[0])>1200):self.clear=True
        if self.mechanic:self.mechanic.tick(before,after,controls)
        if self.mechanic and self.mechanic.events.reset_used:
            if abs(after.ball.position[1])>4900 and after.ball.position[2]>750 and abs(after.ball.position[0])<1000 and self.sign*before.ball.linear_velocity[1]>0 and self.sign*after.ball.linear_velocity[1]<0 and not any(p.ball_touches for p in after.cars.values()):self.backboard=True
            if self.backboard and touch and self.sign*after.ball.linear_velocity[1]>150:self.retouch=True
    def success(self,state):
        scored=state.goal_scored and self.sign*state.ball.position[1]>0;conceded=state.goal_scored and not scored
        if self.stage=='touch_warmup':return self.touch and self.active
        if self.stage in ('ground_score','replay_attack'):return bool(scored and self.touch and self.active)
        if self.stage=='replay_save':return self.touch and self.clear and self.active and not conceded
        if self.stage=='kickoff':return self.first_touch is True
        if self.stage=='boost_pickup':return self.boost
        if self.stage=='wall_roll':return self.wall and state.ball.position[2]>180
        if self.stage=='wall_pop':return self.pop
        if self.stage=='wall_to_air_finish':return self.wall and self.pop and self.mechanic.events.success
        if self.stage=='reset_double_tap':return bool(scored and self.retouch and self.mechanic.events.success)
        return bool(self.mechanic.events.success)

def from_bank(engine,bank,row_index):
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
    with open(bank,'rb') as f:
        f.read(4);version,players,count,width=struct.unpack('<IIII',f.read(16))
        if version!=1 or players!=2 or width!=231 or not 0<=row_index<count:raise ValueError('Invalid duel row')
        f.seek(20+(720+102)*4+row_index*width*4);r=np.frombuffer(f.read(width*4),dtype='<f4')
    state=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(state,{})
    def assign(p,b):p.position=b[:3].copy();p.rotation_mtx=b[3:12].reshape(3,3).T.copy();p.linear_velocity=b[12:15].copy();p.angular_velocity=b[15:18].copy()
    assign(state.ball,r);state.boost_pad_timers=r[18:52].copy()
    for i,aid in enumerate(sorted(state.cars,key=lambda k:state.cars[k].team_num)):
        c=state.cars[aid];b=r[52+43*i:95+43*i];assign(c.physics,b);c.boost_amount=float(b[18]);c.has_jumped=bool(b[20]);c.has_double_jumped=bool(b[21]);c.has_flipped=bool(b[22]);c.is_jumping=bool(b[23]);c.jump_time=float(b[24]);c.flip_time=float(b[25]);c.air_time_since_jump=float(b[26]);c.flip_torque=b[35:38].copy();c.wheels_with_contact=b[38:42].astype(bool);c.is_flipping=bool(b[42])
    return state

def episode(actor,rival,stage,*,seed,side,seconds=12,difficulty=0,window=None,bank=None):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from afk_team_research import TeamObserver
    team=0 if side=='blue' else 1;ours=('blue-' if team==0 else 'orange-')+'0';enemy=('orange-' if team==0 else 'blue-')+'0'
    engine=RocketSimEngine(rlbot_delay=False);observer=TeamObserver();state=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(state,{})
    random.seed(seed);KickoffMutator().apply(state,{})
    if window is not None:
        state=from_bank(engine,bank,window['start_row']);seconds=min(seconds,len(window['controls'])/15)
    else:setup(state,stage,ours,enemy,seed,difficulty)
    try:
        state=engine.set_state(state,{});learner=Controller(actor,scripted=False);opponent=Controller(rival,scripted=True);tracker=Tracker(stage,state,ours,enemy);previous={};idle=0;touches=0;touched=False;native_ticks=round(seconds*120)
        for tick in range(native_ticks):
            kickoff=stage=='kickoff' and not touched and tick<168 and np.linalg.norm(state.ball.position[:2])<1
            a=learner.controls(state,ours,previous,engine,tick,kickoff,observer)
            b=np.array(window['controls'][min(tick//8,len(window['controls'])-1)][1-team],dtype=np.float32) if window is not None else opponent.controls(state,enemy,previous,engine,tick,kickoff,observer)
            before=state;state=engine.step({ours:a[None],enemy:b[None]},{});tracker.tick(before,state,a);previous={ours:a.copy(),enemy:b.copy()};idle+=int(not np.any(a));touches+=int(state.cars[ours].ball_touches>0);touched|=any(c.ball_touches for c in state.cars.values())
            if state.goal_scored:break
        return dict(seed=seed,side=side,success=bool(tracker.success(state)),goal_scored=bool(state.goal_scored and tracker.sign*state.ball.position[1]>0),conceded=bool(state.goal_scored and tracker.sign*state.ball.position[1]<0),idle_fraction=idle/(tick+1),touch_ticks=touches,seconds=(tick+1)/120,window=window.get('replay_group',window.get('replay_sha')) if window else None)
    finally:engine.close()

def mastery(records,required_streak=10):
    if not 5<=required_streak<=15:raise ValueError('Use 5..15 consecutive successes')
    by_side={side:[r for r in records if r['side']==side] for side in ('blue','orange')};streaks={};lowers={}
    for side,rows in by_side.items():
        if len({r['seed'] for r in rows})!=len(rows):raise ValueError('Duplicate mastery case')
        streak=0
        for r in rows:streak=streak+1 if r['success'] else 0
        streaks[side]=streak
        if rows and any(r.get('window') for r in rows):
            groups={}
            for r in rows:groups.setdefault(r['window'],[]).append(r['success'])
            lowers[side]=wilson_lower(sum(all(v) for v in groups.values()),len(groups)) if len(groups)>=5 else 0
        else:lowers[side]=wilson_lower(sum(r['success'] for r in rows),len(rows)) if rows else 0
    passed=all(streaks[s]>=required_streak and lowers[s]>=.6 for s in by_side)
    return dict(passed=passed,streaks=streaks,wilson_lower=lowers,required_streak=required_streak,note='Varied drill success; not proof of competitive rank.')
