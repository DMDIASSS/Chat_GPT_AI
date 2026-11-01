"""Small real RocketSim worlds, explicit goal rewards and recovery starts."""
import math,random
from collections import deque
import numpy as np
from replay_rvq.packet import StateObserver

TICKS=8
GAMMA=math.exp(-(TICKS/120)/15.)


def potential(state,orange):
    sign=-1. if orange else 1.
    return .1*math.tanh(sign*float(state.ball.position[1])/5120.)


def reward(before,after,orange,goal):
    signed_goal=(1. if (float(after.ball.position[1])>0)!=orange else -1.) if goal else 0.
    # Exactly gamma*Phi(next)-Phi(previous), with zero terminal potential.
    # No clipping, touch/jump reward or circular progress farming.
    return signed_goal+GAMMA*(0. if goal else potential(after,orange))-potential(before,orange)


def basis(yaw,roll=0.):
    cy,sy=math.cos(yaw),math.sin(yaw);cr,sr=math.cos(roll),math.sin(roll)
    return np.array([[cy,-sy*cr,sy*sr],[sy,cy*cr,-cy*sr],[0,sr,cr]],np.float32)


class World:
    def __init__(self,seed=0,team_size=1,*,curriculum=True,episode_seconds=60,opponents=('source','chaser','peer'),fixed_orange=None):
        from rlgym.rocket_league.sim import RocketSimEngine
        if team_size not in (1,2,3) or episode_seconds<1:raise ValueError('Invalid Soccar world configuration')
        self.engine=RocketSimEngine(rlbot_delay=False);self.observer=StateObserver();self.rng=np.random.default_rng(seed)
        self.team_size=team_size;self.curriculum=curriculum;self.limit=round(episode_seconds*120/TICKS)
        self.fixed_orange=fixed_orange;self.opponents=tuple(opponents);self.goal_examples=deque(maxlen=4096);self.pending=deque(maxlen=450)
        self.reset()

    def reset(self,*,orange=None,scenario=None):
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
        state=self.engine.create_base_state();FixedTeamSizeMutator(self.team_size,self.team_size).apply(state,{})
        prior=random.getstate()
        try:KickoffMutator().apply(state,{})
        finally:random.setstate(prior) # Spawn slots below use only this world's RNG.
        if orange is None:orange=self.fixed_orange
        self.orange=bool(self.rng.integers(2)) if orange is None else bool(orange)
        self.opponent=str(self.rng.choice(self.opponents));self.decisions=0;self.previous={};self.pending.clear();self.last_touch=None
        self.scenario=scenario or (str(self.rng.choice(['kickoff','attack','defend','recover','aerial'],p=[.2,.25,.3,.1,.15])) if self.curriculum else 'kickoff')
        state.cars={i:car for i,car in enumerate(state.cars.values())}
        slots=np.array([[-2048,-2560],[2048,-2560],[-256,-3840],[256,-3840],[0,-4608]],np.float32)
        selected=self.rng.choice(len(slots),self.team_size,replace=False)
        for team in (0,1):
            side=[car for car in state.cars.values() if car.team_num==team]
            for car,slot in zip(side,slots[selected]):
                sign=-1 if team else 1;car.physics.position=np.array([slot[0]*sign,slot[1]*sign,17.1],np.float32)
                target=-car.physics.position[:2];car.physics.rotation_mtx=basis(math.atan2(target[1],target[0]))
                car.physics.linear_velocity=np.zeros(3,np.float32);car.physics.angular_velocity=np.zeros(3,np.float32)
                car.boost_amount=34.;car.on_ground=True
        if self.scenario!='kickoff':self._scenario(state)
        self.state=self.engine.set_state(state,{})
        self.ours=[aid for aid,car in self.state.cars.items() if car.is_orange==self.orange]
        self.theirs=[aid for aid in self.state.cars if aid not in self.ours]
        return self.observe()

    def _scenario(self,state):
        sign=-1. if self.orange else 1.;x=float(self.rng.uniform(-900,900))
        defending=self.scenario=='defend'
        y=sign*float(self.rng.uniform(2000,3100))*(-1 if defending else 1)
        state.ball.position=np.array([x,y,self.rng.uniform(100,210)],np.float32)
        toward=-sign if defending else sign
        state.ball.linear_velocity=np.array([-x*.25,toward*self.rng.uniform(500,1000),0],np.float32) if defending else np.array([self.rng.uniform(-100,100),self.rng.uniform(-100,100),0],np.float32)
        if self.scenario=='aerial':state.ball.position[2]=self.rng.uniform(350,800)
        state.ball.angular_velocity=np.zeros(3,np.float32)
        team_positions={0:0,1:0}
        for aid,car in state.cars.items():
            ours=car.is_orange==self.orange
            offset=(-sign*1000 if ours else sign*1000)
            lane=(team_positions[car.team_num]-(self.team_size-1)/2)*700;team_positions[car.team_num]+=1
            position=np.array([np.clip(x+lane+self.rng.uniform(-350,350),-3500,3500),np.clip(y+offset,-4400,4400),17.1],np.float32)
            car.physics.position=position
            direction=state.ball.position-position;car.physics.rotation_mtx=basis(math.atan2(direction[1],direction[0]))
            car.boost_amount=float(self.rng.uniform(25,75))
            if ours and self.scenario=='recover':
                car.physics.position[2]=float(self.rng.uniform(100,300));car.on_ground=False
                car.physics.rotation_mtx=basis(float(self.rng.uniform(-math.pi,math.pi)),float(self.rng.choice([math.pi/2,math.pi,-math.pi/2])))

    def observe(self):
        views=self.observer.observe(self.state,self.previous)
        return {aid:(q,kv,np.where(mask>0,-10000.,mask).astype(np.float32)) for aid,(q,kv,mask) in views.items()}

    def chaser(self,aid):
        car=self.state.cars[aid];delta=self.state.ball.position-car.physics.position
        yaw=math.atan2(car.physics.forward[1],car.physics.forward[0]);target=math.atan2(delta[1],delta[0])
        error=math.atan2(math.sin(target-yaw),math.cos(target-yaw));action=np.zeros(8,np.float32)
        action[0]=1;action[1]=np.clip(error*3,-1,1);action[6]=abs(error)<.3 and np.linalg.norm(delta)>400
        action[5]=car.on_ground and np.linalg.norm(delta)<230 and self.state.ball.position[2]>140
        action[2]=-1 if action[5] else 0
        return np.tile(action,(TICKS,1))

    def step(self,commands):
        if set(commands)!=set(self.state.cars):raise ValueError('All cars require controls')
        if any(np.asarray(c).shape!=(TICKS,8) or not np.isfinite(c).all() or np.abs(c).max()>1.001 or not np.isin(np.asarray(c)[:,5:],[0,1]).all() for c in commands.values()):
            raise ValueError('Invalid physical controls')
        observations=self.observe();self.pending.append([observations[aid] for aid in self.ours])
        before=self.state;self.state=self.engine.step(commands,{})
        self.previous={aid:np.asarray(c[-1],np.float32).copy() for aid,c in commands.items()};self.decisions+=1
        touches={car.team_num for car in self.state.cars.values() if car.ball_touches}
        if len(touches)==1:self.last_touch=next(iter(touches))
        terminated=bool(self.state.goal_scored);truncated=not terminated and self.decisions>=self.limit
        scored=bool((float(self.state.ball.position[1])>0)!=self.orange) if terminated else None
        r=reward(before,self.state,self.orange,terminated);final=self.observe()
        own_goal=terminated and not scored and self.last_touch==int(self.orange)
        if terminated:
            history=list(self.pending)
            for i,views in enumerate(history):
                label=(1. if scored else -1.)*GAMMA**(len(history)-i)
                for view in views:self.goal_examples.append((tuple(v.astype(np.float16) for v in view),label))
        # Capture final-state views before reset for time-limit bootstrapping.
        final_ours=[final[aid] for aid in self.ours]
        info={'goal':scored,'own_goal':bool(own_goal),'scenario':self.scenario,'orange':self.orange,
            'airborne_touches':sum(c.ball_touches>0 and not c.on_ground for aid,c in self.state.cars.items() if aid in self.ours)}
        if terminated or truncated:self.reset()
        return r,terminated,truncated,final_ours,info

    def close(self):self.engine.close()
