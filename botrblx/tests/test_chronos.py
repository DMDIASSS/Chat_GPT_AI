"""Run the real Luau port, not a Python replica of its matrix implementation."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import torch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import chronos
import build_chronos
import export_standalone as export
import test_standalone as legacy_tests

LUAU = os.environ.get("LUAU_BIN") or shutil.which("luau")
ASSETS = Path(os.environ.get("CHRONOS_ASSETS", APP / "models/chronos"))


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        policy = (APP / "templates/local_chronos.lua").read_text()
        common = (APP / "templates/local_policy.lua").read_text()
        policy = policy.replace("-- COMMON_ADAPTER_HERE", "local Policy={}\n" +
            common[common.index("function Policy.decode"):common.index("local function dense")] +
            common[common.index("function Policy.actions()"):common.rindex("return Policy")])
        policy = policy.replace("-- CHRONOS_PADS_HERE", export.literal(chronos.PADS.tolist()))
        policy = policy.replace("-- CHRONOS_MIRROR_PADS_HERE", export.literal([i+1 for i in chronos.MIRROR_PADS]))
        cls.module = "local Policy=(function()\n" + policy + "\nend)()\n"

    run_lua = legacy_tests.StandaloneTests.run_lua

    def test_observations_reflections_masks_and_actions(self):
        cases = []
        for packet, previous, flip in chronos.fixtures():
            obs, context = chronos.observe(packet, previous, flip)
            cases.append(dict(packet=packet, previous=previous, flip=flip, obs=obs.tolist(), context=context))
        masks = [dict(ground=g, boost=b, flip=f, turtled=t, expected=chronos.action_mask(g,b,f,t))
                 for g in (False,True) for b in (0,33) for f in (False,True) for t in (False,True)]
        source = self.module + "local cases=" + export.literal(cases) + "\nlocal masks=" + export.literal(masks)
        source += '''
for _,c in ipairs(cases)do
 local obs,context=Policy.observe(c.packet,c.previous,c.flip,function(i)return i end)
 assert(#obs==225 and context.mirror==c.context.mirror)
 for i,v in ipairs(obs)do assert(math.abs(v-c.obs[i])<3e-6,'Obs '..i)end
 for i,v in ipairs(context.mask)do assert(v==c.context.mask[i],'Mask '..i)end
 for i=1,90 do
  local original=Policy.actions()[i]
  local actual=Policy.action(i,context)
  for j,v in ipairs(actual)do
   local expected=original[j]*(context.mirror and(j==2 or j==4 or j==5)and -1 or 1)
   assert(v==expected,'Reflected controls')
  end
 end
end
for _,c in ipairs(masks)do
 for i,v in ipairs(Policy.mask(c.ground,c.boost,c.flip,c.turtled))do assert(v==c.expected[i])end
end
print('CHRONOS_OBSERVATIONS_OK')
'''
        self.assertIn("CHRONOS_OBSERVATIONS_OK", self.run_lua(source))

    def test_unknown_pads_are_not_fabricated_and_team_rotation_preserves_slots(self):
        p, previous, flip = copy.deepcopy(chronos.fixtures()[0])
        p["boost_pads"] = []
        obs, _ = chronos.observe(p, previous, flip)
        np.testing.assert_array_equal(obs[17:51], np.zeros(34))
        for i, pad in enumerate(chronos.PADS):
            p["boost_pads"] = [dict(position=pad.tolist(), is_big=bool(pad[2]>72), active=True)]
            p["team"] = 0
            p["car"]["position"][0] = -1200
            a, _ = chronos.observe(p, previous, flip)
            self.assertEqual(a[17+i], 1)
            p["team"] = 1
            p["car"]["position"][0] = 1200
            b, _ = chronos.observe(p, previous, flip)
            self.assertEqual(b[17+33-i], 1)

    def test_padding_and_supported_team_sizes(self):
        p, previous, flip = copy.deepcopy(chronos.fixtures()[0])
        other = p["other_cars"][0]
        p["other_cars"] += [dict(other, team=0), dict(other, team=0), dict(other), dict(other)]
        obs, context = chronos.observe(p, previous, flip)
        self.assertEqual(obs.shape, (225,))
        self.assertEqual(context["entity_count"], 7)
        p["other_cars"].append(dict(other, team=0))
        with self.assertRaisesRegex(ValueError, "three cars per team"):
            chronos.observe(p, previous, flip)


@unittest.skipUnless((ASSETS / "POLICY.lt").exists(), "Build/download the pinned Chronos assets first")
class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.model = chronos.Chronos(ASSETS)
        cls.tensors, cls.cases = chronos.prepare_model(cls.model)
        cls.source = build_chronos.source(ASSETS)
        cls.module = cls.source.split("local Keyboard=(function()", 1)[0]

    run_lua = legacy_tests.StandaloneTests.run_lua
    client_case = legacy_tests.StandaloneTests.client_case

    def test_full_float32_network_matches_pytorch(self):
        source = self.module + "local tensors=(function()\n" + export.tensor_source(self.tensors) + "\nend)()\n"
        source += "local predict=Policy.new(tensors)\nlocal cases=" + export.literal(self.cases)
        source += '''
local peak,total=0,0
for _,c in ipairs(cases)do
 local at=os.clock()
 local action,logits=predict(c.query,c.entities)
 local ms=(os.clock()-at)*1000;peak=math.max(peak,ms);total=total+ms
 assert(action==c.action,'Action differs from PyTorch')
 for i,v in ipairs(logits)do
  assert(math.abs(v-c.logits[i])<.0003+math.abs(c.logits[i])*.0001,'Chronos logit '..i)
 end
end
print('CHRONOS_PARITY_OK',#cases,'mean_ms',total/#cases,'peak_ms',peak)
'''
        out = self.run_lua(source)
        self.assertIn("CHRONOS_PARITY_OK", out)
        print(out.strip())

    def test_f8_focus_loss_close_and_no_runtime_http(self):
        self.client_case('''
move(.05);inputKey('F6')
for i=1,26 do move(1/30)end
assert(#emissions>0,'Chronos did not send inputs')
inputKey('F8')
local paused=#emissions
for i=1,10 do move(1/30)end
assert(#emissions==paused,'F8 did not pause Chronos')
inputKey('F6');for i=1,15 do move(1/30)end
windowActive=false;services.UserInputService.WindowFocusReleased:Fire()
local lost=#emissions
for i=1,10 do move(1/30)end
assert(#emissions==lost,'Focus loss did not pause Chronos')
windowActive=true;services.UserInputService.WindowFocused:Fire()
inputKey('F6');for i=1,15 do move(1/30)end
click('Close')
''', '''
local down={}
for _,e in ipairs(emissions)do if e[1]=='down'then down[e[2]]=true else down[e[2]]=nil end end
assert(next(down)==nil,'Held keys survived close')
assert(playerGui.children.Update271Standalone.destroyed)
''')

    def test_corrupt_or_unrecognized_weights_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p/"SHARED_HEAD.lt").write_bytes(b"wrong model")
            with self.assertRaisesRegex(ValueError, "Unrecognized Chronos asset"):
                chronos.Chronos(p)

    def test_generated_download_matches_current_builder(self):
        artifact=APP.parent/'downloads/TurboBall_Chronos.lua'
        self.assertEqual(artifact.read_bytes(),self.source.encode('utf-8'))

    def test_buffer_loader_vector_slices_and_scalar_fallback_match(self):
        source=self.module+'\nlocal Worker=(function()\n'+(APP/'templates/local_cooperative.lua').read_text()+'\nend)()\n'
        source+='local loadingYield=function()end\nlocal tensors=(function()\n'+build_chronos.tensor_source(self.tensors)+'\nend)()\n'
        source+='local predict,backend=Policy.new(tensors)\nlocal scalar=Policy.new(tensors,{vector=false})\nlocal cases='+export.literal(self.cases)
        source+='''
assert(backend=='vector float32','Fast backend was not selected')
local w=Worker.new(predict)
local peak,total,slices=0,0,0
for _,c in ipairs(cases)do
 w:start(c.query,c.entities,{})
 local result
 repeat
  local at=os.clock();result=w:step(.0015);peak=math.max(peak,(os.clock()-at)*1000)
 until result
 assert(result.index==c.action)
 total+=result.cpu*1000;slices+=result.slices
 local action,reference=scalar(c.query,c.entities)
 assert(action==c.action)
 for i,v in ipairs(result.logits)do
  assert(math.abs(v-c.logits[i])<.0003+math.abs(c.logits[i])*.0001,'Sliced/vector mismatch '..i)
  assert(math.abs(reference[i]-c.logits[i])<.0003+math.abs(c.logits[i])*.0001,'Fallback mismatch '..i)
 end
end
assert(slices>#cases,'Inference did not yield between frames')
print('SLICED_PARITY_OK',#cases,'mean_cpu_ms',total/#cases,'peak_slice_ms',peak,'slices',slices)
'''
        out=self.run_lua(source);self.assertIn('SLICED_PARITY_OK',out);print(out.strip())

    def test_graphics_default_toggle_and_close_restore(self):
        self.client_case('''
assert(result.version=='local-6.9')
assert(not lighting.GlobalShadows,'Light graphics did not start enabled')
for i=1,10 do move(1/120)end
click('Game optimization: ON');assert(lighting.GlobalShadows)
click('Game optimization: OFF');assert(not lighting.GlobalShadows)
click('Lag compensation: ON');click('Lag compensation: OFF')
click('Close')
''', '''
assert(lighting.GlobalShadows,'Close did not restore graphics')
''',extra='''
local lighting=object('Lighting','Lighting');lighting.Parent=workspace;lighting.GlobalShadows=true
services.Lighting=lighting
''')

    def test_f8_cancels_a_yielded_job_and_restart_uses_new_work(self):
        needle='local predict,backend=Policy.new(loadTensors(),{yieldWork=RUNTIME.cooperative and loadingYield or nil})'
        wrapped='''local rawPredict,backend=Policy.new(loadTensors(),{yieldWork=loadingYield})
local function predict(q,c,checkpoint)
 if slowRuntime then
  jobsStarted+=1
  for i=1,100 do now+=.0004;checkpoint()end
 end
 local action,logits=rawPredict(q,c,checkpoint)
 if slowRuntime then jobsFinished+=1 end
 return action,logits
end'''
        self.assertIn(needle,self.source)
        self.client_case('''
slowRuntime=true
move(.05);inputKey('F6')
for i=1,120 do move(1/120);if jobsStarted>0 then break end end
assert(jobsStarted>0 and jobsFinished==0,'No suspended runtime job to cancel')
inputKey('F8')
local paused=#emissions
for i=1,80 do move(1/120)end
assert(jobsFinished==0 and #emissions==paused,'Paused coroutine finished or sent an input')
inputKey('F6')
for i=1,180 do move(1/120);if jobsFinished>0 then break end end
assert(jobsFinished>0 and jobsStarted>1,'Restart did not complete a fresh job')
inputKey('F8');click('Close')
''','''
local count=jobsFinished
for i=1,80 do move(1/120)end
assert(jobsFinished==count,'Closed work resumed')
''',extra='''
local slowRuntime=false
local jobsStarted,jobsFinished=0,0
task.wait=function(dt)move(dt or 1/120)end
''',source=self.source.replace(needle,wrapped))


if __name__ == "__main__":
    unittest.main()
