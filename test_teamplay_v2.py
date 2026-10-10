"""Pure 2v2 team-shaping smoke tests. Requires project dependencies but no RocketSim."""
import unittest
from types import SimpleNamespace as NS
import numpy as np
from teamplay_v2 import primary_for_state, support_target, shaping


def car(x,y,vx=0.,vy=0.,boost=35.):
    return NS(physics=NS(position=np.array([x,y,17.]),
                         linear_velocity=np.array([vx,vy,0.])),boost_amount=boost)


def state(ball,velocity,cars):
    return NS(ball=NS(position=np.array([*ball,100.]),
                      linear_velocity=np.array([*velocity,0.])),cars=cars)

class CoordinationTests(unittest.TestCase):
    def test_first_man_can_switch(self):
        near=state((0,0),(0,0),{1:car(0,-500),2:car(0,-2200)})
        far=state((0,0),(0,0),{1:car(0,-2200),2:car(0,-500)})
        self.assertEqual(primary_for_state(near,[1,2]),1)
        self.assertEqual(primary_for_state(far,[1,2]),2)

    def test_second_man_relocation_is_rewarded_not_standing_still(self):
        s=state((300,1500),(0,0),{1:car(300,1200),2:car(-1800,-1800,vy=700)})
        target=support_target(s,False,1)
        before={1:np.array([300,1200,17.]),2:np.array([-1800,-1800,17.])}
        moving=state((300,1500),(0,0),{1:car(300,1200),2:car(-1400,-1500,vy=700)})
        stopped=state((300,1500),(0,0),{1:car(300,1200),2:car(-1800,-1800)})
        mover_bonus,_=shaping(before,target,moving,[1,2],False,1)
        idle_bonus,stopped_metrics=shaping(before,target,stopped,[1,2],False,1)
        self.assertGreater(mover_bonus[2],idle_bonus[2])
        self.assertEqual(stopped_metrics['second_man_idle'],1)

    def test_dual_commit_only_when_goal_exposed_and_ball_reversing(self):
        before={1:np.array([-150,1050.,17.]),2:np.array([150,1050.,17.])}
        after=state((0,650),(0,-800),{1:car(-150,1050),2:car(150,1050)})
        _,m=shaping(before,np.array([0,-400,17]),after,[1,2],False,1)
        self.assertEqual(m['dual_commit_risk'],1)
        safe=state((0,650),(0,800),{1:car(-150,1050),2:car(150,1050)})
        _,m2=shaping(before,np.array([0,-400,17]),safe,[1,2],False,1)
        self.assertEqual(m2['dual_commit_risk'],0)

    def test_opposing_team_own_goal_orientation(self):
        s=state((0,1000),(0,0),{1:car(0,500),2:car(700,2000)})
        blue=support_target(s,False,1)
        orange=support_target(s,True,1)
        self.assertLess(blue[1],1000)
        self.assertGreater(orange[1],1000)

if __name__=='__main__':unittest.main(verbosity=2)
