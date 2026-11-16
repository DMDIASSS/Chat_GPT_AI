import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reward_reference import potential,components

class RewardChecks(unittest.TestCase):
    def test_goal_and_own_goal_credit_depends_on_scoring_team(self):
        out=components([0,0,94],[0,5300,94],[0,0,0],[0,2000,0],(False,True),0,terminal=True)
        self.assertEqual(out[0]['goal'],1);self.assertEqual(out[1]['goal'],-1)
    def test_potential_color_rotation(self):
        for p in [(0,0,94),(1000,4400,300),(-1200,-1400,2000)]:self.assertAlmostEqual(potential(p),-potential((-p[0],-p[1],p[2])))
    def test_pbrs_discounted_telescoping_including_terminal(self):
        states=[[0,-2400,94],[100,2500,400],[0,5000,94]];gamma=.995;parts=[]
        for k in range(2):parts.append(components(states[k],states[k+1],[0,0,0],[0,0,0],(False,False),None,gamma,terminal=k==1,impulse_weight=0)[0]['goal_potential'])
        self.assertAlmostEqual(parts[0]+gamma*parts[1],-.25*potential(states[0]))
    def test_timeouts_keep_potential_for_value_bootstrap(self):
        before=[0,1000,94];after=[0,2000,94]
        r=components(before,after,[0,0,0],[0,0,0],(False,False),None,terminal=False,impulse_weight=0)
        self.assertAlmostEqual(r[0]['goal_potential'],.25*(.995*potential(after)-potential(before)))
    def test_no_airtime_jump_flip_or_boost_bonus(self):
        r=components([0,0,94],[0,0,94],[0,0,0],[0,0,0],(False,False),None)
        self.assertEqual(r[0]['touch_impulse'],0);self.assertEqual(r[0]['total'],0)
    def test_impulse_is_small_bounded_and_contact_gated(self):
        r=components([0,0,94],[0,0,94],[0,0,0],[0,10000,0],(True,False),None)
        self.assertEqual(r[0]['touch_impulse'],.05);self.assertEqual(r[1]['touch_impulse'],0)
    def test_reject_wrong_goal_terminal_contract(self):
        with self.assertRaises(ValueError):components([0,0,94],[0,5200,94],[0,0,0],[0,0,0],(False,False),0)

class ModelChecks(unittest.TestCase):
    def test_model_counts_and_finite_shapes(self):
        import torch
        from model_probe import MODELS
        torch.set_num_threads(1)
        for name,factory in MODELS.items():
            model=factory().eval();params=sum(x.numel() for x in model.parameters());self.assertTrue(1_000_000<=params<=5_000_000,(name,params))
            with torch.no_grad():a,v=model(torch.zeros(2,109))
            self.assertEqual(tuple(a.shape),(2,90));self.assertEqual(tuple(v.shape),(2,));self.assertTrue(torch.isfinite(a).all())

if __name__=='__main__':unittest.main()
