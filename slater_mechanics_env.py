"""Native Nexto environments with tick-level rewards and scripted frozen rivals."""
from __future__ import annotations

import random

import numpy as np
import torch
from torch import nn

from afk_team_research import TeamObserver
from mechanics_scenarios import set_car,basis
from nexto_teacher import nexto_actions
from slater_nexto_scheduler_v038b import NextoV4Clock
from slater_mechanics_core import MechanicTracker,DT,STAGES
import slater_cycle9_native_ppo_v025 as base


class MechanicsCritic(nn.Module):
    """Task-specific value heads; actor observations remain native Nexto."""
    def __init__(self):
        super().__init__()
        self.body=nn.Sequential(nn.Linear(80,192),nn.Tanh(),nn.Linear(192,192),nn.Tanh())
        self.heads=nn.Linear(192,len(STAGES)+1)

    def value_for_task(self,x,tasks):
        q,kv,mask=x;valid=(1-mask).unsqueeze(-1).clamp(0,1)
        pooled=(kv*valid).sum(1)/valid.sum(1).clamp_min(1)
        ball_idx=kv[:,:,3].argmax(1)
        ball=kv[torch.arange(len(q)),ball_idx]
        values=self.heads(self.body(torch.cat((q[:,0],pooled,ball),-1)))
        return values.gather(1,tasks.reshape(-1,1)).squeeze(1)


def configure_mechanic(state,stage,ours,opponent,seed,difficulty):
    """Backward curriculum: easier ready-to-control starts, wider starts later."""
    if stage not in STAGES or not 0<=difficulty<=1:raise ValueError('Invalid scenario')
    rng=np.random.default_rng(seed);sign=-1. if state.cars[ours].is_orange else 1.
    x=sign*rng.uniform(-150-800*difficulty,150+800*difficulty)
    y=sign*rng.uniform(200,1400)
    z=rng.uniform(530,740+400*difficulty)
    bp=np.array([x,y,z])
    if stage in ('air_finish','air_bump_finish','reset_finish'):
        bp[1]=sign*rng.uniform(1500,2200)
    velocity=np.array([sign*rng.uniform(-80,80)*difficulty,sign*rng.uniform(450,700),rng.uniform(60,140)])
    us=state.cars[ours];enemy=state.cars[opponent]
    if stage.startswith('reset') and stage!='reset_finish':
        # No flip initially. Wheels face the ball; harder cases require real
        # rotation/alignment instead of spawning already in contact.
        gap=rng.uniform(125+110*difficulty,150+200*difficulty)
        cp=bp+np.array([sign*rng.uniform(-12,12)*(1+7*difficulty),
                       -sign*rng.uniform(0,50+120*difficulty),-gap])
        toward=cp+np.array([0,sign*100,0])
        set_car(us,cp,toward,up=[difficulty*rng.uniform(-.8,.8),0,-1],
                boost=rng.uniform(65,100),spent_flip=True)
        us.physics.linear_velocity=velocity+np.array([0,0,160-120*difficulty])
        us.flip_time=1.5;us.air_time_since_jump=2.
    else:
        forward=np.array([sign*rng.uniform(-.10,.10)*(1+3*difficulty),sign*.78,.63])
        rotation=basis(forward)
        separation=rng.uniform(178,190+140*difficulty)
        cp=bp-rotation[:,0]*separation-rotation[:,2]*rng.uniform(5,20)
        cp[0]+=sign*rng.uniform(-15,15)*(1+4*difficulty)
        set_car(us,cp,cp+forward*100,boost=rng.uniform(70,100))
        us.physics.rotation_mtx=rotation
        us.physics.linear_velocity=velocity+np.array([sign*rng.uniform(-100,100)*difficulty,0,-20])
        us.has_jumped=True;us.has_double_jumped=True;us.has_flipped=False
        us.air_time_since_jump=2.;us.flip_time=1.5
    if stage=='air_entry':
        bp[2]=110.;velocity[2]=0.;velocity[1]*=.5
        cp=bp+np.array([sign*rng.uniform(-30,30)*(1+difficulty),-sign*rng.uniform(230,400+200*difficulty),17.-bp[2]])
        set_car(us,cp,[bp[0],bp[1],17.],on_ground=True,boost=rng.uniform(65,100))
        us.physics.linear_velocity=np.array([0,sign*rng.uniform(350,650),0.])
    state.ball.position=bp;state.ball.linear_velocity=velocity
    state.ball.angular_velocity=np.zeros(3)
    if stage in ('air_bump_finish','reset_finish','air_finish'):
        # The defender stays in the scoring lane and is always policy-controlled.
        ep=np.array([x+sign*rng.uniform(-500,500),sign*rng.uniform(3500,4450),17.])
    else:
        ep=np.array([sign*3000.,-sign*3300.,17.])
    set_car(enemy,ep,[bp[0],bp[1],17],boost=rng.uniform(25,70),on_ground=True)
    state.goal_scored=False


class MechanicsEnv:
    def __init__(self,rivals,*,stage='air_dribble',difficulty=0.,retention=False,
                 max_seconds=6.,fixed_side=None,fixed_rival=None,action_repeat=8,
                 rehearsal_stages=(),anchor_weight=.02):
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
        if action_repeat!=8:raise ValueError('Native exported actor uses 8 ticks; changing timing requires a separate parity test')
        self.engine=RocketSimEngine(rlbot_delay=True)
        self.teams=FixedTeamSizeMutator(blue_size=1,orange_size=1);self.kickoff=KickoffMutator()
        self.observer=TeamObserver();self.actions=nexto_actions();self.rivals=rivals
        if not rivals:raise ValueError('At least one frozen rival is required')
        self.stage=stage;self.difficulty=difficulty;self.retention=retention
        self.rehearsal_stages=rehearsal_stages;self.anchor_weight=anchor_weight
        self.max_seconds=max_seconds;self.fixed_side=fixed_side;self.fixed_rival=fixed_rival
        self.episode_count=0;self.total_ticks=0;self.total_script_ticks=0

    def reset(self,seed):
        self.episode_count+=1
        side=self.fixed_side or ('blue' if (self.episode_count-1)%2==0 else 'orange')
        self.ours='blue-0' if side=='blue' else 'orange-0'
        self.opponent='orange-0' if side=='blue' else 'blue-0'
        self.rival_name=self.fixed_rival or tuple(self.rivals)[((self.episode_count-1)//2+seed)%len(self.rivals)]
        self.rival=self.rivals[self.rival_name]
        if self.rehearsal_stages:self.stage=random.Random(int(seed)^0xABC).choice(self.rehearsal_stages)
        state=self.engine.create_base_state();self.teams.apply(state,{})
        random.seed(int(seed));self.kickoff.apply(state,{})
        if not self.retention:
            configure_mechanic(state,self.stage,self.ours,self.opponent,seed,self.difficulty)
        self.state=self.engine.set_state(state,{})
        self.previous={};self.tick_count=0;self.reward_sum=0.;self.ball_touched=False
        self.clock=NextoV4Clock(hardcoded=True,stochastic=False)
        self.tracker=None if self.retention else MechanicTracker(self.stage,self.state,self.ours,self.opponent)
        self.last_distance=float(np.linalg.norm(self.state.ball.position-self.state.cars[self.ours].physics.position))
        return self.observe()

    @property
    def task(self):return len(STAGES) if self.retention else STAGES.index(self.stage)

    def observe(self):return base.read_obs(self.state,self.previous,self.observer,self.ours)

    def opponent_frame(self):
        ids=sorted(self.state.cars)
        positions=np.array([self.state.cars[k].physics.position[:2] for k in ids])
        teams=np.array([self.state.cars[k].team_num for k in ids])
        def infer(previous,beta):
            prev=dict(self.previous);prev[self.opponent]=previous
            obs=base.read_obs(self.state,prev,self.observer,self.opponent)
            with torch.no_grad():
                index=int(base.logits_of(self.rival,base.to_tensors(obs)).argmax(-1).item())
            return index,self.actions[index]
        # RocketSim has no authoritative RLBot kickoff-pause packet. This is an
        # explicit standard-kickoff proxy; airborne center balls cannot enable it.
        kickoff=(self.retention and not self.ball_touched and self.tick_count<168
                 and np.linalg.norm(self.state.ball.position[:2])<1
                 and self.state.ball.position[2]<100)
        return self.clock.frame(is_kickoff_pause=kickoff,ball_xy=self.state.ball.position[:2],
            positions=positions,teams=teams,index=ids.index(self.opponent),infer=infer)

    def step(self,action):
        learner=np.asarray(self.actions[int(action)],dtype=np.float32)
        reward=0.;done=False;goal=False
        sign=-1. if self.state.cars[self.ours].is_orange else 1.
        for _ in range(8):
            frame=self.opponent_frame()
            self.total_script_ticks+=int(frame.script_applied)
            before=self.state
            self.state=self.engine.step({self.ours:learner[None],self.opponent:frame.controls[None]}, {})
            self.tick_count+=1;self.total_ticks+=1
            self.previous={self.ours:learner.copy(),self.opponent:frame.controls.copy()}
            self.ball_touched |= any(c.ball_touches>0 for c in self.state.cars.values())
            goal=bool(self.state.goal_scored)
            if self.retention:
                reward-=.02*DT
                if goal:reward+=10. if sign*float(self.state.ball.position[1])>0 else -10.
                done=goal
            else:
                r,done=self.tracker.tick(before,self.state,learner);reward+=r
                # Failed carry setup is terminal, rather than granting bonuses
                # for chasing a now-grounded ball through the same drill.
                minimum_ticks=120 if self.stage=='air_entry' else 24
                if self.tick_count>minimum_ticks and self.state.ball.position[2]<150 and not done:
                    done=True;reward-=1.
            timeout=not done and self.tick_count>=round(self.max_seconds*120)
            done |= timeout
            if done:break
        self.reward_sum+=reward
        info={'outcome':int(sign*np.sign(self.state.ball.position[1])) if goal else 0,
              'stage':self.stage,
              'timeout':bool(timeout),'steps':self.tick_count/8,'physics_ticks':self.tick_count,
              'opponent':self.rival_name,'side':'orange' if sign<0 else 'blue',
              'script_physics_ticks':self.clock.script_physics_ticks,'reward':self.reward_sum}
        if self.tracker is not None:info.update(self.tracker.summary())
        else:info['success']=False
        if not np.isfinite(reward):raise FloatingPointError('Nonfinite environment reward')
        return self.observe(),float(reward),bool(done),info

    def close(self):self.engine.close()


def collect_batched(actor,critic,envs,observations,seeds,steps_per_env):
    """Batch learner inference; compute GAE separately for each environment."""
    from torch.distributions import Categorical
    from slater_v040_multirival import adjusted_timeout_reward
    keys=('q','kv','mask','action','old_logp','value','reward','done','task','anchor_weight')
    buffers=[{k:[] for k in keys} for _ in envs];finished=[];truncations=0
    for _ in range(steps_per_env):
        x=tuple(torch.as_tensor(np.stack([o[k] for o in observations]),dtype=torch.float32) for k in range(3))
        with torch.no_grad():
            dist=Categorical(logits=base.logits_of(actor,x));actions=dist.sample()
            logps=dist.log_prob(actions)
            values=critic.value_for_task(x,torch.tensor([e.task for e in envs],dtype=torch.long))
        for j,env in enumerate(envs):
            obs=observations[j]
            task=env.task
            after,reward,done,info=env.step(int(actions[j]))
            nxt=0.
            if info['timeout']:
                with torch.no_grad():nxt=float(critic.value_for_task(base.to_tensors(after),torch.tensor([task])).item())
                truncations+=1
            reward=adjusted_timeout_reward(reward,done,info['timeout'],nxt)
            for key,value in zip(keys,(*obs,int(actions[j]),float(logps[j]),float(values[j]),reward,done,task,env.anchor_weight)):
                buffers[j][key].append(value)
            if done:
                info['retention']=env.retention;finished.append(info)
                seeds[j]+=1;after=env.reset(seeds[j])
            observations[j]=after
    joined={k:[] for k in (*keys,'adv','ret')}
    for j,rows in enumerate(buffers):
        with torch.no_grad():bootstrap=float(critic.value_for_task(base.to_tensors(observations[j]),torch.tensor([envs[j].task])).item())
        rows['adv'],rows['ret']=base.gae(rows['reward'],rows['value'],rows['done'],bootstrap)
        for key,value in rows.items():joined[key].extend(value)
    for key in ('adv','ret'):joined[key]=np.asarray(joined[key],np.float32)
    return joined,finished,observations,seeds,truncations
