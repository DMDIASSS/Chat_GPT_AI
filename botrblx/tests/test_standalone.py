"""Numerical and control-lifecycle checks for the actual standalone Lua runtime."""
import copy
import hashlib
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
                    p["other_cars"]=[dict(p["car"],position=rng.uniform(-3000,3000,3).tolist(),
                        team=i%2,boost_estimate=i*20,ground_estimate=bool(i%2),flip_estimate=bool(i%3))
                        for i in range(5)]
                    p["boost_pads"]=[dict(position=[111,222,73],active=True,is_big=True)]
                    q,kv,mask=bridge.observations(p,previous,not ground)
                    cases.append(dict(packet=p,previous=previous.tolist(),flip=not ground,
                                      q=q[0,0].tolist(),kv=kv[0,mask[0]==0].tolist()))
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

    def test_jump_axes_match_numeric_reference_from_game_control_mapper(self):
        cases=json.loads((HERE/'fixtures/jump_reference.json').read_text())['cases']
        self.assertEqual(len(cases),36)
        source=self.module+'\nlocal cases='+export.literal(cases)+'''
for _,case in ipairs(cases)do
 local keys,a=Policy.keys(case.action,case.ground)
 for key in pairs(case.keys)do assert(keys[key])end
 for key in pairs(keys)do assert(case.keys[key])end
 local n=case.native_axes
 assert(a[2]==n[1]and a[4]==n[2]and a[3]==n[3]and a[5]==n[4],'Jump axes differ from game controls')
 assert(a[3]==case.action[3]and a[4]+a[5]==case.action[4]+case.action[5],'Requested flip direction changed')
end
'''
        self.run_lua(source)

    def client_case(self,behaviour,checks,extra="",source=None):
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
        wrapped="\nlocal function boot()\n"+(source or self.source)+"\nend\nlocal result=boot()\n"
        return self.run_lua(prefix+extra+wrapped+behaviour+checks)

    def test_standalone_owns_inputs_f8_focus_and_close(self):
        self.client_case('''
assert(result.version=='local-6.7')
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

    def test_window_drag_minimize_and_calibration_pause(self):
        self.client_case('''
local function find(name)
 for _,o in ipairs(created)do if o.Name==name then return o end end
end
local panel,header,body=find('Window'),find('Titlebar'),find('Body')
local press={UserInputType=Enum.UserInputType.MouseButton1,Position=Vector3.new(20,20,0)}
header.InputBegan:Fire(press)
services.UserInputService.InputChanged:Fire({UserInputType=Enum.UserInputType.MouseMovement,Position=Vector3.new(100,70,0)})
assert(panel.Position.X.Offset==100 and panel.Position.Y.Offset==70,'Window did not move')
services.UserInputService.InputEnded:Fire(press)
inputKey('F4');assert(not body.Visible and panel.Size.Y.Offset==34)
inputKey('F4');assert(body.Visible and panel.Size.Y.Offset==372)
click('Calibration / physics test');inputKey('F6')
for i=1,15 do move(.02)end
assert(#emissions==0,'F6 started bot during calibration')
local view=find('Calibration');assert(view.Visible)
click('Motion / physics test');click('Record 20 seconds')
for i=1,20 do move(.02)end
inputKey('F10') -- finish the current recording
click('Save test file')
assert(savedName=='TurboBall_Calibration.json'and encoded[savedBody].motion.samples[1],'Motion test did not save poses')
click('Close test');click('Goal safety: ON')
assert(not view.Visible)
''',"click('Close')",extra='''
local savedName,savedBody
writefile=function(name,body)savedName,savedBody=name,body end
''')

    def test_incident_hotkey_retains_recent_driving_window(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,100 do move(.02)end
inputKey('F9');inputKey('F8')
for i=1,120 do move(.02)end
click('Save physics report')
assert(saved.incidents and #saved.incidents==1 and #saved.incidents[1].trace>0,'Lost marked incident')
assert(saved.goal_safety_enabled and saved.calibration.active==nil)
''',"click('Close')",extra='''
local saved
writefile=function(_,body)saved=encoded[body]end
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

    def test_rendered_opponent_reaches_live_policy_and_panel_then_is_removed(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,40 do move(1/30)end
local function panelHas(text)
 for _,o in ipairs(created)do if o.Text and string.find(o.Text,text,1,true)then return true end end
 return false
end
assert(panelHas('Opponents 1 | teammates 0'),'Live policy omitted rendered opponent')
plate.BackgroundColor3={R=46/255,G=120/255,B=226/255}
for i=1,15 do move(1/30)end
assert(panelHas('Opponents 0 | teammates 1'),'Team change did not update observation')
enemy.Parent=nil
for i=1,15 do move(1/30)end
assert(panelHas('Opponents 0 | teammates 0'),'Removed car remained in live observation')
''',"click('Close')",extra='''
local enemy=object('Model','Enemy');enemy.Parent=scene
local root=object('Part','Root');root.Parent=enemy;root.CFrame=frame(50);root.Position=root.CFrame.Position
enemy.PrimaryPart=root
local tag=object('BillboardGui','Nametag');tag.Parent=root;tag.Enabled=true
local plate=object('Frame','Plate');plate.Parent=tag;plate.BackgroundColor3={R=232/255,G=116/255,B=38/255}
''')

    def test_live_auto_team_two_v_two_and_midgame_side_switch(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,40 do move(1/30)end
local function has(text)
 for _,o in ipairs(created)do if o.Text and string.find(o.Text,text,1,true)then return true end end
 return false
end
assert(has('AUTO ORANGE')and has('Opponents 2 | teammates 1'),'Orange 2v2 observation is wrong')
edgePaint.BackgroundColor3={R=30/255,G=155/255,B=240/255}
friendPlate.BackgroundColor3={R=46/255,G=120/255,B=226/255}
enemyPlate1.BackgroundColor3={R=232/255,G=116/255,B=38/255}
enemyPlate2.BackgroundColor3=enemyPlate1.BackgroundColor3
for i=1,30 do move(1/30)end
assert(has('AUTO BLUE')and has('Opponents 2 | teammates 1'),'Side switch retained old team')
inputKey('F8')
local down={}
for _,e in ipairs(emissions)do if e[1]=='down'then down[e[2]]=true else down[e[2]]=nil end end
assert(next(down)==nil,'Side-switch inputs were not released by F8')
''',"click('Close')",extra='''
local sheet=object('ScreenGui','CarSoccerMatchSheet');sheet.Parent=playerGui
local row=object('Frame','Row1');row.Parent=sheet
local face=object('Frame','Face');face.Parent=row
local edge=object('Frame','TeamEdge');edge.Parent=face;edge.BackgroundTransparency=1
local edgePaint=object('Frame','Paint');edgePaint.Parent=edge;edgePaint.BackgroundColor3={R=252/255,G=122/255,B=2/255}
local me=object('TextLabel','Name');me.Parent=face;me.Text='Deadline_coolgun'
local function remote(name,team,x,friend)
 local model=object('Model',name);model.Parent=scene
 local root=object('Part','Root');root.Parent=model;root.CFrame=frame(x);root.Position=root.CFrame.Position;model.PrimaryPart=root
 local tag=object('BillboardGui','Nametag');tag.Parent=root;tag.Enabled=true
 local plate=object('Frame','Plate');plate.Parent=tag
 plate.BackgroundColor3=team==0 and {R=46/255,G=120/255,B=226/255}or{R=232/255,G=116/255,B=38/255}
 plate.Size={Y={Scale=friend and .74 or 1}}
 if friend then
  local bar=object('Frame','Boost');bar.Parent=tag
  local fill=object('Frame','Fill');fill.Parent=bar;fill.Size={X={Scale=.3}}
 end
 return plate
end
local friendPlate=remote('Friend',1,20,true)
local enemyPlate1=remote('Enemy1',0,40,false)
local enemyPlate2=remote('Enemy2',0,60,false)
''')

    def test_f8_stops_and_releases_during_scripted_kickoff(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,35 do move(1/30)end
local found=false
for _,o in ipairs(created)do if o.Text and string.find(o.Text,'kickoff:',1,true)then found=true end end
assert(found,'Scripted kickoff did not take control')
local down={}
for _,e in ipairs(emissions)do if e[1]=='down'then down[e[2]]=true else down[e[2]]=nil end end
assert(down[0x57]and down.LMB,'Kickoff did not use verified W and boost')
inputKey('F8');local n=#emissions
for i=1,10 do move(1/30)end
assert(#emissions==n,'Kickoff continued after F8')
''','''
local down={}
for _,e in ipairs(emissions)do if e[1]=='down'then down[e[2]]=true else down[e[2]]=nil end end
assert(next(down)==nil,'Kickoff inputs remained held')
click('Close')
''',extra='''
local function kickoffFrame(x,y,z)
 local f=frame(x);f.Position=Vector3.new(x,z,y);f.LookVector=Vector3.new(0,0,1)
 f.ToObjectSpace=function()return {ToAxisAngle=function()return Vector3.new(0,1,0),0 end}end
 return f
end
move=function(dt)
 now=now+dt
 carRoot.CFrame=kickoffFrame(0,-460.8,1.7);carRoot.Position=carRoot.CFrame.Position
 ballRoot.CFrame=kickoffFrame(0,0,9.315);ballRoot.Position=ballRoot.CFrame.Position
 carAnchor.Position=carRoot.Position;ballAnchor.Position=ballRoot.Position
 beat:Fire()
end
task.wait=function(dt)move(dt)end
''')

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

    def test_physics_assist_toggle_and_manual_report_export_release_inputs(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,45 do move(1/30)end
inputKey('F8')
click('Physics assist: ON')
inputKey('F6');for i=1,30 do move(1/30)end
inputKey('F8');click('Save physics report')
assert(savedName=='TurboBall_Physics_Report.json' and savedReport,'Report was not written')
local report=encoded[savedReport]
assert(report.version=='local-6.7' and report.physics_assist_enabled==false)
assert(report.place==101880234193261 and #report.model_sha256==64)
assert(report.saved_from.enabled==false and report.saved_from.last_stop_reason=='STOPPED by F8. F6 starts again.')
assert(#report.trace>0 and #report.trace<=150 and report.profile=='turbo_soccer_standard')
assert(not report.account and not report.tensors,'Private identity/weights entered report')
click('Physics assist: OFF')
local held={}
for _,e in ipairs(emissions)do if e[1]=='down'then held[e[2]]=true else held[e[2]]=nil end end
assert(next(held)==nil,'Report/toggle left inputs down')
''',"click('Close')",extra='''
local savedName,savedReport
writefile=function(name,body)savedName,savedReport=name,body end
''')

    def test_runtime_error_is_saved_with_stage_and_inputs_released(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,45 do move(1/30)end
breakPose=true
for i=1,5 do move(1/30)end
local report=saved['TurboBall_Last_Error.json']
assert(report and report.last_error.stage=='reading poses','Error stage was not captured')
assert(errorWrites==1,'Paused sampling repeatedly overwrote the original error file')
assert(string.find(report.last_error.reason,'fixture pose failure',1,true),'Original error lost')
assert(report.saved_from.enabled and not report.runtime.enabled,'Error report did not distinguish running/stopped')
assert(#report.runtime.held_inputs==0,'Error report captured held bot inputs')
click('Save physics report')
local manual=saved['TurboBall_Physics_Report.json']
assert(manual.last_error.reason==report.last_error.reason,'Manual save erased the original error')
local held={}
for _,e in ipairs(emissions)do if e[1]=='down'then held[e[2]]=true else held[e[2]]=nil end end
assert(next(held)==nil,'Runtime error left inputs pressed')
''',"click('Close')",extra='''
local saved={};local errorWrites=0
writefile=function(name,body)
 saved[name]=encoded[body]
 if name=='TurboBall_Last_Error.json'then errorWrites=errorWrites+1 end
end
local breakPose=false
local originalFrame=frame
frame=function(x)
 local f=originalFrame(x)
 if breakPose then f.ToObjectSpace=function()error('fixture pose failure')end end
 return f
end
''')

    def test_actual_pose_reader_finds_pads_in_local_match_view(self):
        self.client_case('''
for i=1,12 do move(1/30)end
click('Save physics report')
local t=savedReport.latest_pose
assert(t.pads_total==1 and t.pads_known==1 and t.pad_folder_found,'Local nested pads were omitted')
assert(t.boost_pads[1].active and t.boost_pads[1].position[1]==400)
assert(t.hitbox_probe.selection_boxes==0,'Hitbox probe omitted missing renderer markers')
assert(#savedReport.trace==0,'Paused poses replaced active-run history')
''',"click('Close')",extra='''
local savedReport
writefile=function(_,body)savedReport=encoded[body]end
local view=object('Folder','MatchView');view.Parent=scene
car.Parent=view;ball.Parent=view
local decoy=object('Folder','BoostPads');decoy.Parent=scene
local folder=object('Folder','BoostPads');folder.Parent=view
local halo=object('Part','PadHalo');halo.Parent=folder;halo.Position=Vector3.new(40,.48,12)
for i=1,10 do
 local ring=object('Part','PadRing');ring.Parent=folder
 ring.Position=Vector3.new(40+math.cos(i*2*math.pi/10)*7,.53,12+math.sin(i*2*math.pi/10)*7)
 ring.Transparency=0;ring.Color={R=1,G=.83,B=.19}
 folder.children['ring'..i]=ring
end
folder.children.PadRing=nil
''')

    def test_custom_coordinate_scale_is_used_by_actual_shared_pose_reader(self):
        # The geometry reader already honored profile scale, but the shared pose
        # reader previously multiplied by 10 regardless of the chosen profile.
        source=(APP/"client271.lua").read_text().split("-- POSE_READER_BEGIN",1)[1].partition("\n")[2].split("-- POSE_READER_END",1)[0]
        prefix=(HERE/"fixtures/roblox_mock.luau").read_text()
        self.run_lua(prefix+'''
local arenaAdapter={profile={roblox_studs_per_sim_unit=.2}}
'''+source+'''
local p=pose(frame(12),frame(10),.1)
assert(p.position[1]==60 and p.position[3]==10)
assert(p.velocity[1]==100,'Pose velocity used a hardcoded coordinate scale')
arenaAdapter=nil
p=pose(frame(12),frame(10),.1)
assert(p.position[1]==120 and p.velocity[1]==200,'Legacy bridge scale changed')
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

    def test_nexto_preset_selects_original_asset_and_rejects_custom_checkpoint(self):
        with tempfile.TemporaryDirectory()as directory:
            output=Path(directory)/'nexto.lua'
            args=[sys.executable,str(APP/'export_standalone.py'),'--project-root',str(APP.parent),
                  '--preset','nexto','--no-install','--output',str(output)]
            result=subprocess.run(args,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            source=output.read_text()
            self.assertIn('local MODEL_NAME="Nexto"',source)
            self.assertIn('local physicsEnabled=false',source)
            self.assertIn(export.NEXTO_SHA256,source)
            result=subprocess.run(args+['--model',str(BASE)],capture_output=True,text=True,timeout=30)
            self.assertNotEqual(result.returncode,0,'Nexto preset accepted an arbitrary model override')
            private=Path(directory)/'private.pt';private.write_bytes(b'private-checkpoint')
            rejected=Path(directory)/'must-not-publish.lua'
            result=subprocess.run([sys.executable,str(APP/'build_nexto.py'),'--asset',str(private),
                '--output',str(rejected)],capture_output=True,text=True,timeout=30)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(rejected.exists(),'Public build accepted an unverified checkpoint')

    def test_ready_nexto_runtime_keeps_cadence_and_active_trace_after_pause(self):
        from build_nexto import NOTICE
        expected=NOTICE+export.standalone_source(self.model,export.NEXTO_SHA256,model_name='Nexto',physics_assist=False)
        artifact=APP/'TurboBall_Nexto.lua'
        if not artifact.is_file():artifact=APP.parent/'downloads/TurboBall_Nexto.lua'
        source=artifact.read_text()
        self.assertEqual(source,expected,'Rebuild the public Nexto artifact after runtime changes')
        self.client_case('''
move(.05);inputKey('F6')
for i=1,220 do move(.02)end
inputKey('F4');for i=1,20 do move(.02)end;inputKey('F4')
inputKey('F8');click('Save physics report')
local before=saved
assert(before.model_name=='Nexto'and before.model_sha256=='bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa')
assert(not before.physics_assist_enabled and not before.teammate_yield_enabled,'Nexto default contains scripted yielding')
assert(before.performance.decision_hz>14 and before.performance.decision_hz<16,'Runtime scheduling fell below cadence')
assert(before.performance.model_calls>0 and #before.trace>0)
local lastAt=before.trace[#before.trace].time
for i=1,260 do move(.02)end
click('Save physics report')
assert(saved.trace[#saved.trace].time==lastAt and saved.performance.samples==before.performance.samples,'Pause overwrote active diagnostics')
assert(saved.performance.last_active_age>5)
click('Yield to teammate: OFF');click('Save physics report')
assert(saved.teammate_yield_enabled,'Optional teammate switch did not update')
''',"click('Close')",extra='''
local saved
writefile=function(_,body)saved=encoded[body]end
''',source=source)

    def test_far_ground_override_skips_inference_in_actual_worker(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,20 do move(1/30)end
inputKey('F8');click('Save physics report')
assert(saved.performance.samples>0,'No ground decisions produced')
assert(saved.performance.model_calls==0,'Computed a model result discarded by far ground assist')
assert(saved.trace[#saved.trace].decision.mode~='model','Did not test a ground override')
''',"click('Close')",extra='''
local saved
writefile=function(_,body)saved=encoded[body]end
local originalFrame=frame
frame=function(x)
 local out=originalFrame(x)
 if x>4 then out.Position=Vector3.new(out.Position.X+200,out.Position.Y,out.Position.Z)end
 return out
end
''')

    def flip_source(self):
        return self.source.replace('local index=predict(query,entities)','local index=forcedIndex')

    def flip_setup(self,delay):
        actions=bridge.lookup_table()
        ground=next(i+1 for i,a in enumerate(actions)if a.tolist()==[1,1,0,1,0,0,0,0])
        back=next(i+1 for i,a in enumerate(actions)if a.tolist()==[0,0,1,0,0,1,0,1])
        return f'local forcedIndex={ground};local backIndex={back}\n'+'''
local delayLive=false
local queued={};local jumpCount=0;local saved
local originalMove=move
move=function(dt)
 for i=#queued,1,-1 do
  if queued[i].at<=now+dt then physicalDown[queued[i].key]=queued[i].down or nil;table.remove(queued,i)end
 end
 originalMove(dt)
end
keypress=function(key)
 local name=virtualCodes[key]or key
 emit('down',key)
 if delayLive then
  if LIVE_DELAY>=0 then queued[#queued+1]={at=now+LIVE_DELAY,key=name,down=true}end
 else physicalDown[name]=true end
end
keyrelease=function(key)
 local name=virtualCodes[key]or key
 emit('up',key)
 if delayLive and LIVE_DELAY>=0 then queued[#queued+1]={at=now+LIVE_DELAY,key=name,down=false}
 else physicalDown[name]=nil end
end
mouse2press=function()
 jumpCount+=1
 assert(physicalDown.S and not physicalDown.W,'Jump arrived without backflip pitch')
 assert(not physicalDown.D and not physicalDown.A and not physicalDown.Q and not physicalDown.E and not physicalDown.LeftShift,'Jump arrived with stale sideways input')
 emit('down','RMB')
end
writefile=function(_,body)saved=encoded[body]end
'''.replace('LIVE_DELAY',str(delay))

    def test_backflip_waits_for_queued_direction_release_and_press(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,20 do move(.02)end
assert(physicalDown.D,'Test did not establish the previous steering input')
forcedIndex=backIndex;delayLive=true
for i=1,12 do move(.02)end
assert(jumpCount==1,'Deferred jump was lost or repeated')
inputKey('F8');click('Save physics report')
local jump=saved.jump_events[#saved.jump_events]
assert(jump.requested[3]==1 and jump.mapped[3]==1 and jump.mapped[4]+jump.mapped[5]==0)
assert(jump.wait_ms>0 and jump.wait_ms<150)
''',"click('Close')",extra=self.flip_setup(.04),source=self.flip_source())

    def test_f8_cancels_queued_jump_before_axis_acknowledgment(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,20 do move(.02)end
forcedIndex=backIndex;delayLive=true
for i=1,4 do move(.02)end
assert(jumpCount==0)
inputKey('F8');for i=1,20 do move(.02)end
assert(jumpCount==0,'Pending jump fired after F8')
''',"click('Close')",extra=self.flip_setup(.1),source=self.flip_source())

    def test_lost_direction_acknowledgment_stops_before_wrong_flip(self):
        self.client_case('''
move(.05);inputKey('F6');for i=1,20 do move(.02)end
forcedIndex=backIndex;delayLive=true
for i=1,20 do move(.02)end
assert(jumpCount==0,'Jump fired with missing direction keys')
assert(saved and saved.last_error and saved.last_error.stage=='waiting for jump direction keys')
assert(string.find(saved.last_error.reason,'Jump direction did not reach Roblox',1,true))
''',"click('Close')",extra=self.flip_setup(-1),source=self.flip_source())


if __name__=="__main__": unittest.main()
