"""Behavior checks against the shipped Luau sources, plus binary preservation.

The shared mock supplies API-shaped fixtures. It does not simulate Roblox rendering,
network transport, asset permissions, or the rigid-body engine.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
LUAU=Path(os.environ.get('LUAU_BIN','/workspace/work/dm/luau/luau'))
COMPILE=LUAU.with_name('luau-compile')
BASE=(REPO/'backseat_rally_game/tests/roblox_mock.luau').read_text()+'\n'+(ROOT/'tests/fixture.luau').read_text()
PATHS={p.stem:p for p in (ROOT/'src').rglob('*.lua')}


def program(body):
    setup=[BASE]
    for name,p in PATHS.items():
        path=list(p.relative_to(ROOT/'src').with_suffix('').parts)
        setup.append('do local n=node('+ '{'+','.join(json.dumps(v) for v in path)+'}' +'); modules[n]=function(script)\n'+p.read_text()+'\nend end')
    # Keep collision deformation outside the input/rack tests.
    setup.append("cache[node({'ReplicatedStorage','RallyShared','Physics','DeformationModel'})]={GetHandlingDegradation=function()return {SteeringBias=0,MaxSteerMultiplier=1,DampingMultiplier=1}end,ApplyImpact=function()end}")
    setup.append("local function load(name) local paths="+ '{'+','.join('['+json.dumps(n)+']={'+','.join(json.dumps(v) for v in p.relative_to(ROOT/'src').with_suffix('').parts)+'}' for n,p in PATHS.items()) +"};return require(node(paths[name]))end")
    setup.append(body)
    return '\n'.join(setup)


class RedoneBehavior(unittest.TestCase):
    def run_luau(self,body):
        with tempfile.NamedTemporaryFile(suffix='.luau',mode='w') as f:
            f.write(program(body));f.flush()
            result=subprocess.run([LUAU,f.name],capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_all_sources_compile(self):
        for p in PATHS.values():
            result=subprocess.run([COMPILE,p],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
            self.assertEqual(result.returncode,0,str(p)+result.stderr)

    def test_fixed_rate_and_reversal_at_four_frame_rates(self):
        self.run_luau('''
local Steering=load('Steering')
for _,car in pairs(load('CarProfiles').Cars)do
 for _,fps in ipairs({15,30,60,144})do
  local value=0
  for i=1,math.floor(fps*.25)do
   local nextValue=Steering.Step(value,1,1/fps,car.Steering,false)
   near((nextValue-value)*car.Steering.MaxAngle,60/fps);value=nextValue
  end
  local before=value
  value=Steering.Step(value,-1,1/fps,car.Steering,false)
  assert(value>0,'Reversing input reset the rack');near((before-value)*car.Steering.MaxAngle,60/fps)
  for i=1,fps*2 do value=Steering.Step(value,-1,1/fps,car.Steering,false)end
  near(value,-1)
  before=value;value=Steering.Step(value,0,1/fps,car.Steering,true)
  near((value-before)*car.Steering.MaxAngle,75/fps)
 end
end
''')

    def test_keyboard_overlap_reversal_and_settings_do_not_reset_rack(self):
        self.run_luau('''
local car=load('VehicleManager').SpawnVehicle('KazeRS',CFrame.new(0,2.1,0),localPlayer)
local vc=load('VehicleController');vc.SetActiveVehicle(car)
key(Enum.KeyCode.D,true,true);advance(.3)
local angle=vc.GetTelemetry().Steer*32;near(angle,18)
key(Enum.KeyCode.A,true,true);advance(1/60)
near(vc.GetTelemetry().Steer*32,17)
vc.SetSteeringRateScale(.5);advance(1/60)
near(vc.GetTelemetry().Steer*32,16.5)
key(Enum.KeyCode.D,false);advance(.6)
assert(vc.GetTelemetry().Steer<0)
input.focusedText={};advance(.2);near(vc.GetTelemetry().Throttle,0)
''')

    def test_all_five_saved_axles_and_wheel_orientation(self):
        self.run_luau('''
local vm=load('VehicleManager');local rs=load('RaycastSuspension')
local expected={BrennerS1={-4.4,3.9,2.8,-.75},KazeRS={-4.5,4.5,2.607,-.7},FalkeE3={-4.75,4.4,2.65,-.75},KumoR1={-4.7,4.7,2.7535,-.65},FrecciaHF={-5,4,2.602,-.75}}
for id,spec in pairs(expected)do
 local tuning=load('CarProfiles').Get(id);local car=vm.BuildVehicleModel(id,tuning)
 for _,wid in ipairs({'WheelFL','WheelFR','WheelRL','WheelRR'})do
  local front=wid:sub(6,6)=='F';local right=wid:sub(7,7)=='R'
  local mount=rs.GetMountOffset(wid,tuning);near(mount.X,(right and 1 or -1)*spec[3]);near(mount.Z,front and spec[1]or spec[2])
  local wheel=car.VisualWheels:FindFirstChild('Visual_'..wid);near(wheel.Position.Y,spec[4]);near(wheel.Position.Z,mount.Z)
  local tyre=wheel.Mesh3D.Tyre;assert(math.abs(tyre.CFrame.RightVector.X)>.999,'Tyre axle is not horizontal X')
  near(tyre.Size.Y,tuning.Tyres.Radius*2)
  local rim=wheel.Mesh3D.Rim;assert(right and rim.Position.X>wheel.Position.X or not right and rim.Position.X<wheel.Position.X,'Rim faces inward')
 end
end
''')

    def test_suspension_visuals_share_solver_mounts_and_turn_in_air(self):
        self.run_luau('''
local tuning=load('CarProfiles').Get('KazeRS');local rs=load('RaycastSuspension')
local car=load('VehicleManager').BuildVehicleModel('KazeRS',tuning);car:PivotTo(CFrame.new(0,2.1,0))
car.Body.WheelFL.Position=V.new(-3.3,.3,-4.8)
local result=rs.Solve(car,1/60,tuning,.4,0,0,false,0,1000,{},1)
near(result.Wheels.WheelFL.VisualOffset.X,-3.3)
for _,state in pairs(result.Wheels)do
 if state.IsGrounded then near(car.Body.Position.Y+state.VisualOffset.Y-tuning.Tyres.Radius,0)end
 assert(state.TotalWheelForce.Magnitude==state.TotalWheelForce.Magnitude)
end
workspace.noGround=true
result=rs.Solve(car,1/60,tuning,.4,0,0,false,0,1000,{},1)
assert(result.GroundedCount==0);assert(result.Wheels.WheelFL.SteerAngle~=0)
''')

    def test_left_right_corners_and_straight_noise(self):
        self.run_luau('''
local analyzer=load('CurvatureAnalyzer')
for _,left in ipairs({true,false})do
 local samples={};for i=0,24 do
  local angle=i*math.pi/48;local radius=100
  samples[#samples+1]={Position=V.new((left and 1 or -1)*radius*(1-math.cos(angle)),0,radius*math.sin(angle)),Distance=radius*angle,Progress=i/24,Curvature=0}
 end
 local notes=analyzer.AnalyzeStage(samples);assert(#notes==1,'One smooth corner should produce one call')
 assert(notes[1].Direction==(left and 'Left'or'Right'));assert(notes[1].EndDistance>notes[1].DistanceAlongTrack)
end
local straight={};for i=1,100 do straight[i]={Position=V.new(math.sin(i)*.01,0,i*16),Distance=i*16,Progress=i/100,Curvature=0}end
assert(#analyzer.AnalyzeStage(straight)==0)
''')

    def test_route_projection_hairpin_and_lookahead(self):
        self.run_luau('''
local p=load('StageProgress')
local route={{Position=V.new(0,0,0),Distance=0},{Position=V.new(0,0,100),Distance=100},{Position=V.new(20,0,100),Distance=120},{Position=V.new(20,0,0),Distance=220}}
local distance=p.Project(route,V.new(20,0,75),140);near(distance,145)
near(p.Project(route,V.new(0,0,75),75),75)
assert(p.Lookahead(100,7,3)>p.Lookahead(100,6,3));assert(p.Lookahead(1000,1,5)<=650)
''')

    def test_codriver_calls_facing_backwards_and_resets_for_new_stage(self):
        self.run_luau('''
local car=load('VehicleManager').SpawnVehicle('KazeRS',CFrame.new(0,2,-80),localPlayer)
car.Body.CFrame=CFrame.lookAt(V.new(0,2,-80),V.new(0,2,0));car.Body.AssemblyLinearVelocity=V.new(0,0,-30)
local vc=load('VehicleController');vc.SetActiveVehicle(car)
local function data()
 local old=services.ReplicatedStorage:FindFirstChild('ActiveStageData');if old then old:Destroy()end
 local stage=folder(services.ReplicatedStorage,'ActiveStageData');stage:SetAttribute('SampleCount',4);stage:SetAttribute('NoteCount',2)
 local route=folder(stage,'RouteSamples')
 for i,spec in ipairs({{0,0,0},{0,-100,100},{50,-100,150},{50,0,250}})do local n=folder(route,'p'..i);n:SetAttribute('Position',V.new(spec[1],0,spec[2]));n:SetAttribute('Distance',spec[3])end
 local nf=folder(stage,'PaceNotes')
 for i,spec in ipairs({{100,145,'Left'},{150,210,'Right'}})do local n=folder(nf,'n'..i);n:SetAttribute('Index',i);n:SetAttribute('Distance',spec[1]);n:SetAttribute('EndDistance',spec[2]);n:SetAttribute('Severity',2);n:SetAttribute('Direction',spec[3]);n:SetAttribute('Description',spec[3]..' 2')end
end
data();local c=load('CoDriverClient');advance(.11)
assert(c.GetActiveCall().IsActive);assert(c.GetActiveCall().Direction=='Left');near(c.GetActiveCall().DistanceRemaining,20)
assert(c.GetUpcomingNote():find('into'))
car.Body.CFrame=CFrame.new(0,2,-90);advance(.11);near(c.GetProgress(),90)
data();advance(.11);assert(c.GetActiveCall().Index==1)
''')

    def test_original_generation_is_seeded_uses_props_and_shares_route(self):
        self.run_luau('''
local manager=load('StageManager');local config={Seed=42,LengthStuds=1600,RoadWidth=24,SegmentLength=16,Curviness=1,ElevationRange=55,Weather='Clear'}
local a,b=manager.GenerateControlPoints(config),manager.GenerateControlPoints(config)
for i=1,#a do near((a[i]-b[i]).Magnitude,0)end
local stage=manager.BuildStage(config)
local shared=services.ReplicatedStorage.ActiveStageData
assert(#shared.RouteSamples:GetChildren()==#manager.GetSamples())
assert(#shared.PaceNotes:GetChildren()==#manager.GetPaceNotes())
local nativeProps=0;for _,n in ipairs(stage.Scenery:GetChildren())do if n:IsA('Model')then nativeProps+=1 end end
assert(nativeProps>20,'Supplied props were not reused')
for _,n in ipairs(stage.Roadbed:GetChildren())do if n.Name:find('^Road_')then assert(n.CanCollide);assert(n.CFrame.UpVector.Y>.95)end end
''')

    def test_missing_stage_switch_cannot_hide_road_and_regeneration_moves_all_players(self):
        self.run_luau('''
local manager=load('StageManager');local vm=load('VehicleManager')
local peer=newPlayer(202)
load('MainServer')
local remotes=load('StageRemotes');local road=workspace.RallyStage.Roadbed:GetChildren()[1]
assert(remotes.GetFunction('ToggleStageMode'):InvokeServer('PineForest')=='Procedural')
assert(road.Transparency==0 and road.CanCollide)
advance(1)
local cars=workspace.RallyVehicles:GetChildren();assert(#cars==2)
assert(remotes.GetFunction('RequestStageRegen'):InvokeServer(150,'Clear'))
assert(#workspace.RallyVehicles:GetChildren()==2)
for _,car in ipairs(workspace.RallyVehicles:GetChildren())do assert(car.OwnerUserId==nil);assert(car:GetAttribute('OwnerUserId')~=nil)end
''')

    def test_cockpit_default_replay_moves_clone_only(self):
        self.run_luau('''
local car=load('VehicleManager').SpawnVehicle('KazeRS',CFrame.new(0,2.1,0),localPlayer)
local vc=load('VehicleController');vc.SetActiveVehicle(car)
local camera=load('CameraController');assert(camera.GetMode()=='Cockpit');camera.SetMode('Chase');assert(camera.GetMode()=='Cockpit')
local ghost=node({'ReplicatedStorage','RallyClient','GhostClient'})
local codec=load('TelemetryCodec')
local frames={codec.CreateFrame(0,CFrame.new(100,2,100),V.zero,0,0,1000,1),codec.CreateFrame(5,CFrame.new(200,2,100),V.zero,0,0,1000,1)}
cache[ghost]={GetPersonalBest=function()return {CarId='KazeRS',TotalTime=5,Frames=frames}end}
load('ReplayGui');key(Enum.KeyCode.R,true);advance(.2,true)
assert(camera.GetMode()=='TracksideDirector')
near(car.Body.Position.X,0);assert(workspace.LocalReplay.PrimaryPart.Position.X>100)
key(Enum.KeyCode.R,false);key(Enum.KeyCode.R,true);advance(.1,true)
assert(camera.GetMode()=='Cockpit');assert(not workspace:FindFirstChild('LocalReplay'))
''')

    def test_source_manifest_includes_all_original_scripts(self):
        manifest=json.loads((ROOT/'BASE_MANIFEST.json').read_text())
        self.assertEqual(len(manifest['scripts']),24)
        for row in manifest['scripts']:
            self.assertTrue((ROOT/row['file']).is_file())

    def test_binary_contains_shipped_sources_and_exact_backups(self):
        sys.path.insert(0,str(ROOT/'tools'))
        from build import build, Place, property_rows
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            report=build(ROOT/'base/Redone_Upload.rbxl',output)
            self.assertEqual(report['original_instances'],14091)
            self.assertEqual(report['effective_original_source_changes'],13)
            self.assertTrue(report['original_parent_relationships_unchanged'])
            shipped=Place((output/'Backseat_Rally_Redone_Fixed.rbxl').read_bytes())
            actual=property_rows(shipped,'Source')
            original=property_rows(Place((ROOT/'base/Redone_Upload.rbxl').read_bytes()),'Source')
            for row in report['source_repairs']:
                expected=ROOT/'src'/Path(*row['path'].split('.')).with_suffix('.lua')
                self.assertEqual(actual[row['ref']],expected.read_text())
                self.assertEqual(actual[row['backup_ref']],original[row['ref']])
            bad=output/'wrong_base.rbxl'
            bad.write_bytes(b'invalid place')
            with self.assertRaises(ValueError):build(bad,output)

    def test_stage_switch_restores_hidden_triggers_and_original_material_visibility(self):
        self.run_luau('''
load('MainServer')
local world=folder(workspace,'World');local pine=folder(world,'Stage_PineForest')
local trigger=part(pine,'HiddenTrigger',V.new(1,1,1),V.zero)
trigger.Transparency=1;trigger.CanCollide=false;trigger.CanTouch=true;trigger.CanQuery=false
local leaf=part(pine,'Leaves',V.new(1,1,1),V.zero)
leaf.Transparency=.4;leaf.CanCollide=false
local remote=load('StageRemotes').GetFunction('ToggleStageMode')
assert(remote:InvokeServer('PineForest')=='PineForest')
near(leaf.Transparency,.4);assert(trigger.Transparency==1 and not trigger.CanCollide)
remote:InvokeServer('Procedural');near(leaf.Transparency,1)
local routeTrigger=workspace.RallyStage.Checkpoints.StartGantry.StartTrigger
assert(routeTrigger.Transparency==1 and not routeTrigger.CanCollide)
remote:InvokeServer('PineForest');near(leaf.Transparency,.4);assert(not leaf.CanCollide)
''')

if __name__=='__main__':unittest.main(verbosity=2)
