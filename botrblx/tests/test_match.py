"""Kickoff state transitions and rendered multiplayer observations in real Luau."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from export_standalone import literal,load_arena_profile
from test_bridge import packet

LUAU=os.environ.get("LUAU_BIN") or shutil.which("luau")
PROFILE=load_arena_profile(HERE.parent/"arena_profile.json")


@unittest.skipUnless(LUAU,"Set LUAU_BIN to exercise multiplayer and kickoff")
class MatchTests(unittest.TestCase):
    def run_lua(self,body,mock=False):
        source=(HERE/"fixtures/roblox_mock.luau").read_text() if mock else ""
        source+="\nlocal profile="+literal(PROFILE)+"\n"
        for name in ("Arena","Cars","Kickoff"):
            source+="local "+name+"=(function()\n"+(HERE.parent/"templates"/("local_"+name.lower()+".lua")).read_text()+"\nend)()\n"
        source+="local p="+literal(packet())+"\np.car.velocity={0,0,0};p.ball.velocity={0,0,0}\n"+body
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"match.luau";path.write_text(source)
            result=subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_detects_all_standard_spawns_both_teams_and_only_once(self):
        self.run_lua('''
for team=0,1 do
 for _,spawn in ipairs({{-2048,-2560},{2048,-2560},{-256,-3840},{256,-3840},{0,-4608}})do
  local k=Kickoff.new(profile)
  local s=team==0 and 1 or -1;p.team=team
  p.car.position={spawn[1]*s,spawn[2]*s,17}
  local d=math.sqrt(spawn[1]^2+spawn[2]^2)
  p.car.forward={-spawn[1]*s/d,-spawn[2]*s/d,0}
  assert(k:step(p,0)) -- Holds neutral during detection, never lets policy move away.
  local a,mode=k:step(p,.2)
  assert(a and a[1]==1 and a[7]==1 and mode=='kickoff: drive')
  p.ball.velocity={200,0,0}
  assert(not k:step(p,.3),'Must hand off immediately once ball moves')
  p.ball.velocity={0,0,0}
  assert(not k:step(p,.4),'Retriggered while still centered')
  p.ball.position={100,0,93.15};assert(not k:step(p,.5))
  p.ball.position={0,0,93.15};assert(k:step(p,.6))
 end
end
''')

    def test_rejects_centered_ball_during_normal_play_and_wrong_heading(self):
        self.run_lua('''
for _,position in ipairs({{0,-1000,17},{0,-4608,400},{0,0,17},{1000,-3000,17}})do
 p.car.position=position
 local k=Kickoff.new(profile)
 assert(not k:step(p,0));assert(not k:step(p,.3))
end
p.car.position={0,-4608,17};p.car.forward={0,-1,0}
local k=Kickoff.new(profile);assert(not k:step(p,0))
''')

    def test_countdown_waits_and_flip_clock_starts_when_car_moves(self):
        self.run_lua('''
local matchHud=object('ScreenGui','CarSoccerMatchHud');matchHud.Parent=playerGui;matchHud.Enabled=true
local call=object('Frame','Call');call.Parent=matchHud;call.Visible=true
local number=object('TextLabel');number.Parent=call;number.Text='3'
local k=Kickoff.new(profile);k:step(p,0)
for _,t in ipairs({.2,1,2,3,4,6})do
 local a,mode=k:step(p,t,playerGui)
 assert(a and a[1]==0 and a[6]==0 and a[7]==0 and mode=='kickoff: countdown')
end
call.Visible=false
local a=k:step(p,7,playerGui)
assert(a[1]==1 and a[6]==0 and not k.moveAt,'Frozen countdown consumed jump sequence')
-- Four seconds into play still allowed despite a seven-second countdown.
p.car.velocity={0,1400,0};p.car.position={0,-2400,17}
a=k:step(p,7.1,playerGui);assert(a[6]==1 and k.moveAt==7.1)
-- Exact press/release/press order; long gaps cannot skip a phase.
a=k:step(p,7.22,playerGui);assert(a[6]==0 and k.state=='release')
a=k:step(p,7.34,playerGui);assert(a[6]==1 and a[3]==-1 and k.state=='flip')
a=k:step(p,7.48,playerGui);assert(a[6]==0 and a[3]==0 and k.state=='recover')
a=k:step(p,7.8,playerGui);assert(a[6]==0)
a=k:step(p,8,playerGui);assert(a[6]==0,'Second flip attempted')
k:reset();assert(not k.state and not k.flipped and not k.moveAt)
''',mock=True)

    def test_fallback_launches_without_hud_and_has_bounded_timeout(self):
        self.run_lua('''
local k=Kickoff.new(profile);k:step(p,0)
local a=k:step(p,.2);assert(a[1]==1 and a[7]==1 and a[6]==0)
a=k:step(p,8);assert(a and a[6]==0,'Jump clock advanced while frozen')
assert(not k:step(p,12.3),'Waiting sequence never timed out')
k:reset();k:step(p,13);assert(k:step(p,13.2))
p.car.velocity={0,900,0};k:step(p,13.3)
assert(not k:step(p,17.9),'Moving sequence never timed out')
''')

    def test_steers_using_actual_car_right_axis_and_yields_to_teammate(self):
        self.run_lua('''
local k=Kickoff.new(profile);k:step(p,0);k:step(p,.2)
p.car.position={300,-3000,17};p.car.velocity={0,600,0}
local a=k:step(p,.3);assert(a[2]==1,'D must turn toward negative X when facing +Y')
p.car.position={-300,-3000,17};a=k:step(p,.4);assert(a[2]==-1)
for team=0,1 do
 local s=team==0 and 1 or -1
 p.team=team;p.car.position={-2048*s,-2560*s,17};p.car.velocity={0,0,0}
 local d=math.sqrt(2048^2+2560^2);p.car.forward={2048*s/d,2560*s/d,0}
 p.other_cars={{team=team,position={2048*s,-2560*s,17}}}
 k=Kickoff.new(profile);k:step(p,0);assert(not k:step(p,.2),'Ignored teammate left-goes priority')
 p.other_cars[1].team=1-team
 k=Kickoff.new(profile);k:step(p,0);assert(k:step(p,.2),'Yielded to opponent')
end
''')

    def test_team_plate_dimming_is_supported_but_custom_paint_is_not_guessed(self):
        self.run_lua('''
for n=0,8 do
 local s=.95^n
 assert(Cars.team({R=46/255*s,G=120/255*s,B=226/255*s})==0)
 assert(Cars.team({R=232/255*s,G=116/255*s,B=38/255*s})==1)
end
assert(Cars.team({R=.4,G=.4,B=.4})==nil)
assert(Cars.team({R=0,G=1,B=0})==nil)
''')

    def cars_fixture(self):
        return '''
local function remote(name,team,x)
 local model=object('Model',name);model.Parent=scene
 local root=object('Part','Root');root.Parent=model;root.CFrame=frame(x);root.Position=root.CFrame.Position
 model.PrimaryPart=root
 local tag=object('BillboardGui','Nametag');tag.Parent=root;tag.Enabled=true
 local plate=object('Frame','Plate');plate.Parent=tag
 plate.BackgroundColor3=team==0 and {R=46/255,G=120/255,B=226/255}or{R=232/255,G=116/255,B=38/255}
 return model,root,tag,plate
end
local function pose(cf,previous,dt)
 local v=(cf.Position-previous.Position)/dt
 return {position={cf.Position.X*10,cf.Position.Z*10,cf.Position.Y*10},
  velocity={v.X*10,v.Z*10,v.Y*10},forward={1,0,0},up={0,0,1},angular_velocity={0,0,0}},
  (cf.Position-previous.Position).Magnitude
end
local reader=Cars.new(profile,Arena)
local function read(t)return reader:read(scene,carRoot,ballRoot,t,pose,p.ball,91.25,0)end
'''

    def test_remote_cars_are_observed_with_velocity_and_verified_teammate_boost(self):
        self.run_lua(self.cars_fixture()+'''
local m,r,tag=remote('Enemy',1,40)
local friend,fr,ft=remote('Friend',0,20)
local holder=object('Frame','Boost');holder.Parent=ft
local fill=object('Frame','Fill');fill.Parent=holder;fill.Size={X={Scale=.27}}
-- An opponent bar, even if planted in the render tree, must not be trusted.
local fake=object('Frame','Boost');fake.Parent=tag
local fakeFill=object('Frame','Fill');fakeFill.Parent=fake;fakeFill.Size={X={Scale=.9}}
assert(#read(0)==0,'First sample invented velocity')
r.CFrame=frame(42);r.Position=r.CFrame.Position
local rows=read(.1);assert(#rows==2 and reader.opponents==1 and reader.teammates==1)
assert(rows[1].team==0 and rows[1].boost_verified and math.abs(rows[1].boost_estimate-27)<1e-8)
assert(rows[2].team==1 and not rows[2].boost_verified and rows[2].boost_estimate==50)
assert(math.abs(rows[2].velocity[1]-200)<1e-6,'Render velocity lost')
assert(rows[2].position[1]==420 and rows[2].forward[1]==1)
''',mock=True)

    def test_respawn_hidden_unknown_teleport_and_scenery_do_not_create_phantom_cars(self):
        self.run_lua(self.cars_fixture()+'''
local m,r,tag,plate=remote('Enemy',1,40)
local prop=object('Model','PaintedProp');prop.Parent=scene
local root=object('Part','PropRoot');root.Parent=prop;prop.PrimaryPart=root
read(0);assert(#read(.1)==1)
tag.Enabled=false;assert(#read(.15)==0)
tag.Enabled=true;assert(#read(.2)==0);assert(#read(.25)==1)
plate.BackgroundColor3={R=0,G=1,B=0};assert(#read(.3)==0 and reader.unknown==1)
plate.BackgroundColor3={R=232/255,G=116/255,B=38/255};read(.35);assert(#read(.4)==1)
r.CFrame=frame(1000);r.Position=r.CFrame.Position;assert(#read(.45)==0,'Teleport treated as velocity')
assert(#read(.5)==1)
m.Parent=nil;assert(#read(.55)==0,'Removed/demo car retained')
scene.children.Enemy=nil
local replacement,newRoot=remote('Enemy',1,60)
assert(#read(1)==0);assert(#read(1.1)==1,'Respawn was never reacquired')
assert(#read(1.5)==0,'Long frame gap retained stale velocity')
''',mock=True)

    def test_limits_context_to_nearest_five_and_rejects_own_root(self):
        self.run_lua(self.cars_fixture()+'''
for i=1,8 do remote('Other'..i,i%2,i*20)end
local ownTag=object('BillboardGui','Nametag');ownTag.Parent=carRoot
local plate=object('Frame','Plate');plate.Parent=ownTag;plate.BackgroundColor3={R=232/255,G=116/255,B=38/255}
read(0);local rows=read(.1)
assert(#rows==5 and reader.opponents+reader.teammates==5)
for i,row in ipairs(rows)do assert(row.position[1]==i*200,'Did not select nearest cars')end
''',mock=True)


if __name__=="__main__":unittest.main()
