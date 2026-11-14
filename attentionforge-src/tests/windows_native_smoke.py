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
