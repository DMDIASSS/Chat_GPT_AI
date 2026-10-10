"""Pure local geometry tests; no RocketSim/RLBot installation needed."""
import unittest
import numpy as np
from fusion_logic import decide, first_man, drive_toward, defensive_danger, support_target

class Physics:
    def __init__(self,pos,vel=(0,0,0),forward=(0,1,0)):
        self.position=np.asarray(pos,dtype=float)
        self.linear_velocity=np.asarray(vel,dtype=float)
        self._forward=forward
    def rotation_mtx(self):
        vec=np.asarray(self._forward,dtype=float)
        vec=vec/np.linalg.norm(vec)
        left=np.array([-vec[1],vec[0],0.])
        return np.stack([vec,left,np.array([0.,0.,1.])],axis=1)

class Player:
    def __init__(self,i,pos,vel=(0,0,0),forward=(0,1,0),on_ground=True):
        self.car_id=i
        self.car_data=Physics(pos,vel,forward)
        self.on_ground=on_ground
        self.team_num=0

class FusionTests(unittest.TestCase):
    def test_kickoff_left_goes(self):
        a=Player(1,(-2048,-2560,17))
        b=Player(2,(2048,-2560,17))
        for self_car,other in ((a,b),(b,a)):
            self.assertEqual(first_man(self_car,[other],np.array([0.,0.,93.]),True,0),1)

    def test_farther_second_man_coverage(self):
        first=Player(1,(0.,-200.,17.))
        second=Player(2,(300.,-2600.,17.))
        ball=np.array([100.,-100.,93.])
        a=decide(first,[second],[],ball,np.zeros(3),0)
        b=decide(second,[first],[],ball,np.zeros(3),0)
        self.assertEqual(a.role,'first')
        self.assertEqual(b.role,'second')
        self.assertEqual(b.policy,'support')
        self.assertLess(b.target[1],ball[1])

    def test_defense_chooses_wavedash(self):
        a=Player(1,(0.,-3500.,17))
        d=decide(a,[],[],np.array([0.,-3100.,93.]),np.array([0.,-700.,0.]),0)
        self.assertTrue(d.danger)
        self.assertEqual(d.policy,'wavedash')

    def test_ideal_finishing_lane_chooses_champion(self):
        a=Player(1,(0.,2100.,17))
        d=decide(a,[],[],np.array([0.,3200.,93.]),np.zeros(3),0)
        self.assertEqual(d.policy,'champion')

    def test_else_cycle9(self):
        a=Player(1,(0.,-300.,17))
        d=decide(a,[],[],np.array([0.,0.,93.]),np.zeros(3),0)
        self.assertEqual(d.policy,'cycle9')

    def test_orange_mirror(self):
        first=Player(1,(0.,200.,17))
        second=Player(2,(200.,2600.,17))
        ball=np.array([0.,100.,93.])
        b=decide(second,[first],[],ball,np.zeros(3),1)
        self.assertEqual(b.policy,'support')
        self.assertGreater(b.target[1],ball[1])

    def test_controller_valid_actions_and_brakes(self):
        a=Player(1,(0.,-3000.,17))
        mate=Player(2,(0.,-2700.,17))
        c=drive_toward(a,np.array([0.,-1000.]),[mate])
        self.assertEqual(c.shape,(8,))
        self.assertTrue(np.isfinite(c).all())
        self.assertTrue(all(-1<=x<=1 for x in c))
        self.assertEqual(c[0],-1.)

    def test_no_danger_opponent_half(self):
        self.assertFalse(defensive_danger(np.array([0.,3000.,93.]),np.array([0.,-100.,0.]),0))

    def test_support_target_stays_behind_play(self):
        a=Player(3,(0.,1500.,17))
        t=support_target(np.array([0.,3000.,93.]),a,0)
        self.assertLess(t[1],3000)

if __name__=='__main__':unittest.main()
