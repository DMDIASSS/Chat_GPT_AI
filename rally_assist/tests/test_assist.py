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
assert(c.prediction and c.predictedViolation>0,'Missing unsafe trajectory prediction')
state.obstacle=3;state.vz=0
for i=1,100 do c=Driver.step(driver,base,base,stage,state,cfg,1/30,1+i/30)end
assert(c.Throttle==0 and c.Brake==1 and c.mode=='Obstacle: emergency braking','Did not stop for a close obstruction')
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

    def test_predictive_search_full_throttle_and_room_to_avoid_obstacle(self):
        self.run_lua('''
local stage={Id='test',Origin={0,0,0},Heading=0,Width=24,StartAt=5,FinishAt=450,StopAt=490,
 Surface='Gravel',segments={{Straight=500}},features={}}
local base=Route.fromStage(stage)
local s={x=0,y=2,z=-30,vx=0,vz=-25,fx=0,fz=-1,yawRate=0,grounded=4,upY=1,
 wheelbase=8,halfWidth=2.8,halfLength=5,cgHeight=2.2,gravity=75,grip=42,braking=39,maxAngle=25,runState='Running'}
local cfg={maxKmh=180,margin=1.2,brake=1.5}
local d=Driver.new();local c
for i=1,12 do c=Driver.step(d,base,base,stage,s,cfg,1/30,i/30)end
assert(c.Throttle>.95 and c.Brake==0,'Did not use full throttle on clear straight')
assert(c.prediction and #c.prediction==6 and c.predictedViolation<.1)
s.obstacles={{x=0,z=-72,radius=1}}
d=Driver.new()
c=Driver.step(d,base,base,stage,s,cfg,1/30,1)
assert(math.abs(c.Steer)>.01 or c.Brake>0,'Ignored obstacle in predicted path')
assert(c.predictedViolation<.2,'Failed to find a collision-free alternative with room available')
''',modules=(("Route","route.lua"),("Driver","controller.lua")))

    def test_corridor_uses_rotated_full_car_and_assist_returns_inward(self):
        self.run_lua('''
local stage={Id='test',Origin={0,0,0},Heading=0,Width=18,StartAt=5,FinishAt=450,StopAt=490,
 Surface='Gravel',segments={{Straight=500}},features={}}
local base=Route.fromStage(stage)
local s={x=4,y=2,z=-50,vx=5,vz=-35,fx=0,fz=-1,yawRate=0,grounded=4,upY=1,halfWidth=2.8,halfLength=5,grip=42}
local tangent=base:at(50)
assert(math.abs(Driver.envelope(s,tangent,1.2)-4)<.01)
s.fx=1;s.fz=0
assert(math.abs(Driver.envelope(s,tangent,1.2)-6.2)<.01,'Ignored car length when sideways')
s.fx=0;s.fz=-1
local g=Driver.assist(base,stage,s,{margin=1.2})
assert(g.risk and g.lateralAccel<0 and g.Brake>0,'No inward correction before road exit')
s.x=0;s.vx=0
g=Driver.assist(base,stage,s,{margin=1.2})
assert(not g.risk and g.lateralAccel==0,'Rail-locked a car safely inside the corridor')
''',modules=(("Route","route.lua"),("Driver","controller.lua")))

    def test_fallback_grip_is_not_inflated_and_brake_multiplier_applies(self):
        self.run_lua('''
local car,root=spawnCar()
local adapter=Adapter.new(player,World,services.ReplicatedStorage,{})
adapter:find();local cfg={speed=1,turn=1,grip=3,brake=3,roadAssist=true,maxKmh=180}
adapter:tune(cfg,true)
local state=adapter:measure()
assert(state.grip==42,'Pretended slip damping tripled tyre grip')
assert(state.braking==78 and state.maxAngle<28,'Fallback braking/steering estimates wrong')
local guard={rightX=1,rightZ=0,lateralAccel=0,yawAccel=0,Brake=0}
local before=math.abs(root.AssemblyLinearVelocity.Z)
adapter:stabilize(state,cfg,guard,{Brake=1},1/60)
assert(math.abs(root.AssemblyLinearVelocity.Z)<before-.8,'Brake multiplier supplied no extra braking')
''',modules=(("Adapter","adapter.lua"),),fixture=True)

    def test_high_grip_does_not_remove_rollover_steering_limit(self):
        self.run_lua('''
local s={wheelbase=8.3,halfWidth=2.8,cgHeight=3.2,gravity=75,grip=500}
local angle=math.rad(28)
local limit=Driver.steerLimit(s,90,angle)
local lateral=90^2/s.wheelbase*math.tan(limit*angle)
assert(limit<.1,'High grip removed rollover protection')
assert(lateral<=75*2.8/3.2*.6+.01,'Steering exceeded conservative rollover acceleration')
assert(Driver.steerLimit(s,8,angle)>limit,'Low-speed steering unnecessarily restricted')
''',modules=(("Driver","controller.lua"),))

    def test_upright_damping_toggle_and_no_position_writes(self):
        self.run_lua('''
local car,root=spawnCar()
local adapter=Adapter.new(player,World,services.ReplicatedStorage,{})
adapter:find();root.CFrame.UpVector=Vector3.new(.6,.8,0)
local s=adapter:measure();local pos=root.Position
local g={rightX=1,rightZ=0,lateralAccel=0,yawAccel=0,Brake=0}
adapter:stabilize(s,{roadAssist=false,brake=1},g,{Brake=0},1/60)
assert(root.AssemblyAngularVelocity.Magnitude==0,'Disabled stabilizer applied torque')
adapter:stabilize(s,{roadAssist=true,brake=1},g,{Brake=0},1/60)
assert(root.AssemblyAngularVelocity.Z>0,'Torque moved tilt away from upright')
assert(root.Position==pos and not root.pivots,'Stability teleported the car')
''',modules=(("Adapter","adapter.lua"),),fixture=True)

    def test_keyboard_pedals_preserve_partial_command_average(self):
        self.run_lua('''
local driver=Input.new(input)
assert(driver:probe(function()return false end,function()end))
local count=0
for i=1,120 do
 assert(driver:write({Throttle=.25,Brake=0,Steer=0,Handbrake=false}))
 if input.held.W then count+=1 end
 now+=1/60
end
assert(count==30,'Quarter throttle became permanently held W')
driver:release()
''',modules=(("Input","input.lua"),),fixture=True)

    def test_small_keyboard_steering_survives_faster_return_ramp(self):
        self.run_lua('''
local driver=Input.new(input)
assert(driver:probe(function()return false end,function()end))
driver.steerRate=4.8;driver.returnRate=7
for _,hz in ipairs({30,60,120})do for _,desired in ipairs({.02,.12,-.12,.65})do
 driver:release();local actual,total=0,0
 for i=1,hz*6 do
  driver:write({Throttle=0,Brake=0,Steer=desired,Handbrake=false})
  local target=(input.held.D and 1 or 0)-(input.held.A and 1 or 0)
  local rate=(target==0 or math.sign(target)~=math.sign(actual))and 7 or 4.8
  actual=actual+math.clamp(target-actual,-rate/hz,rate/hz)
  if i>hz then total+=actual end
  now+=1/hz
 end
 assert(math.abs(total/(hz*5)-desired)<.025,'Digital steering lost desired average: '..total/(hz*5)..' vs '..desired)
end
end
driver:release();assert(next(input.held)==nil)
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
 assert(s==500 and body==chassis and finish and plan.GripUse==.76)
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
local cfg={speed=2,turn=1.5,grip=2,brake=2.5,roadAssist=true}
assert(adapter:tune(cfg,true))
assert(chassis.Tune~=original and original.Engine.Force==2 and original.Gears.Ratios[1]==17)
assert(chassis.Tune.Brakes.Force==110 and original.Brakes.Force==44,'Native brake multiplier changed its baseline')
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

    def test_gui_road_toggle_and_brake_control(self):
        self.client('''
local car,root=spawnCar()
for i=1,4 do step()end
findCreated('Master').Activated:Fire();step()
assert(app.enabled and app.cfg.roadAssist)
findCreated('RoadAssist').Activated:Fire();step()
assert(not app.cfg.roadAssist and app.enabled,'Road toggle disabled unrelated boosts')
input.InputBegan:Fire({KeyCode=Enum.KeyCode.F9},false);step()
assert(app.cfg.roadAssist,'F9 did not restore road assist')
local box=findCreated('Window'):FindFirstChild('Body'):FindFirstChild('brake'):FindFirstChild('Value')
box.Text='2.5';box.FocusLost:Fire();step()
assert(app.cfg.brake==2.5 and app.state.brakeForce==65,'Brake field did not update the handling model')
app.destroy()
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
assert(app.command and app.command.Throttle==0 and app.command.Handbrake and not input.held.S)
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
