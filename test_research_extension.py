"""Tests use mocked state/real TorchScript CPU; RocketSim live test is Windows preflight."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
import numpy as np
import torch
ROOT=Path(__file__).resolve().parent
SOURCE_DIR=Path(__file__).resolve().parents[0]
UPSTREAM=Path(os.environ.get('AFK_TEST_EXISTING_BASE','')) if os.environ.get('AFK_TEST_EXISTING_BASE') else None

class FakePhys:
 def __init__(self):
  self.position=np.array([100.,-300.,17.]);self.rotation_mtx=np.eye(3)
  self.linear_velocity=np.zeros(3);self.angular_velocity=np.zeros(3)
class FakeCar:
 def __init__(self,orange):
  self.is_orange=orange;self.physics=FakePhys();self.boost_amount=55.;self.on_ground=True;self.has_flip=True
class FakeBall:
 position=np.array([0.,0.,92.]);linear_velocity=np.zeros(3);angular_velocity=np.zeros(3)
class FakeState:
 def __init__(self,n):
  self.cars={i:FakeCar(i>=n//2) for i in range(n)}
  self.ball=FakeBall();self.boost_pad_timers=np.zeros(34)

class ResearchTests(unittest.TestCase):
 def setUp(self):
  sys.path.insert(0,str(ROOT))
  if UPSTREAM:sys.path.insert(1,str(UPSTREAM))
 def test_sizes(self):
  from afk_team_research import validate_teams
  for mode in [(1,1),(1,2),(1,3),(2,1),(2,2),(2,3),(3,1),(3,2),(3,3)]:
   self.assertEqual(validate_teams(*mode),f'{mode[0]}v{mode[1]}')
  for mode in [(0,1),(4,1),(1,4)]:
   with self.assertRaises(ValueError):validate_teams(*mode)
 @unittest.skipUnless(UPSTREAM is not None,'Supply AFK_TEST_EXISTING_BASE for real baseline tests')
 def test_nexto_multi_input_shapes(self):
  from afk_team_research import TeamObserver
  from native_nexto import actor_logits
  model=torch.jit.load(str(UPSTREAM/'vendor'/'nexto'/'nexto-model.pt'),map_location='cpu')
  for count in range(2,7):
   view=TeamObserver().observe(FakeState(count),{})
   self.assertEqual(len(view),count)
   for obs in view.values():
    q,kv,mask=obs
    self.assertEqual(q.shape,(1,32));self.assertEqual(kv.shape,(41,24));self.assertEqual(mask.shape,(41,))
    self.assertEqual(int(mask.sum()),6-count)
    log=actor_logits(model,*[torch.from_numpy(a[None]).float() for a in obs])
    self.assertEqual(tuple(log.shape),(1,90))
 @unittest.skipUnless(UPSTREAM is not None,'Supply AFK_TEST_EXISTING_BASE for real export tests')
 def test_export_model_no_input_change(self):
  import export_rlbot_v4 as exporter
  with tempfile.TemporaryDirectory() as root:
   d=Path(root);model=d/'nexto-model.pt'
   shutil=__import__('shutil');shutil.copy2(UPSTREAM/'vendor'/'nexto'/'nexto-model.pt',model)
   exporter.SOURCE=model
   exporter.OUTPUT=d/'exports'
   exporter.TEMPLATE=ROOT/'rlbot_v4_template'
   m=torch.jit.load(str(model),map_location='cpu')
   native=d/'candidate.pt'
   torch.save({'actor':m.state_dict()},native)
   before=exporter.sha(native)
   out=exporter.export(native,'Experimental_Cycle_09')
   self.assertTrue((out/'nexto-model.pt').is_file())
   self.assertEqual(exporter.sha(native),before)
   with self.assertRaises(FileExistsError):exporter.export(native,'Experimental_Cycle_09')
   info=__import__('json').loads((out/'EXPORT_INFO.json').read_text('utf8'))
   self.assertEqual(info['source_sha256'],before)
 def test_export_name_safety(self):
  from export_rlbot_v4 import validate_name
  for bad in ['../bad','bad name','../','/abs','']:
   with self.assertRaises(ValueError):validate_name(bad)

if __name__=='__main__':unittest.main()
