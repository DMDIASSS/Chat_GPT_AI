from __future__ import annotations

import numpy as np
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
from .core import TICK_SKIP

SCENARIOS = ('kickoff','shot','defense','dribble','aerial','recovery','wall')


def set_pose(car, position, yaw, velocity=(0,0,0), pitch=0., roll=0., boost=60.):
    # Team rotation mutates these arrays. Never alias KickoffMutator's shared
    # float32 spawn templates (np.asarray alone returns a view of them).
    car.physics.position = np.array(position, dtype=np.float32, copy=True)
    car.physics.linear_velocity = np.array(velocity, dtype=np.float32, copy=True)
    car.physics.angular_velocity = np.zeros(3, dtype=np.float32)
    car.physics.euler_angles = np.asarray([pitch,yaw,roll], dtype=np.float32)
    car.on_ground = position[2] < 30 and abs(roll) < .1 and abs(pitch) < .1
    car.boost_amount = float(boost)


def make_state(engine, rng, scenario, learner_team=0, difficulty=.25, bank=None):
    if scenario == 'replay':
        from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state
        if bank is None or len(bank) == 0:
            raise ValueError('Replay scenario requires a nonempty reset bank')
        state = deserialize_game_state(bank[int(rng.integers(len(bank)))].copy())
        state.tick_count = 0
        state.goal_scored = False
        return state
    state = engine.create_base_state()
    FixedTeamSizeMutator(blue_size=1, orange_size=1).apply(state,{})
    own = state.cars['blue-0']
    opponent = state.cars['orange-0']
    state.ball.linear_velocity = np.zeros(3, dtype=np.float32)
    state.ball.angular_velocity = np.zeros(3, dtype=np.float32)
    state.ball.rotation_mtx = np.eye(3, dtype=np.float32)
    x = float(rng.uniform(-900,900))
    d = float(np.clip(difficulty,0,1))
    set_pose(opponent, [rng.uniform(-1200,1200),3500,17], -np.pi/2, boost=45)
    if scenario == 'kickoff':
        i = int(rng.integers(5))
        set_pose(own, KickoffMutator.SPAWN_BLUE_POS[i], KickoffMutator.SPAWN_BLUE_YAW[i],boost=33.3)
        set_pose(opponent, KickoffMutator.SPAWN_ORANGE_POS[i], KickoffMutator.SPAWN_ORANGE_YAW[i],boost=33.3)
        state.ball.position = np.array([0,0,93.15], dtype=np.float32)
    elif scenario == 'shot':
        y = 3000-2300*d
        state.ball.position = np.array([x,y,93.15], dtype=np.float32)
        set_pose(own, [x+rng.uniform(-200,200)*(1+d),y-650,17],np.pi/2,(0,300,0))
        set_pose(opponent, [rng.choice([-1,1])*(2000-1100*d),4300,17],-np.pi/2)
    elif scenario == 'defense':
        state.ball.position = np.array([x,-1200,200+300*d],dtype=np.float32)
        state.ball.linear_velocity = np.array([-x*.15,-800-900*d,100],dtype=np.float32)
        set_pose(own, [rng.uniform(-700,700),-3800,17],np.pi/2,boost=70)
        set_pose(opponent,[x,800,17],-np.pi/2,(0,-700,0))
    elif scenario == 'dribble':
        set_pose(own,[x,-1500,17],np.pi/2,(0,450,0),boost=50)
        state.ball.position = np.array([x,-1480,150],dtype=np.float32)
        state.ball.linear_velocity = np.array([80*d,450,0],dtype=np.float32)
    elif scenario == 'aerial':
        state.ball.position = np.array([x,300,350+700*d],dtype=np.float32)
        state.ball.linear_velocity = np.array([150*d,200,150],dtype=np.float32)
        set_pose(own,[x,-450,17+150*d],np.pi/2,(0,450,150*d),pitch=.2*d,boost=100)
    elif scenario == 'recovery':
        state.ball.position = np.array([x,1600,93.15],dtype=np.float32)
        set_pose(own,[x,-1400,180+800*d],rng.uniform(-np.pi,np.pi),
                 (rng.uniform(-500,500),rng.uniform(-500,500),0),
                 pitch=rng.uniform(-1,1),roll=rng.uniform(-np.pi,np.pi),boost=55)
    elif scenario == 'wall':
        side = int(rng.choice([-1,1]))
        state.ball.position = np.array([side*3900,0,250+550*d],dtype=np.float32)
        state.ball.linear_velocity = np.array([0,300,100],dtype=np.float32)
        set_pose(own,[side*4070,-650,200+300*d],np.pi/2,(0,450,0),roll=-side*np.pi/2,boost=90)
    else:
        raise ValueError(f'Unknown scenario {scenario}')
    # Team rotation, not reflection: local steer/yaw/roll controls retain signs.
    if learner_team == 1:
        sign = np.array([-1,-1,1],dtype=np.float32)
        for car in state.cars.values():
            car.team_num = 1-car.team_num
            car.physics.position *= sign
            car.physics.linear_velocity *= sign
            car.physics.angular_velocity *= sign
            car.physics.rotation_mtx = sign[:,None]*car.physics.rotation_mtx
        state.ball.position *= sign
        state.ball.linear_velocity *= sign
        state.ball.angular_velocity *= sign
    return state


class Curriculum:
    """Small per-worker curriculum; retain all configured practice types."""
    def __init__(self, weights, adaptive=True):
        self.weights = dict(weights)
        self.adaptive = adaptive
        self.stats = {k:dict(episodes=0,ewma=.5) for k in weights}

    def choose(self,rng):
        names=list(self.weights)
        weights=np.array([self.weights[k]*(.35+1-self.stats[k]['ewma']
                    if self.adaptive and self.stats[k]['episodes']>=10 else 1) for k in names])
        return str(rng.choice(names,p=weights/weights.sum()))

    def difficulty(self,scenario):
        st=self.stats[scenario]
        return .15 if st['episodes']<10 else float(np.clip(st['ewma'],.15,.9))

    def record(self,scenario,success):
        st=self.stats[scenario]
        st['episodes']+=1
        st['ewma']=.95*st['ewma']+.05*float(success)


def practice_success(scenario, state, agent, touches, high_touch, wall_touch, dribble_seconds, outcome):
    car=state.cars[agent]
    if scenario=='defense':
        return outcome>=0 and touches>0
    if scenario=='aerial':
        return high_touch
    if scenario=='wall':
        return wall_touch
    if scenario=='recovery':
        return car.on_ground and car.physics.up[2]>.85 and np.linalg.norm(car.physics.linear_velocity)>500
    if scenario=='dribble':
        return dribble_seconds>=.5
    return outcome==1
