"""CI check independent of game assets, Torch and RLGym installation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from attentionforge import _attention_native as n
from attentionforge.observation import encode_reference,ACTIONS
assert n.feature_version==2
np.testing.assert_array_equal(n.action_table(),ACTIONS)
for team in (1,2,3):
    w=np.random.default_rng(71).normal(size=(2,1+2*team,32)).astype(np.float32)
    w[:,:,9:15]=[1,0,0,0,0,1];w[:,:,15]=40;w[:,:,18]=0;w[:,:,20]=0
    p=np.zeros((2,34,2),np.float32);loc=np.random.default_rng(81).normal(size=(34,4)).astype(np.float32)
    a,m=n.encode(w,p,loc);b,l=encode_reference(w,p,loc)
    np.testing.assert_allclose(a,b,rtol=2e-6,atol=2e-6);np.testing.assert_array_equal(m,l)
print('WINDOWS_NATIVE_ACTION_AND_OBSERVATION_PARITY_PASS')

assert n.reward_version>=1
assert abs(n.control_value(200.,2000.,1000.,100.)+n.control_value(2000.,200.,1000.,100.))<1e-6
s=n.ShotTrace();s.observe(1,False,1);assert s.clean(0,2,720);s.observe(0,True,3);assert not s.clean(0,4,720)
print('WINDOWS_REWARD_MATH_AND_TRACKER_PASS')

assert n.reward_version>=2
c=n.ComboTrace();c.touch(1,0);c.event(0,2,1);a=c.goal(0,2);c.event(0,2,3);assert c.goal(0,4)==a;c.touch(2,5);assert c.goal(0,6)==0
print('WINDOWS_SKILLS_CHAIN_ANTI_REPEAT_PASS')

assert n.reward_version>=3
q=n.attack_shot_quality(0,0,94,0,2000,0,0)
assert q>0.8 and n.attack_shot_quality(0,0,94,900,2000,0,0)<.1
assert abs(q-n.attack_shot_quality(0,0,94,0,-2000,0,1))<1e-6
print('WINDOWS_AIM_QUALITY_AND_TEAM_SYMMETRY_PASS')
