"""Mixed match, mechanics, replay and 2v2 practice using the native actor."""
from __future__ import annotations
import random
import numpy as np
import torch
from torch import nn
from slater_mechanics_env import MechanicsEnv,MechanicsCritic,configure_mechanic
from slater_mechanics_core import MechanicTracker,DT
from slater_versatile_data import native_observation
from slater_nexto_scheduler_v038b import NextoV4Clock
from mechanics_scenarios import configure,set_car,set_ball
import slater_cycle9_native_ppo_v025 as base

TASKS=('match','ground','defense','recovery','low_boost','aerial','wall',
       'air_dribble','air_finish','reset_use','replay','teamplay')

class VersatileCritic(MechanicsCritic):
    def __init__(self):
        super().__init__();self.heads=nn.Linear(192,len(TASKS))
    def value_for_task(self,x,tasks):
        q,kv,mask=x;valid=(mask==0).unsqueeze(-1).to(kv.dtype)
        pooled=(kv*valid).sum(1)/valid.sum(1).clamp_min(1)
        ball_idx=kv[:,:,3].argmax(1);ball=kv[torch.arange(len(q)),ball_idx]
        values=self.heads(self.body(torch.cat((q[:,0],pooled,ball),-1)))
        return values.gather(1,tasks.reshape(-1,1)).squeeze(1)

class VersatileEnv(MechanicsEnv):
    def __init__(self,rivals,*,task_name='ground',dataset=None,max_seconds=12,fixed_side=None,fixed_rival=None,scripted_student=False,anchor_weight=.03):
        super().__init__(rivals,retention=True,max_seconds=max_seconds,fixed_side=fixed_side,fixed_rival=fixed_rival,anchor_weight=anchor_weight)
        if task_name not in TASKS:raise ValueError('Unknown versatile task')
        self.task_name=task_name;self.dataset=dataset;self.scripted_student=scripted_student
        self.team_size=2 if task_name=='teamplay' else 1
    def observe(self):return native_observation(super().observe())
    @property
    def task(self):return TASKS.index(self.task_name)
    def reset(self,seed):
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
        self.episode_count+=1;rng=np.random.default_rng(seed)
        side=self.fixed_side or ('blue' if self.episode_count%2 else 'orange')
        self.ours='blue-0' if side=='blue' else 'orange-0';self.opponent='orange-0' if side=='blue' else 'blue-0'
        self.rival_name=self.fixed_rival or tuple(self.rivals)[(self.episode_count-1+seed)%len(self.rivals)]
        self.rival=self.rivals[self.rival_name]
        state=self.engine.create_base_state();FixedTeamSizeMutator(blue_size=self.team_size,orange_size=self.team_size).apply(state,{})
        random.seed(int(seed));self.kickoff.apply(state,{})
        sign=-1 if side=='orange' else 1
        task=self.task_name;us=state.cars[self.ours]
        if task=='replay':
            if self.dataset is None:raise ValueError('Replay task requires a prepared dataset')
            state=self.dataset.reset_state(rng)
        elif task in ('ground','low_boost','teamplay'):
            bp=np.array([rng.uniform(-2300,2300),rng.uniform(-2800,2800),93.])
            set_ball(state.ball,bp,[rng.uniform(-400,400),rng.uniform(-600,600),rng.uniform(0,150)])
            for i,car in enumerate(state.cars.values()):
                cp=[rng.uniform(-3300,3300),rng.uniform(-4300,4300),17.]
                set_car(car,cp,[bp[0],bp[1],17],speed=rng.uniform(0,1200),boost=rng.uniform(0,25) if task=='low_boost' else rng.uniform(20,100),on_ground=True)
        elif task=='defense':
            bp=[rng.uniform(-700,700),-sign*rng.uniform(2100,3300),rng.uniform(93,550)]
            set_ball(state.ball,bp,[rng.uniform(-180,180),-sign*rng.uniform(650,1300),rng.uniform(-80,100)])
            set_car(us,[rng.uniform(-900,900),-sign*4300,17],[bp[0],bp[1],17],boost=rng.uniform(15,70),on_ground=True)
            set_car(state.cars[self.opponent],[rng.uniform(-600,600),-sign*1200,17],[bp[0],bp[1],17],boost=50,on_ground=True)
        elif task in ('recovery','aerial'):
            configure(state,'recovery' if task=='recovery' else 'aerial_touch',self.ours,self.opponent,rng)
        elif task=='wall':
            x=float(rng.choice([-1,1]))*3700;y=rng.uniform(-2300,2300)
            set_ball(state.ball,[x,y,600],[rng.uniform(-100,100),sign*650,120])
            set_car(us,[x*.97,y-sign*380,400],[x,y,600],boost=80,up=[-np.sign(x),0,.2])
        elif task in ('air_dribble','air_finish','reset_use'):
            configure_mechanic(state,task,self.ours,self.opponent,seed,float(rng.uniform(.15,.85)))
        self.state=self.engine.set_state(state,{})
        self.previous={};self.tick_count=0;self.reward_sum=0.;self.ball_touched=False
        self.clocks={aid:NextoV4Clock(hardcoded=True,stochastic=False) for aid in self.state.cars if aid!=self.ours}
        self.student_clock=NextoV4Clock(hardcoded=True,stochastic=False) if self.scripted_student else None
        self.tracker=MechanicTracker(task,self.state,self.ours,self.opponent) if task in ('air_dribble','air_finish','reset_use') else None
        self.touch_payments=0;self.last_touch=-100.;self.recovered=False;self.saved=False;self.aerial_hit=False
        self.potential=self.phi(self.state);return self.observe()
    def phi(self,state):
        sign=-1 if state.cars[self.ours].is_orange else 1
        ball=state.ball.position;cp=state.cars[self.ours].physics.position
        # Bounded potential differences; movement/touch farming is not the goal.
        return .4*sign*float(ball[1])/5120-.12*min(float(np.linalg.norm(ball-cp))/5000,1)
    def step(self,action):
        learner=self.actions[int(action)];reward=0.;done=False;timeout=False;goal=False
        for _ in range(8):
            state=self.state;ids=sorted(state.cars);positions=np.asarray([state.cars[k].physics.position[:2] for k in ids]);teams=np.asarray([state.cars[k].team_num for k in ids])
            kickoff=(not self.ball_touched and self.tick_count<168 and np.linalg.norm(state.ball.position[:2])<1 and state.ball.position[2]<100)
            ready=[aid for aid,clock in self.clocks.items() if clock.update_action]
            predicted={}
            if ready:
                previous=dict(self.previous)
                for aid in ready:previous[aid]=self.clocks[aid].action
                views={aid:native_observation(obs) for aid,obs in self.observer.observe(state,previous).items()}
                x=tuple(torch.from_numpy(np.stack([views[k][i] for k in ready])) for i in range(3))
                with torch.no_grad():indices=base.logits_of(self.rival,x).argmax(-1).tolist()
                predicted={aid:int(index) for aid,index in zip(ready,indices)}
            commands={self.ours:learner[None]}
            if self.student_clock:
                frame=self.student_clock.frame(is_kickoff_pause=kickoff,ball_xy=state.ball.position[:2],
                    positions=positions,teams=teams,index=ids.index(self.ours),infer=lambda previous,beta:(int(action),learner))
                commands[self.ours]=frame.controls[None]
            for aid,clock in self.clocks.items():
                def infer(previous,beta,aid=aid):
                    index=predicted[aid];return index,self.actions[index]
                frame=clock.frame(is_kickoff_pause=kickoff,ball_xy=state.ball.position[:2],positions=positions,teams=teams,index=ids.index(aid),infer=infer)
                self.total_script_ticks+=int(frame.script_applied);commands[aid]=frame.controls[None]
            self.state=self.engine.step(commands,{})
            self.tick_count+=1;self.total_ticks+=1
            self.previous={aid:a[0].copy() for aid,a in commands.items()}
            self.ball_touched|=any(c.ball_touches>0 for c in self.state.cars.values())
            goal=bool(self.state.goal_scored);done=goal
            sign=-1 if self.state.cars[self.ours].is_orange else 1
            potential=0. if goal else self.phi(self.state)
            reward+=(.995**(1/8))*potential-self.potential-.02*DT
            self.potential=potential
            car=self.state.cars[self.ours]
            if car.ball_touches and self.tick_count-self.last_touch>30 and self.touch_payments<6:
                # Reward useful goalward contact, capped per episode.
                if sign*self.state.ball.linear_velocity[1]>100:reward+=.05;self.touch_payments+=1
                self.last_touch=self.tick_count
                if car.physics.position[2]>250:self.aerial_hit=True
                if self.task_name=='defense' and sign*self.state.ball.linear_velocity[1]>100:self.saved=True
            if self.task_name=='recovery' and not self.recovered and car.on_ground and car.physics.rotation_mtx[2,2]>.8:
                self.recovered=True;reward+=.5*min(np.linalg.norm(car.physics.linear_velocity)/1000,1)
            if self.tracker is not None and not goal:
                mechanic_reward,_=self.tracker.tick(state,self.state,learner);reward+=mechanic_reward
            if goal:reward+=10 if sign*self.state.ball.position[1]>0 else -10
            timeout=not done and self.tick_count>=round(self.max_seconds*120);done|=timeout
            if done:break
        self.reward_sum+=reward
        info={'outcome':int(sign*np.sign(self.state.ball.position[1])) if goal else 0,'timeout':timeout,
              'success':bool(self.saved if self.task_name=='defense' else self.recovered if self.task_name=='recovery' else self.aerial_hit if self.task_name=='aerial' else self.tracker.events.success if self.tracker else False),
              'task_name':self.task_name,'steps':self.tick_count/8,'physics_ticks':self.tick_count,
              'student_script_physics_ticks':self.student_clock.script_physics_ticks if self.student_clock else 0,
              'opponent':self.rival_name,'script_physics_ticks':sum(c.script_physics_ticks for c in self.clocks.values()),
              'side':'orange' if sign<0 else 'blue','reward':self.reward_sum}
        if not np.isfinite(reward):raise FloatingPointError('Nonfinite versatile reward')
        return self.observe(),float(reward),bool(done),info
