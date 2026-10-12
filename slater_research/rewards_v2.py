"""RLGym v2 reward adapter compatible with RLGym GameState/Car.

Full 120-Hz controls for kickoff are supplied as shared_info['controls'][agent]
(last command vector [8]). Every timestep reward weight assumes PHYSICS ticks,
not decision ticks; event bonuses occur once per transition.
"""
from __future__ import annotations
import math
import numpy as np
from rlgym.api import RewardFunction
from slater_research.geometry import (
    BALL_RADIUS, SUPERSONIC_SPEED, collision_ttc, ball_goal_threat,
    double_commit_pair, flip_reset_event, shadow_defense_quality, norm, unit, clamp)


class SlaterCurriculumReward(RewardFunction):
    def __init__(self, *, physics_tick_rate=120):
        self.physics_tick_rate=physics_tick_rate
        self.last={}
        self.kickoff_start=0
        self.kickoff_active=True
        self.previous_controls={}
        self.flip_start={}
        self.cancel_awarded=set()
        self.last_pair_commits=set()
        self.last_contacts={}
        self.last_demos={}
        self.last_at_risk={}

    def reset(self, agents, initial_state, shared_info):
        import copy
        self.last = copy.deepcopy(initial_state.cars)
        self.kickoff_start=initial_state.tick_count
        self.kickoff_active=True
        self.previous_controls={}
        self.flip_start={}
        self.cancel_awarded=set()
        self.last_pair_commits=set()
        self.last_contacts={}
        self.last_demos={a: bool(c.is_demoed) for a,c in initial_state.cars.items()}
        self.last_at_risk={}

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        """Call once per *physics* tick for speedflip timing, or scale continuous terms by elapsed dt."""
        cars=state.cars
        rewards={a:0.0 for a in agents}
        controls=shared_info.get('controls', {})  # optional; action vectors at this physics tick
        age=(state.tick_count-self.kickoff_start)/self.physics_tick_rate
        on_kickoff=self.kickoff_active and age < 2.1
        if any(c.ball_touches for c in cars.values()): self.kickoff_active=False

        for aid in agents:
            c=cars[aid]
            if c.is_demoed:continue
            p=np.asarray(c.physics.position,float)
            v=np.asarray(c.physics.linear_velocity,float)
            ball=np.asarray(state.ball.position,float)
            speed=norm(v)
            enemy=[(bid,o) for bid,o in cars.items() if o.is_orange != c.is_orange and not o.is_demoed]
            mates=[(bid,o) for bid,o in cars.items() if bid!=aid and o.is_orange==c.is_orange and not o.is_demoed]
            own_threat=ball_goal_threat(ball,state.ball.linear_velocity,c.is_orange)

            # Per-physics-step progress signal; 0.002 maximum -> ~0.24 per simulated second
            if not on_kickoff and speed > 1400:
                rewards[aid] += 0.002*clamp((speed-1400)/800)
            # Recovery velocity aligned with own car forward, discourages uncontrolled sideways boosting
            forward=np.asarray(c.physics.rotation_mtx,float)[:,0]
            if not c.on_ground and p[2]<350 and speed>700:
                rewards[aid] += 0.0015*clamp(float(np.dot(unit(v), unit(forward))))

            if on_kickoff:
                # This is a *soft* penalty: never clamp simulated physical position.
                rewards[aid] -= 0.010*(max(0., p[2]-130.)/100.)**2
                if c.on_ground and speed >= SUPERSONIC_SPEED:
                    rewards[aid] += 0.003
                cmd=np.asarray(controls.get(aid, np.zeros(8)),float)
                old=np.asarray(self.previous_controls.get(aid,np.zeros(8)),float)
                # A dodge command begins with rising jump edge while airborne.
                if cmd[5]>.5 and old[5]<=.5 and not c.on_ground and c.has_flipped:
                    self.flip_start[aid]=(state.tick_count, float(cmd[2]))
                if aid in self.flip_start and aid not in self.cancel_awarded:
                    tick,pitch=self.flip_start[aid]
                    dt=(state.tick_count-tick)/self.physics_tick_rate
                    if dt<=.065 and abs(pitch)>.5 and pitch*cmd[2]<-.45:
                        rewards[aid] += 0.40
                        self.cancel_awarded.add(aid)
                    if dt>.065: self.cancel_awarded.add(aid)
                if c.ball_touches:
                    rewards[aid] += 1.0  # contact first is tested by episode outcome, not only touch count

            # Predict moving demo trajectories analytically, only for high-speed attackers.
            at_risk=False
            for bid,o in enemy:
                ov=np.asarray(o.physics.linear_velocity,float)
                ttc=collision_ttc(p,v,o.physics.position,ov,170,.6)
                if norm(ov)>SUPERSONIC_SPEED and math.isfinite(ttc) and ttc<=.55:
                    at_risk=True
                    danger=clamp((.55-ttc)/.55)
                    # Penalty for remaining on collision course, not a blind 'jump constantly' incentive
                    rewards[aid]-=0.015*danger
                # Demo hunting sparse event, do NOT continuously reward harassment
                if o.is_demoed and not self.last_demos.get(bid,False):
                    if norm(p-o.physics.position)<280 and speed>SUPERSONIC_SPEED:
                        rewards[aid] += 2.0
            if self.last_at_risk.get(aid,False) and not at_risk and c.on_ground:
                rewards[aid]+=0.12  # threat clearance; sparse and gated by prior risk
            self.last_at_risk[aid]=at_risk
            prior=self.last.get(aid)
            if prior is not None and flip_reset_event(prior,c,ball): rewards[aid]+=2.0

            # Opponent with saved dodge within ball vicinity = delayed reset threat cone
            delayed=any((not o.on_ground and o.has_flip and
                         norm(o.physics.position-ball)<500) for _,o in enemy)
            threat=ball_goal_threat(ball,state.ball.linear_velocity,c.is_orange,
                                    uncertainty=450 if delayed else 0)
            if threat.danger:
                coverage=shadow_defense_quality(p,ball,c.is_orange)
                rewards[aid]+=0.003*coverage*clamp(1.5/threat.time)
                if delayed and coverage <.20:rewards[aid]-=0.002

            # Possession: low relative speed ball-car + controlled ball height
            rv=norm(np.asarray(state.ball.linear_velocity,float)-v)
            d=norm(ball-p)
            if d<350 and 100<ball[2]<350 and rv<650:
                rewards[aid]+=0.004*(1-d/350)*(1-rv/650)

            # Small boost lane collection; state pad index matching uses official order
            previous_timers=shared_info.get('previous_boost_timers')
            if previous_timers is not None and len(previous_timers)==len(state.boost_pad_timers):
                from rlgym.rocket_league.common_values import BOOST_LOCATIONS
                for i,(old_t,new_t) in enumerate(zip(previous_timers,state.boost_pad_timers)):
                    if old_t<.03 and new_t>1.0 and float(BOOST_LOCATIONS[i][2])<73:
                        if norm(p-np.asarray(BOOST_LOCATIONS[i],float))<190:
                            rewards[aid]+=0.08
            # Penalize *choosing* a far corner detour during goal threat, not collecting pads per se
            if threat.danger and abs(p[0])>3100 and abs(p[1])>3800 and d>1000:
                rewards[aid]-=0.004

            if c.bump_victim_id is not None:
                victim=cars.get(c.bump_victim_id)
                if (victim is not None and victim.is_orange==c.is_orange
                     and self.last_contacts.get(aid)!=c.bump_victim_id):
                    rewards[aid]-=3.5
            self.last_contacts[aid]=c.bump_victim_id
            if state.goal_scored:
                scorer=0 if state.ball.position[1]>0 else 1
                rewards[aid]+=10. if c.team_num==scorer else -10.

        new_pairs=set()
        for i,(a,ca) in enumerate(cars.items()):
            for b,cb in list(cars.items())[i+1:]:
                if ca.is_orange==cb.is_orange and double_commit_pair(ca,cb,state.ball.position):
                    key=frozenset((a,b));new_pairs.add(key)
                    if key not in self.last_pair_commits:
                        if a in rewards:rewards[a]-=4.0
                        if b in rewards:rewards[b]-=4.0
        self.last_pair_commits=new_pairs
        import copy
        self.last=copy.deepcopy(cars)
        self.previous_controls={a: np.asarray(u,float).copy() for a,u in controls.items()}
        self.last_demos={a:bool(c.is_demoed) for a,c in cars.items()}
        return rewards
