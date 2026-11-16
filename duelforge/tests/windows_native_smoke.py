import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from duelforge import _native
from duelforge.observation import ACTIONS
np.testing.assert_array_equal(_native.action_table(),ACTIONS)
assert _native.contract=='duelforge-109-v1-octane-120hz-skip8-delay7'
assert _native.version==1
print('DUELFORGE_WINDOWS_NATIVE_IMPORT_ACTION_CONTRACT_PASS')
from duelforge.observation import encode
rng=np.random.default_rng(13);w=rng.normal(size=(12,3,32)).astype(np.float32);w[:,:,0:3]*=1000;w[:,:,3:6]*=1000;w[:,1:,15]=rng.uniform(0,100,(12,2));w[:,1:,16:21]=rng.integers(0,2,(12,2,5));w[:,1:,29]=rng.integers(0,2,(12,2))
locations=np.zeros((34,4),np.float32)
for j in range(17):locations[j,:3]=[100*j+10,200*j+20,70];locations[33-j,:3]=[-100*j-10,-200*j-20,70]
pads=np.zeros((12,34,2),np.float32);pads[:,:,0]=rng.integers(0,2,(12,34));pads[:,:,1]=rng.uniform(0,10,(12,34))
a,l=_native.encode(w,pads,locations);b,k=encode(w,pads,locations);np.testing.assert_allclose(a,b,atol=2e-6,rtol=2e-6);np.testing.assert_array_equal(l,k)
print('DUELFORGE_WINDOWS_NATIVE_OBSERVATION_MASK_PARITY_PASS')

from duelforge.potential import estimate_reference
w=np.zeros((48,3,32),np.float32);w[:,:,0:2]=rng.uniform(-3000,3000,(48,3,2));w[:,0,2]=rng.uniform(94,1200,48);w[:,1:,2]=rng.uniform(17,700,(48,2));w[:,:,3:6]=rng.uniform(-1600,1600,(48,3,3));w[:,1:,15]=rng.uniform(0,100,(48,2));w[:,1:,16]=rng.integers(0,2,(48,2));w[:,1:,29]=rng.integers(0,2,(48,2));angles=rng.uniform(-3.14,3.14,(48,2));w[:,1:,9]=np.cos(angles);w[:,1:,10]=np.sin(angles);w[:,1:,14]=1
c={'predictive':{'horizon':3.,'samples':16,'temperature':.6,'intercept_weight':.8,'threat_weight':.2}}
r=estimate_reference(w,c);f=dict(_native.predictive_estimate(w,3.,16,.6,.8,.2))
for name in ('eta','phi','intercept','threat'):np.testing.assert_allclose(f[name],r[name],atol=2e-4,rtol=2e-4)
for name in ('reachable','prediction_quality'):np.testing.assert_array_equal(f[name],r[name])
print('DUELFORGE_WINDOWS_NATIVE_INTERCEPTION_REFERENCE_PARITY_PASS')
