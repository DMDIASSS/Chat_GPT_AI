"""Fresh, small reward hypotheses for controlled tests; NOT a trainer.
Dimensions/weights and limitations are documented in REWARDS.md.
"""
import math

def potential(ball):
    x,y,z=ball;scale=3000.
    def dist(goal_y):return math.sqrt(x*x+(y-goal_y)**2+(z-200.)**2)
    return math.exp(-dist(5120.)/scale)-math.exp(-dist(-5120.)/scale)

def components(before_ball,after_ball,before_velocity,after_velocity,touched,scoring_team,gamma=.995,terminal=False,impulse_weight=.05):
    """Two per-player rewards. Timeouts are NOT true terminal transitions.
    For a goal, scoring_team is 0/1; otherwise None. Return both raw and weighted.
    """
    if scoring_team not in (None,0,1):raise ValueError('Invalid scoring team')
    if scoring_team is not None and not terminal:raise ValueError('A goal is terminal in this proposed training contract')
    if not 0<gamma<=1 or not 0<=impulse_weight<=.1:raise ValueError('Invalid fixed experimental parameters')
    old=potential(before_ball);new=0. if terminal else potential(after_ball)
    shaping=.25*(gamma*new-old)
    impulse=min(1.,math.sqrt(sum((a-b)**2 for a,b in zip(after_velocity,before_velocity)))/3000.)
    rows=[]
    for player in (0,1):
        goal=0. if scoring_team is None else 1. if scoring_team==player else -1.
        pbrs=shaping if player==0 else -shaping
        touch=impulse_weight*impulse if touched[player] else 0.
        rows.append({'goal':goal,'goal_potential':pbrs,'touch_impulse':touch,'total':goal+pbrs+touch})
    return rows
