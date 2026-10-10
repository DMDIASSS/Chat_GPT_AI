import sys, unittest, random
from pathlib import Path
from types import SimpleNamespace as N
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finishing_scenarios import configure_shot, SCENARIOS

def state():
    def car(orange):
        return N(is_orange=orange,physics=N(position=np.zeros(3),linear_velocity=np.zeros(3),
                     angular_velocity=np.zeros(3),rotation_mtx=np.eye(3)),boost_amount=0)
    return N(ball=N(position=np.zeros(3),linear_velocity=np.zeros(3),angular_velocity=np.zeros(3)),
             cars={0:car(False),1:car(True)})
class Tests(unittest.TestCase):
    def test_scenarios_in_bounds_nonoverlap_both_sides(self):
        for scenario in SCENARIOS:
            for orange in [False,True]:
                for seed in range(20):
                    s=state()
                    configure_shot(s,orange,scenario,rng=random.Random(seed))
                    self.assertLess(abs(s.ball.position[0]),3500)
                    self.assertLess(abs(s.ball.position[1]),4800)
                    self.assertGreater(s.ball.position[2],90)
                    self.assertLess(s.ball.position[2],1100)
                    for car in s.cars.values():
                        self.assertLess(abs(car.physics.position[0]),4000)
                        self.assertLess(abs(car.physics.position[1]),5000)
                        self.assertGreaterEqual(car.physics.position[2],16)
                        self.assertGreater(car.boost_amount,0)
                    self.assertGreater(np.linalg.norm(s.cars[0].physics.position-s.cars[1].physics.position),100)
    def test_invalid(self):
        with self.assertRaises(ValueError):configure_shot(state(),False,'invalid')
if __name__=='__main__':unittest.main()
