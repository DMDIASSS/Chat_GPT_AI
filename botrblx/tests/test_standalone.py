"""Numerical and control-lifecycle checks for the actual standalone Lua runtime."""
import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import torch

HERE=Path(__file__).resolve().parent
APP=HERE.parent
sys.path.insert(0,str(APP))
import export_standalone as export
import bridge271 as bridge

LUAU=os.environ.get("LUAU_BIN") or shutil.which("luau")
BASE=APP.parent/"vendor/nexto/nexto-model.pt"


@unittest.skipUnless(BASE.is_file(),"Local Nexto asset unavailable")
class StandaloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.model=bridge.load_model(BASE,BASE)
        cls.tensors,cls.cases=export.prepare_model(cls.model)
        cls.policy=(APP/"templates/local_policy.lua").read_text(encoding="utf-8")
        cls.module="local Policy=(function()\n"+cls.policy+"\nend)()\n"
        cls.source=export.standalone_source(cls.model,hashlib.sha256(BASE.read_bytes()).hexdigest())

    def run_lua(self,source):
        if not LUAU: self.skipTest("Set LUAU_BIN to verify the Lua network and controls")
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"test.luau";path.write_text(source,encoding="utf-8")
            result=subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return result.stdout

    def test_full_float32_weights_and_logits_match_torchscript(self):
        # Exercises real base64 decode + all two-block attention/FFN computations.
        source=self.module+"local tensors=(function()\n"+export.tensor_source(self.tensors)+"\nend)()\n"
        source+="local predict=Policy.new(tensors)\nlocal cases="+export.literal(self.cases)
        source+='''
for _,case in ipairs(cases)do
 local action,logits=predict(case.query,case.entities)
 assert(action==case.action,'Action differs from PyTorch')
 for i,v in ipairs(logits)do
  assert(math.abs(v-case.logits[i])<.0003+math.abs(case.logits[i])*.0001,'Logit mismatch '..i)
 end
end
print('PARITY_OK',#cases)
'''
        self.assertIn("PARITY_OK",self.run_lua(source))

    def test_lua_observations_actions_and_emitted_axes_match_python(self):
        from test_bridge import packet
        rng=np.random.default_rng(700)
        cases=[]
        for team in (0,1):
            for ground in (True,False):
                for _ in range(5):
                    p=copy.deepcopy(packet());p["team"]=team;p["ground_estimate"]=ground
                    for body in (p["car"],p["ball"]):
                        for field in ("position","velocity"):
                            body[field]=rng.uniform(-1500,1500,3).tolist()
                        body["angular_velocity"]=rng.uniform(-5,5,3).tolist()
                    yaw=float(rng.uniform(-np.pi,np.pi))
                    p["car"]["forward"]=[float(np.sin(yaw)),float(np.cos(yaw)),0]
                    previous=bridge.lookup_table()[int(rng.integers(90))]
                    q,kv,_=bridge.observations(p,previous,not ground)
                    cases.append(dict(packet=p,previous=previous.tolist(),flip=not ground,
                                      q=q[0,0].tolist(),kv=kv[0,:2].tolist()))
        mapping=[]
        for ground in (True,False):
            for action in bridge.lookup_table():
                keys,actual=bridge.mapped_keys(action,ground)
                mapping.append(dict(action=action.tolist(),ground=ground,keys={k:True for k in keys},actual=actual.tolist()))
        source=self.module+"local cases="+export.literal(cases)+"\nlocal mapping="+export.literal(mapping)
        source+="\nlocal expectedActions="+export.literal(bridge.lookup_table().tolist())
        source+='''
for i,a in ipairs(Policy.actions())do for j,v in ipairs(a)do assert(v==expectedActions[i][j])end end
local function close(actual,expected)
 assert(#actual==#expected)
 for i,v in ipairs(actual)do assert(math.abs(v-expected[i])<3e-6,'Observation mismatch at '..i)end
end
for _,case in ipairs(cases)do
 local q,kv=Policy.observe(case.packet,case.previous,case.flip)
 close(q,case.q);for i,row in ipairs(kv)do close(row,case.kv[i])end
end
for _,case in ipairs(mapping)do
 local keys,actual=Policy.keys(case.action,case.ground)
 close(actual,case.actual)
 for k in pairs(keys)do assert(case.keys[k])end
 for k in pairs(case.keys)do assert(keys[k])end
end
print('OBS_AND_INPUT_OK')
'''
        self.assertIn("OBS_AND_INPUT_OK",self.run_lua(source))

    def client_case(self,behaviour,checks,extra=""):
        prefix=(HERE/"fixtures/roblox_mock.luau").read_text(encoding="utf-8")
        extra='''
services.UserInputService.WindowFocusReleased=event()
services.UserInputService.WindowFocused=event()
local windowActive=true
local isrbxactive=function()return windowActive end
local emissions={}
local function emit(kind,key)emissions[#emissions+1]={kind,key}end
local physicalDown={}
local virtualCodes={[0x57]='W',[0x41]='A',[0x53]='S',[0x44]='D',[0x51]='Q',[0x45]='E',[0x10]='LeftShift'}
services.UserInputService.IsKeyDown=function(self,key)return physicalDown[key]==true end
local keypress=function(key)physicalDown[virtualCodes[key] or key]=true;emit('down',key)end
local keyrelease=function(key)physicalDown[virtualCodes[key] or key]=nil;emit('up',key)end
local mouse1press=function()emit('down','LMB')end
local mouse1release=function()emit('up','LMB')end
local mouse2press=function()emit('down','RMB')end
local mouse2release=function()emit('up','RMB')end
local function inputKey(key)
 for _,v in ipairs(services.UserInputService.InputBegan.listeners)do
  if v.connection.enabled then v.callback({KeyCode=key},false)end
 end
end
request=function()error('Standalone must not use HTTP')end
local readfile=function()error('Standalone must not read files during operation')end
local writefile=readfile
task.wait=function(dt)move(dt)end
'''+extra
        wrapped="\nlocal function boot()\n"+self.source+"\nend\nlocal result=boot()\n"
        return self.run_lua(prefix+extra+wrapped+behaviour+checks)

    def test_standalone_owns_inputs_f8_focus_and_close(self):
        self.client_case('''
assert(result.version=='local-3')
move(.05);inputKey('F6')
for i=1,40 do move(1/30)end
assert(#emissions>0,'No local inputs sent')
inputKey('F8')
local before=#emissions
for i=1,10 do move(1/30)end
assert(#emissions==before,'F8 did not pause')
inputKey('F6');for i=1,30 do move(1/30)end
assert(#emissions>before,'F6 did not restart')
windowActive=false;services.UserInputService.WindowFocusReleased:Fire()
local focusCount=#emissions
for i=1,10 do move(1/30)end
assert(#emissions==focusCount,'Focus loss did not pause')
windowActive=true;services.UserInputService.WindowFocused:Fire()
inputKey('F6');for i=1,30 do move(1/30)end
click('Close')
''','''
local held={}
for _,e in ipairs(emissions)do
 if e[1]=='down'then held[e[2]]=true else held[e[2]]=nil end
end
assert(next(held)==nil,'Inputs left down after close')
for _,listener in ipairs(beat.listeners)do assert(not listener.connection.enabled)end
print('LIFECYCLE_OK')
''')

    def test_missing_input_function_reports_in_panel_without_pressing(self):
        self.client_case("",'''
assert(#emissions==0)
local found=false
for _,o in ipairs(created)do
 if o.Text and string.find(o.Text,'Missing executor input function: mouse2press',1,true)then found=true end
end
assert(found,'Missing input error was not visible')
click('Close')
''',extra="\nmouse2press=nil\n")

    def test_f8_during_executor_press_cannot_leave_a_late_key_down(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,10 do move(1/30)end
local oldPress=keypress
inputKey('F8')
keypress=function(key)
 if not interrupted then interrupted=true;inputKey('F8')end
 oldPress(key) -- simulate a yielding press completing after F8
end
inputKey('F6')
for i=1,40 do move(1/30)end
''','''
assert(interrupted,'Did not exercise an interrupted key press')
local held={}
for _,e in ipairs(emissions)do if e[1]=='down'then held[e[2]]=true else held[e[2]]=nil end end
assert(next(held)==nil,'A press completed after F8 and remained down')
click('Close')
''',extra='''
local interrupted=false
''')

    def test_missing_boost_releases_instead_of_running_with_fake_state(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,30 do move(1/30)end
boostLabel.Text='BOOST'
now=now+.04
beat:Fire()
''','''
local held={}
for _,e in ipairs(emissions)do if e[1]=='down'then held[e[2]]=true else held[e[2]]=nil end end
assert(next(held)==nil,'Invalid state did not release')
click('Close')
''')

    def test_cli_exports_native_actor_without_installing_or_starting_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);model=directory/"update.pt";output=directory/"private.lua"
            torch.save({"actor":self.model.state_dict()},model)
            result=subprocess.run([sys.executable,str(APP/"export_standalone.py"),"--model",str(model),
                "--base",str(BASE),"--no-install","--output",str(output)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn("READY STANDALONE",result.stdout)
            self.assertIn(hashlib.sha256(model.read_bytes()).hexdigest(),output.read_text(encoding="utf-8"))
            self.assertNotIn("-- MODEL_",output.read_text(encoding="utf-8"))
            self.assertIn("Generated LOCAL model",output.read_text(encoding="utf-8"))


if __name__=="__main__": unittest.main()
