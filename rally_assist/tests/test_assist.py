"""Independent controller, input ownership, UI lifecycle and numeric place checks."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("rally_build",ROOT/"build.py")
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
LUAU=os.environ.get("LUAU_BIN")or shutil.which("luau")or "/tmp/roworld-luau-source/luau"
COMPILER=os.environ.get("LUAU_COMPILE")or "/tmp/roworld-luau-source/luau-compile"


class AssistTests(unittest.TestCase):
    def run_lua(self,body,modules=(),fixture=False,timeout=30):
        source=(ROOT/"tests/roblox_fixture.lua").read_text()if fixture else ""
        for name,file in modules:
            source+="\nlocal "+name+"=(function()\n"+(ROOT/file).read_text()+"\nend)()\n"
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/"test.luau";path.write_text(source+body)
            result=subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=timeout)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return result.stdout

    def test_generated_source_compiles_and_contains_no_network_writes_or_teleports(self):
        source=build.source()
        self.assertEqual(source,(ROOT/"Backseat_Rally_Assist.lua").read_text())
        for text in (":FireServer(",":InvokeServer(","setthreadidentity","getgc(","HttpGet(",":PivotTo(","root.CFrame=",":Kick("):
            self.assertNotIn(text,source)
        result=subprocess.run([COMPILER,str(ROOT/"Backseat_Rally_Assist.lua")],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_all_stage_lines_and_showcase_references_are_finite(self):
        stages=json.loads((ROOT/"stage_profiles.json").read_text())
        reels=json.loads((ROOT/"showcase_lines.json").read_text())
        self.assertEqual(set(stages),set(reels));self.assertEqual(len(stages),7)
        self.run_lua("local stages="+build.literal(stages)+"\nlocal reels="+build.literal(reels)+'''
for id,stage in pairs(stages)do
 local base=Route.fromStage(stage)
 assert(base.length>stage.StopAt-10 and base.length<30000,id..' length')
 local line=Route.fromShowcase(reels[id].samples,{source='showcase'})
 assert(line.length>stage.FinishAt-stage.StartAt-250,id..' incomplete showcase')
 for _,p in ipairs(base.points)do assert(p.y==p.y and math.abs(p.y)<1000,id..' malformed height')end
 local row=reels[id].samples[math.floor(#reels[id].samples/2)]
 local n=line:nearest({x=row[2],y=row[3],z=row[4]})
 assert(n.distance<.16,id..' nearest projection')
end
''',modules=(("Route","route.lua"),))

    def test_stage_height_and_position_agree_with_saved_collision_road(self):
        stage=json.loads((ROOT/"stage_profiles.json").read_text())["PineForest"]
        cases=json.loads((ROOT/"tests/collision_reference.json").read_text())["cases"]
        self.run_lua("local stage="+build.literal(stage)+"\nlocal cases="+build.literal(cases)+'''
local route=Route.fromStage(stage)
for _,case in ipairs(cases)do
 local p=case.position
 local n=route:nearest({x=p[1],y=case.road_height,z=p[3]})
 assert(n.distance<2.5,'Collision road center differs')
 assert(math.abs(n.y-case.road_height)<.15,'Elevation differs from actual saved collision: '..n.y..' vs '..case.road_height)
end
''',modules=(("Route","route.lua"),))

    def test_preview_brakes_before_a_hairpin_and_respects_lane_margin(self):
        self.run_lua('''
local stage={Id='test',Origin={0,0,0},Heading=0,Width=18,StartAt=5,FinishAt=240,StopAt=260,Surface='Gravel',
 segments={{Straight=100},{Turn='Right',Radius=26,Angle=165},{Straight=100}},
 features={{Kind='Hazard',At=102,Side='Left'}}}
local base=Route.fromStage(stage)
assert(base:targetSpeed(75,150,40,25,1)<50,'Did not brake before hairpin')
local cfg={maxKmh=180,pace=1}
local state={x=4,y=2,z=-75,vx=0,vz=-90,fx=0,fz=-1,yawRate=0,grounded=4,upY=1,
 wheelbase=7.5,halfWidth=2.5,grip=40,braking=26,maxAngle=28,runState='Running'}
local driver=Driver.new();local c=Driver.step(driver,base,base,stage,state,cfg,1/30,1)
assert(c.Brake>0 and c.Throttle==0,'Failed to brake for a slower corner')
assert(math.abs(base:nearest(c.target).lateral)<=5.6,'Hazard offset left the safe lane')
state.obstacle=3;state.vz=0
for i=1,100 do c=Driver.step(driver,base,base,stage,state,cfg,1/30,1+i/30)end
assert(driver.recoveryCooldown and driver.recoveryCooldown>0,'No bounded obstruction recovery')
state.runState='Countdown';c=Driver.step(driver,base,base,stage,state,cfg,1/30,6)
assert(c.Brake==1 and c.Throttle==0 and c.mode=='Countdown')
state.runState='Finished';c=Driver.step(driver,base,base,stage,state,cfg,1/30,7)
assert(c.mode=='Stage complete' and c.Brake==1)
''',modules=(("Route","route.lua"),("Driver","controller.lua")))

    def test_ghost_decoder_matches_binary_format_and_rejects_resets(self):
        raw=bytearray(60)
        for i in range(2):
            off=i*30;struct.pack_into('<3f',raw,off,1+i,62,-30-i*3)
            struct.pack_into('<hh',raw,off+20,2500,-2000)
        payload={"Data":base64.b64encode(raw).decode(),"Count":2,"Rate":20}
        raw[25]=64
        bad=dict(payload,Data=base64.b64encode(raw).decode())
        self.run_lua("local payload="+build.literal(payload)+"\nlocal bad="+build.literal(bad)+'''
local rows=Ghost.decode(payload)
assert(#rows==2 and rows[2][1]==.05 and rows[2][2]==2 and rows[1][5]==50 and rows[1][6]==-.2)
assert(not pcall(Ghost.decode,bad),'Accepted a teleport/reset in replay')
payload.Count=999999;assert(not pcall(Ghost.decode,payload),'Accepted unbounded sample allocation')
local g=Ghost.new()
for i=1,50 do g:sample('PineForest','Hatch','Running',{x=0,y=62,z=-i,speed=0},i*.1)end
g:sample('PineForest','Hatch','Finished',{x=0,y=62,z=-50},5.1)
assert(g.tracks['PineForest/Hatch'])
assert(g.tracks['PineForest/Hatch'].samples[5][5]>1,'Rendered ghost motion was treated as stationary')
local late=Ghost.new()
for i=1,50 do late:sample('PineForest','Hatch','Running',{x=0,y=62,z=-i,elapsed=10+i*.1},i*.1)end
late:sample('PineForest','Hatch','Finished',{},5.1)
assert(not late.tracks['PineForest/Hatch'],'Accepted capture started halfway through a run')
''',modules=(("Ghost","ghost.lua"),))

    def test_keyboard_fallback_verifies_observable_input_and_releases(self):
        self.run_lua('''
local inputAdapter=Input.new(input)
assert(inputAdapter:probe(function()return false end,function()end))
assert(inputAdapter.name=='executor VK')
assert(inputAdapter:write({Throttle=1,Brake=0,Steer=1,Handbrake=false}))
assert(input.held.W and input.held.D)
inputAdapter:release();assert(next(input.held)==nil)
local oldPress=keypress
keypress=function()end
inputAdapter=Input.new(input)
local ok=inputAdapter:probe(function()return false end,function()end)
assert(not ok,'No-op input API counted as working')
keypress=oldPress
''',modules=(("Input","input.lua"),),fixture=True)

    def test_late_executor_press_after_stop_is_released(self):
        self.run_lua('''
local driver=Input.new(input)
assert(driver:probe(function()return false end,function()end))
local send=driver.backend.send;local interrupted=false
driver.backend.send=function(key,down)
 if down and not interrupted then interrupted=true;driver:release()end
 send(key,down)
end
assert(not driver:write({Throttle=1,Brake=0,Steer=1,Handbrake=false}))
assert(interrupted and next(input.held)==nil,'Late key press remained held')
''',modules=(("Input","input.lua"),),fixture=True)

    def test_lost_keyboard_delivery_stops_and_requires_retest(self):
        self.run_lua('''
local driver=Input.new(input)
assert(driver:probe(function()return false end,function()end))
local command={Throttle=1,Brake=0,Steer=0,Handbrake=false}
assert(driver:write(command))
input.held.W=nil;now+=.3
local ok,reason=driver:write(command)
assert(not ok and reason:find('stopped reaching Roblox') and not driver.backend)
driver:release();assert(next(input.held)==nil)
''',modules=(("Input","input.lua"),),fixture=True)

    def test_unshared_module_reader_falls_back_to_verified_keys(self):
        self.run_lua('''
local driver=Input.new(input)
local original=function()return {Throttle=0,Brake=0,Steer=0}end
local module={Read=original}
assert(driver:attach(module))
assert(driver:probe(function()return false end,function()end))
assert(driver.name=='executor VK' and module.Read==original,'Accepted a reader the game never called')
driver:release();assert(next(input.held)==nil)
''',modules=(("Input","input.lua"),),fixture=True)

    def test_surface_wetness_and_native_braking_preview_reach_controller(self):
        self.run_lua('''
local car,root=spawnCar()
local cfg={Gravity=75,Engine={Force=2},Steering={Rate=4,ReturnRate=6,MaxAngle=34},
 Tyres={LateralGrip=.5,LongitudinalGrip=.6},Brakes={Force=44},Surfaces={Gravel={Lateral=.8}},WetGrip={Default=.5}}
local chassis={Body=root,Tune=cfg,State={Grounded=4,Surface='Gravel',Wetness=.5}}
local adapter=Adapter.new(player,World,services.ReplicatedStorage,{})
adapter:find();adapter.chassis=chassis;adapter.cfg={maxKmh=180}
adapter.nativeRoute={Get=function()return {Nearest=function()return 1,500 end}end}
adapter.nativePlan={Target=function(route,s,body,plan,finish)
 assert(s==500 and body==chassis and finish and plan.GripUse==.8)
 return 12
end}
local state=adapter:measure()
assert(math.abs(state.grip-22.5)<1e-6,'Wet/surface grip not reflected in planning')
assert(state.nativePreview==12,'Native future-surface preview omitted')
''',modules=(("Adapter","adapter.lua"),),fixture=True)

    def test_tune_multipliers_do_not_compound_and_restore_external_changes(self):
        self.run_lua('''
local car,root=spawnCar()
local original={Gravity=75,Engine={Force=2},Steering={Rate=4,ReturnRate=6,MaxAngle=34},
 Tyres={LateralGrip=.5,LongitudinalGrip=.6},Gears={Ratios={17,11,7}},Brakes={Force=44}}
local chassis={Body=root,Tune=original}
local adapter=Adapter.new(player,World,services.ReplicatedStorage,{})
adapter.root=root;adapter.controller={GetChassis=function()return chassis end}
local cfg={speed=2,turn=1.5,grip=2}
assert(adapter:tune(cfg,true))
assert(chassis.Tune~=original and original.Engine.Force==2 and original.Gears.Ratios[1]==17)
local applied=chassis.Tune
for i=1,20 do assert(adapter:tune(cfg,true));assert(chassis.Tune==applied)end
adapter:restore();assert(chassis.Tune==original)
adapter:tune(cfg,true)
local external={Engine={Force=4}};chassis.Tune=external
adapter:restore();assert(chassis.Tune==external,'Close overwrote an external tune change')
player:SetAttribute('ManualGears',true);adapter:automatic(true);assert(player:GetAttribute('ManualGears')==false)
adapter:automatic(false);assert(player:GetAttribute('ManualGears')==true)
''',modules=(("Adapter","adapter.lua"),),fixture=True)

    def client(self,body,extra=""):
        return self.run_lua(extra+"\nlocal function boot()\n"+build.source()+"\nend\nlocal app=boot()\n"+body,fixture=True)

    def test_gui_drag_minimize_close_and_manual_assist_restoration(self):
        self.client('''
local car,root=spawnCar()
for i=1,3 do step()end
assert(app.alive and not app.enabled and not app.lastError,app.lastError)
local window=findCreated('Window');local body=window:FindFirstChild('Body');local title=findCreated('Titlebar')
title.InputBegan:Fire({UserInputType=Enum.UserInputType.MouseButton1,Position=Vector3.new(30,30,0)})
input.InputChanged:Fire({UserInputType=Enum.UserInputType.MouseMovement,Position=Vector3.new(100,80,0)})
assert(window.Position.X.Offset==92 and window.Position.Y.Offset==74,'Window did not drag')
input.InputEnded:Fire({UserInputType=Enum.UserInputType.MouseButton1})
findCreated('Minimize').Activated:Fire();assert(not body.Visible and window.Size.Y.Offset==46)
findCreated('Minimize').Activated:Fire();assert(body.Visible and window.Size.Y.Offset==676)
findCreated('Master').Activated:Fire();input.held.W=true
local before=root.AssemblyLinearVelocity.Magnitude
step();assert(app.enabled and root.AssemblyLinearVelocity.Magnitude>before,'Manual speed assist did not apply')
input.held.W=nil
findCreated('Report').Activated:Fire();assert(savedFiles['BackseatRally_Report.json'])
findCreated('Close').Activated:Fire()
assert(not app.alive and not app.enabled and env.__BackseatRallyAssist==nil)
for _,c in ipairs(app.connections)do assert(not c.active,'Close left a connection active')end
''')

    def test_keyboard_autodrive_stops_for_f8_focus_countdown_and_co_driver(self):
        self.client('''
local car,root,seat=spawnCar()
root.AssemblyLinearVelocity=Vector3.zero
for i=1,3 do step()end
app.toggleAuto();for i=1,12 do step()end
assert(app.autoReady and app.command and not app.lastError,app.lastError or app.status)
assert(app.command.Throttle>0 and input.held.W,'Autodrive emitted no throttle')
input.InputBegan:Fire({KeyCode=Enum.KeyCode.F8},false)
assert(not app.enabled and next(input.held)==nil,'F8 left owned input down')
app.start();for i=1,12 do step()end
input.WindowFocusReleased:Fire()
assert(not app.enabled and next(input.held)==nil,'Focus loss did not release')
input.WindowFocused:Fire();car:SetAttribute('RunState','Countdown')
app.start();for i=1,10 do step()end
assert(app.command and app.command.Throttle==0 and app.command.Brake==1)
seat.Name='CoDriver';step()
assert(not app.autoReady and next(input.held)==nil,'Controlled the co-driver seat')
app.destroy()
''')

    def test_native_analog_route_and_reinjection_restore_only_our_bindings(self):
        extra='''
local car,root=spawnCar()
root.AssemblyLinearVelocity=Vector3.zero
local scripts=object('Folder',player,'PlayerScripts')
local client=object('LocalScript',scripts,'Client')
local init=object('Folder',client,'Init');local folder=object('Folder',init,'Car')
local controllerModule=object('ModuleScript',folder,'CarController')
local inputModule=object('ModuleScript',folder,'CarInput')
local base={Gravity=75,Engine={Force=2},Steering={Rate=4,ReturnRate=6,MaxAngle=34},
 Tyres={LateralGrip=.55,LongitudinalGrip=.6},Gears={Ratios={17,11,7}},Brakes={Force=44}}
local chassis={Body=root,Tune=base,State={Grounded=4,Surface='Gravel'},MaxAngleNow=28}
local originalRead=function()return {Throttle=0,Brake=0,Steer=0,Handbrake=false}end
local nativeInput={Read=originalRead}
moduleValues[controllerModule]={GetChassis=function()return chassis end}
moduleValues[inputModule]=nativeInput
local emitted
services.RunService.PreSimulation:Connect(function()emitted=nativeInput.Read()end)
'''
        body='''
for i=1,3 do step()end
app.toggleAuto();for i=1,10 do step()end
assert(app.input.name=='analog' and app.autoReady and emitted.Analog and emitted.Throttle>0)
assert(chassis.Tune~=base,'Native tune not applied')
assert(next(input.held)==nil,'Analog mode emitted keyboard presses')
local first=app
local function reboot()
'''+build.source()+'''
end
local second=reboot()
assert(second.alive and not first.alive,'Reinjection left old controller running')
assert(chassis.Tune==base,'Reinjection left modified tuning')
second.destroy();assert(nativeInput.Read==originalRead,'Close did not restore CarInput.Read')
'''
        self.client(body,extra)


if __name__=="__main__":unittest.main()
