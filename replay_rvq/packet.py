"""Standalone canonical features and explicitly estimated RLBot forecast state."""
import math
import numpy as np
try:
    from replay_nexto_obs import NextoObsBuilder,rotation_to_quaternion
    from replay_rlbot_core import vector,rotation
except ModuleNotFoundError:
    from vendor.nexto.nexto_obs import NextoObsBuilder,rotation_to_quaternion
    from replay_rlbot_core import vector,rotation


class StateObserver:
    def __init__(self):self.builder=NextoObsBuilder(n_players=6,tick_skip=8)

    def observe(self,state,previous):
        ids=sorted(state.cars,key=lambda aid:(state.cars[aid].team_num,str(aid)))
        row=np.zeros(55+38*len(ids),np.float64);row[3:37]=state.boost_pad_timers<=1e-6
        row[37:40]=state.ball.position;row[40:43]=state.ball.linear_velocity;row[43:46]=state.ball.angular_velocity
        # The builder consumes only the original ball/car pose and flag fields.
        for position,aid in enumerate(ids):
            car=state.cars[aid];offset=55+38*position;physics=car.physics
            row[offset:offset+2]=position,car.team_num
            row[offset+2:offset+5]=physics.position;row[offset+5:offset+9]=rotation_to_quaternion(physics.rotation_mtx)
            row[offset+9:offset+12]=physics.linear_velocity;row[offset+12:offset+15]=physics.angular_velocity
            row[offset+33:offset+38]=car.is_demoed,car.on_ground,car.ball_touches>0,car.has_flip,car.boost_amount/100.
        obs=self.builder.batched_build_obs(row[None]);result={}
        for i,aid in enumerate(ids):
            self.builder.add_actions(obs,np.asarray(previous.get(aid,np.zeros(8)),np.float64),i)
            q,kv,mask=obs[i];result[aid]=(q[0].astype(np.float32),kv[0].astype(np.float32),mask[0].astype(np.float32))
        return result


class PacketState:
    def __init__(self,observer):self.observer=observer;self.pad_expiry=np.full(34,np.nan)
    def reset(self):self.pad_expiry[:]=np.nan

    def from_packet(self,packet,index,previous,engine):
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
        import RocketSim as rs
        # Also validates packet physics and updates the existing jump estimates.
        self.observer.observe(packet,index,previous)
        state=engine.create_base_state();blue=sum(packet.game_cars[i].team==0 for i in range(packet.num_cars))
        FixedTeamSizeMutator(blue,packet.num_cars-blue).apply(state,{})
        now=float(packet.game_info.seconds_elapsed);state.tick_count=math.floor(now*120+.5)
        ball=packet.game_ball.physics
        state.ball.position=vector(ball.location).astype(np.float32);state.ball.linear_velocity=vector(ball.velocity).astype(np.float32)
        state.ball.angular_velocity=vector(ball.angular_velocity).astype(np.float32);state.ball.rotation_mtx=np.eye(3,dtype=np.float32)
        state.goal_scored=False
        templates={team:[car for car in state.cars.values() if car.team_num==team] for team in (0,1)};cars={}
        hitboxes=np.stack([rs.CarConfig(i).hitbox_size.as_numpy() for i in range(6)])
        for i in range(packet.num_cars):
            source=packet.game_cars[i];car=templates[source.team].pop(0);physics=source.physics
            car.physics.position=vector(physics.location).astype(np.float32);car.physics.linear_velocity=vector(physics.velocity).astype(np.float32)
            car.physics.angular_velocity=vector(physics.angular_velocity).astype(np.float32);car.physics.rotation_mtx=rotation(physics.rotation).astype(np.float32)
            car.on_ground=bool(source.has_wheel_contact);car.boost_amount=float(source.boost)
            car.demo_respawn_timer=1. if source.is_demolished else 0.;car.supersonic_time=.1 if getattr(source,'is_super_sonic',False) else 0.
            start=self.observer.jumps.get(i);elapsed=max(0.,now-start) if start is not None else 0.
            car.has_jumped=bool(source.jumped);car.has_double_jumped=bool(source.double_jumped)
            car.air_time_since_jump=elapsed;car.jump_time=min(.2,elapsed) if source.jumped else 0.
            known=np.asarray(previous if i==index else np.zeros(8),np.float32)
            car.is_holding_jump=bool(known[5]);car.is_jumping=bool(source.jumped) and elapsed<.2 and car.is_holding_jump
            car.handbrake=float(known[7]);car.boost_active_time=.05 if known[6] and car.boost_amount>0 else 0.
            # Only map standard hitboxes; dimensions can include collision margin.
            hitbox=getattr(source,'hitbox',None)
            if hitbox is not None:
                dims=np.array([hitbox.length,hitbox.width,hitbox.height])
                distance=np.minimum(np.linalg.norm(hitboxes-dims,axis=1),np.linalg.norm(hitboxes-2.5-dims,axis=1))
                if not np.isfinite(distance).all() or distance.min()>8:raise ValueError('Unsupported car hitbox for standard Soccar forecasts')
                car.hitbox_type=int(distance.argmin())
            cars[i]=car
        state.cars=cars
        for canonical,actual in enumerate(self.observer.pad_order):
            active=bool(packet.game_boosts[int(actual)].is_active)
            if active:self.pad_expiry[canonical]=np.nan;state.boost_pad_timers[canonical]=0.
            else:
                if np.isnan(self.pad_expiry[canonical]):
                    duration=10. if self.observer.builder._boost_locations[canonical,2]>72 else 4.
                    self.pad_expiry[canonical]=now+duration
                state.boost_pad_timers[canonical]=max(1/120,self.pad_expiry[canonical]-now)
        return state
