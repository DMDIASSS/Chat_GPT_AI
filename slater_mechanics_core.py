"""Tick-level physical events and stage-specific rewards for native Slater."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

STAGES=('air_dribble','air_entry','air_finish','air_bump_finish',
        'reset_acquire','reset_use','reset_finish')
SCORING_STAGES={'air_finish','air_bump_finish','reset_finish'}
DT=1/120


def unit(v):
    v=np.asarray(v,dtype=float)
    return v/max(float(np.linalg.norm(v)),1e-9)


def wilson_lower(successes,total,z=1.96):
    if not 0<=successes<=total or total<1:raise ValueError('Invalid success counts')
    p=successes/total;denom=1+z*z/total
    return (p+z*z/(2*total)-z*math.sqrt(p*(1-p)/total+z*z/(4*total*total)))/denom


def mastery_verdict(records,*,minimum_pairs=12,threshold=.50):
    """Both sides must succeed: one seed is one conservative paired trial."""
    groups={}
    for row in records:
        key=row['seed']
        part=groups.setdefault(key,{})
        cell=(row['rival'],row['side'])
        if cell in part or row['side'] not in ('blue','orange'):
            raise ValueError('Duplicate/invalid mastery side')
        part[cell]=bool(row['success'])
    required={(r['rival'],side) for r in records for side in ('blue','orange')}
    if not groups or any(set(g)!=required for g in groups.values()):
        return False,{'reason':'incomplete_pairs','pairs':len(groups)}
    passed=sum(all(g.values()) for g in groups.values())
    lower=wilson_lower(passed,len(groups))
    ok=len(groups)>=minimum_pairs and lower>=threshold
    return ok,{'reason':'mastery_pass' if ok else 'practice_required',
               'pairs':len(groups),'successful_pairs':passed,
               'paired_success_rate':passed/len(groups),'wilson_lower':lower,
               'threshold':threshold,'note':'Drill mastery, not competitive rank.'}


@dataclass
class MechanicEvents:
    nose_contacts: int=0
    best_carry_seconds: float=0.
    carry_distance: float=0.
    carry_qualified: bool=False
    reset_acquired: bool=False
    reset_used: bool=False
    useful_bump: bool=False
    scored: bool=False
    conceded: bool=False
    success: bool=False


class MechanicTracker:
    def __init__(self,stage,state,ours,opponent):
        if stage not in STAGES:raise ValueError('Unknown mechanic stage')
        self.stage=stage;self.ours=ours;self.opponent=opponent
        self.sign=-1. if state.cars[ours].is_orange else 1.
        self.events=MechanicEvents();self.seconds=0.
        self.last_nose=-100.;self.last_carry=-100.;self.last_bump=-100.
        self.streak=0.;self.streak_start_y=float(state.ball.position[1])
        self.streak_contacts=0;self.last_contact_edge=False
        self.paid_carry_seconds=0.;self.paid_progress=0.
        self.reset_at=None;self.used_at=None;self.last_bump_id=None
        self.used_flip_at=None;self.previous_control=np.zeros(8)
        self.reward_terms={};self.reset_paid=False;self.use_paid=False
        self.launch_paid=False;self.carry_before_reset=False
        self.regained_at=None

    def add(self,terms,name,value):
        terms[name]=terms.get(name,0.)+float(value)
        self.reward_terms[name]=self.reward_terms.get(name,0.)+float(value)

    def tick(self,before,after,control):
        self.seconds+=DT
        c=after.cars[self.ours];old=before.cars[self.ours]
        enemy=before.cars[self.opponent]
        bp=np.asarray(after.ball.position);cp=np.asarray(c.physics.position)
        bv=np.asarray(after.ball.linear_velocity);cv=np.asarray(c.physics.linear_velocity)
        delta=bp-cp;distance=float(np.linalg.norm(delta));local=c.physics.rotation_mtx.T@delta
        airborne=cp[2]>220 and bp[2]>300
        # Body contact on the forward portion of the hitbox, not proximity alone.
        nose=bool(c.ball_touches) and airborne and local[0]>40 and abs(local[1])<105 and -30<local[2]<150
        if nose and (not self.last_contact_edge or self.seconds-self.last_nose>.12):
            self.events.nose_contacts+=1;self.streak_contacts+=1
            self.last_nose=self.seconds
        self.last_contact_edge=nose
        aligned=float(np.dot(c.physics.rotation_mtx[:,0],unit(delta)))>.40
        recent=self.seconds-self.last_nose<.30
        controlled=airborne and distance<235 and float(np.linalg.norm(bv-cv))<550 and aligned and recent
        moving=self.sign*float(bv[1])>80
        if controlled and moving:
            if self.streak==0:
                self.streak_start_y=float(before.ball.position[1]);self.streak_contacts=int(nose)
            self.streak+=DT;self.last_carry=self.seconds
            travel=max(0.,self.sign*(float(bp[1])-self.streak_start_y))
            self.events.best_carry_seconds=max(self.events.best_carry_seconds,self.streak)
            self.events.carry_distance=max(self.events.carry_distance,travel)
            if self.streak>=1.0 and self.streak_contacts>=2 and travel>=250:
                self.events.carry_qualified=True
        else:
            self.streak=0.;self.streak_contacts=0

        terms={};self.add(terms,'time',-.02*DT)
        old_dist=float(np.linalg.norm(before.ball.position-old.physics.position))
        self.add(terms,'approach',.15*np.clip(old_dist-distance,-15,15)/1000)
        boost=max(0.,float(old.boost_amount-c.boost_amount))
        self.add(terms,'boost_cost',-.002*boost)
        if not self.stage.startswith('reset') or self.stage=='reset_finish':
            if nose and self.seconds-self.last_nose<DT/2 and self.events.nose_contacts<=6:
                self.add(terms,'nose_contact',.10)
            if controlled and moving and self.paid_carry_seconds<2.5:
                duration=min(DT,2.5-self.paid_carry_seconds);self.paid_carry_seconds+=duration
                self.add(terms,'guided_carry',.8*duration)
                progress=max(0.,self.sign*float(bp[1]-before.ball.position[1]))
                progress=min(progress,800-self.paid_progress)
                self.paid_progress+=progress;self.add(terms,'carry_progress',.002*progress)
        if self.stage.startswith('reset'):
            old_delta=before.ball.position-old.physics.position
            old_alignment=max(0.,float(np.dot(-old.physics.rotation_mtx[:,2],unit(old_delta))))
            alignment=max(0.,float(np.dot(-c.physics.rotation_mtx[:,2],unit(delta))))
            old_potential=old_alignment/(1+old_dist/200)
            new_potential=alignment/(1+distance/200)
            self.add(terms,'wheel_alignment',.30*(new_potential-old_potential))

        # Four wheel rays on the ball + an actual false->true flip transition.
        # on_ground can be true during ball-wheel contact, so height and geometry
        # distinguish this from landing. Body ball_touches may be zero here.
        wheels=sum(bool(x) for x in c.wheels_with_contact)
        ball_under_wheels=float(np.dot(-c.physics.rotation_mtx[:,2],unit(delta)))>.70
        away_from_surfaces=abs(cp[0])<3200 and abs(cp[1])<4500 and 250<cp[2]<1700
        near_wheel_ball=distance<155 and ball_under_wheels and bp[2]>300 and away_from_surfaces
        if not old.has_flip and c.has_flip and near_wheel_ball:self.regained_at=self.seconds
        reset=(self.regained_at is not None and self.seconds-self.regained_at<.10
               and c.has_flip and wheels==4 and near_wheel_ball)
        if reset and not self.events.reset_acquired:
            self.carry_before_reset=self.events.carry_qualified and self.seconds-self.last_carry<1.5
            self.events.reset_acquired=True;self.reset_at=self.seconds
            if self.stage.startswith('reset'):
                self.add(terms,'reset_acquisition',3.);self.reset_paid=True
        if self.stage=='air_entry' and not self.launch_paid and c.ball_touches and bp[2]>150 and bv[2]>150:
            self.add(terms,'controlled_launch',.75);self.launch_paid=True
        if self.events.reset_acquired and old.has_flip and not c.has_flip and c.has_flipped:
            self.used_flip_at=self.seconds
        if (self.used_flip_at is not None and self.seconds-self.used_flip_at<=.45
                and bool(c.ball_touches) and self.sign*float(bv[1])>150
                and self.sign*float(bv[1]-before.ball.linear_velocity[1])>100):
            self.events.reset_used=True;self.used_at=self.seconds
            if self.stage.startswith('reset') and not self.use_paid:
                self.add(terms,'useful_reset_touch',4.);self.use_paid=True

        # Only count an actual bump along a progressing shot's corridor.
        bump=c.bump_victim_id==self.opponent and self.last_bump_id!=self.opponent
        self.last_bump_id=c.bump_victim_id
        goal_vector=np.array([0.,self.sign*5120.,300.])-before.ball.position
        advance=self.sign*float(enemy.physics.position[1]-before.ball.position[1])
        goal_advance=self.sign*float(5120*self.sign-before.ball.position[1])
        projected_x=float(before.ball.position[0])+float(goal_vector[0])*advance/max(goal_advance,1.)
        in_corridor=0<advance<goal_advance and abs(float(enemy.physics.position[0])-projected_x)<650
        goalward=float(np.dot(unit(before.ball.linear_velocity),unit(goal_vector)))>.65
        if bump and in_corridor and goalward and self.events.carry_qualified and self.seconds-self.last_carry<2.0:
            self.events.useful_bump=True;self.last_bump=self.seconds
        # No standalone bump/demo reward: payoff requires the actual scored goal.
        goal=bool(after.goal_scored)
        if goal:
            scored=self.sign*float(bp[1])>0
            self.events.scored=scored;self.events.conceded=not scored
            qualified={
                'air_dribble':False,
                'air_entry':False,
                'air_finish':self.events.carry_qualified and self.seconds-self.last_carry<2.5,
                'air_bump_finish':self.events.carry_qualified and self.events.useful_bump and self.seconds-self.last_bump<2.5,
                'reset_acquire':False,'reset_use':False,
                'reset_finish':self.carry_before_reset and self.events.reset_used and self.used_at is not None and self.seconds-self.used_at<3.,
            }[self.stage]
            if not scored:self.add(terms,'conceded',-8.)
            elif self.stage in SCORING_STAGES:
                self.add(terms,'goal',2.)
                if qualified:self.add(terms,'mechanic_goal',12.)
            self.events.success=scored and qualified
        if self.stage in ('air_dribble','air_entry') and self.events.carry_qualified and not self.events.success:
            self.events.success=True;self.add(terms,'carry_completed',5.)
        if self.stage=='reset_acquire' and self.events.reset_acquired:self.events.success=True
        if self.stage=='reset_use' and self.events.reset_used:self.events.success=True
        self.previous_control=np.asarray(control).copy()
        reward=sum(terms.values())
        if not math.isfinite(reward):raise FloatingPointError('Nonfinite mechanic reward')
        return float(reward),bool(goal or self.events.success)

    def summary(self):
        return {**vars(self.events),'carry_before_reset':self.carry_before_reset,
                'seconds':self.seconds,'reward_terms':dict(self.reward_terms)}
