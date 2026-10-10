import sys
from pathlib import Path
from types import SimpleNamespace as N
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finishing_core import predict_direct_goal, FinishingTracker, opponent_has_lane


def state(ball_pos=(0,4000,300),ball_v=(0,1500,0),ours_touch=False,
          opp_pos=(1400,4500,17),ours_orange=False,flipping=False):
    ours=N(is_orange=ours_orange,ball_touches=int(ours_touch),is_flipping=flipping,
           physics=N(position=np.array([0.,3600.,17.])))
    opp=N(is_orange=not ours_orange,ball_touches=0,
           physics=N(position=np.array(opp_pos,dtype=float)))
    return N(ball=N(position=np.array(ball_pos,dtype=float),
                    linear_velocity=np.array(ball_v,dtype=float)),cars={0:ours,1:opp})

class TestFinishing(unittest.TestCase):
    def test_direct_goal_prediction(self):
        self.assertTrue(predict_direct_goal([0,4000,300],[0,1500,0],1))
        self.assertTrue(predict_direct_goal([0,-4000,300],[0,-1500,0],-1))
        self.assertFalse(predict_direct_goal([1800,4000,300],[0,1500,0],1))
        self.assertFalse(predict_direct_goal([0,4000,300],[0,-1500,0],1))
        self.assertFalse(predict_direct_goal([0,4000,1000],[0,1500,0],1))
    def test_reward_on_accurate_touch_not_direction_alone(self):
        s=state()
        t=FinishingTracker(False);t.begin(s)
        bonus,_=t.step(s,0,1)
        self.assertEqual(bonus,0)
        s=state(ours_touch=True)
        bonus,event=t.step(s,0,1)
        self.assertTrue(event['on_target'])
        self.assertEqual(t.counts['direct_on_target_proxy'],1)
        self.assertGreater(bonus,0)
        for _ in range(15):
            s=state(ours_touch=True)
            bonus,event=t.step(s,0,1)
            self.assertEqual(bonus,0) # anti-spam cooldown
    def test_defender_in_lane_discount(self):
        s=state(opp_pos=(100,4450,17),ours_touch=True)
        t=FinishingTracker(False);t.begin(s)
        bonus,event=t.step(s,0,1)
        self.assertEqual(t.counts['blocked_lane_on_target'],1)
        self.assertAlmostEqual(bonus,.025)
    def test_backboard_only_not_rewarded(self):
        initial=state(ball_pos=(0,4830,800),ball_v=(0,850,0),ours_touch=True)
        t=FinishingTracker(False);t.begin(initial)
        t.step(initial,0,1)
        bounce=state(ball_pos=(0,4890,770),ball_v=(0,-350,-25))
        bonus,events=t.step(bounce,0,1)
        self.assertTrue(events['backboard'])
        self.assertEqual(bonus,0)
        self.assertEqual(t.counts['backboard_bounce_proxy'],1)
    def test_second_touch_after_backboard_can_reward(self):
        initial=state(ball_pos=(0,4830,800),ball_v=(0,850,0),ours_touch=True)
        t=FinishingTracker(False);t.begin(initial)
        t.step(initial,0,1)
        bounce=state(ball_pos=(0,4890,770),ball_v=(0,-350,-25))
        t.step(bounce,0,1)
        second=state(ball_pos=(0,4750,350),ball_v=(0,1750,0),ours_touch=True)
        bonus,events=t.step(second,0,1)
        self.assertTrue(events['followup'])
        self.assertGreaterEqual(bonus,.12)
        self.assertEqual(t.counts['followup_on_target_proxy'],1)
        self.assertFalse(t.step(second,0,1)[1]['followup'])
    def test_goal_counter_and_no_forced_shot_penalty(self):
        s=state(ball_pos=(1000,0,150),ball_v=(0,0,0))
        t=FinishingTracker(False);t.begin(s)
        reward,event=t.step(s,0,1)
        self.assertEqual(reward,0)
        t.step(s,0,1,goal=True,winner='nexto')
        self.assertEqual(t.counts['goals_against'],1)

if __name__=='__main__':unittest.main()
