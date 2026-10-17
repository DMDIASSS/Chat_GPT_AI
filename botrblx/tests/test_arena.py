"""Measured collision geometry, rendered hitboxes/pads and bounded recovery."""
import json
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

LUAU=os.environ.get("LUAU_BIN") or shutil.which("luau")
PROFILE=load_arena_profile(HERE.parent/"arena_profile.json")


@unittest.skipUnless(LUAU,"Set LUAU_BIN to exercise the collision and sensor adapters")
class ArenaTests(unittest.TestCase):
    def run_lua(self,body,mock=False):
        prefix=(HERE/"fixtures/roblox_mock.luau").read_text(encoding="utf-8") if mock else ""
        source=prefix+"\nlocal profile="+literal(PROFILE)+"\n"
        for name,file in (("Arena","local_arena.lua"),("Pads","local_pads.lua")):
            source+="local "+name+"=(function()\n"+(HERE.parent/"templates"/file).read_text()+"\nend)()\n"
        source+="local arena=Arena.new(profile)\n"+body
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"arena.luau";path.write_text(source,encoding="utf-8")
            r=subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_matches_saved_game_collision_distances_including_goals_and_facets(self):
        cases=json.loads((HERE/"fixtures/arena_reference.json").read_text())["cases"]
        self.run_lua("local cases="+literal(cases)+'''
for _,case in ipairs(cases)do
 local d,n=arena:query(case.position)
 assert(math.abs(d-case.distance)<1e-6,'Saved game collision distance differs')
 local dot=n[1]*case.normal[1]+n[2]*case.normal[2]+n[3]*case.normal[3]
 assert(dot>.97,'Collision normal differs')
end
''')

    def test_wheel_contacts_on_floor_ceiling_curved_ramp_and_goal_interior(self):
        self.run_lua('''
local function car(position,forward,up)return {position=position,forward=forward,up=up,velocity={0,0,0}}end
assert(arena:ground(car({0,0,17},{0,1,0},{0,0,1})))
assert(not arena:ground(car({0,0,150},{0,1,0},{0,0,1})))
assert(arena:ground(car({0,0,2031},{0,1,0},{0,0,-1})))
local _,normal=arena:query({4030,0,100})
assert(arena:ground(car({4030,0,100},{0,1,0},normal)),'Ramp was mistaken for air')
assert(arena:ground(car({0,5600,27},{1,0,0},{0,0,1})),'Net interior floor missing')
assert(not arena:ground(car({0,0,40},{0,1,0},{0,0,-1})),'Upside-down chassis is not wheel contact')
''')

    def test_collision_hitbox_comes_from_selection_box_not_decorations(self):
        self.run_lua('''
local cfg=profile.car_presets.low
local boxPart=object('Part','Debug');boxPart.Parent=car
boxPart.Size=Vector3.new(cfg.size[2]/10,cfg.size[3]/10,cfg.size[1]/10)
boxPart.CFrame=frame(0)
local selection=object('SelectionBox');selection.Adornee=boxPart;selection.Parent=boxPart
carRoot.CFrame.ToObjectSpace=function()return {Position=Vector3.new(cfg.offset[2]/10,cfg.offset[3]/10,-cfg.offset[1]/10)}end
local decoration=object('Part','Hat');decoration.Parent=car;decoration.Size=Vector3.new(100,100,100)
arena:measureCar(car,carRoot)
assert(arena.preset=='low'and arena.hitboxVerified)
selection.Parent=nil;boxPart.children.SelectionBox=nil
arena:measureCar(car,carRoot)
assert(arena.preset=='standard'and not arena.hitboxVerified)
''',mock=True)

    def test_wheel_ball_contacts_use_current_ball_radius(self):
        self.run_lua('''
local car={position={0,0,689},forward={1,0,0},up={0,0,1}}
local ball={position={0,0,500}}
assert(not arena:ground(car,ball,91.25))
local ground,contacts,onBall=arena:ground(car,ball,182.5)
assert(ground and contacts>=3 and onBall==contacts,'Scaled ball was ignored by wheel rays')
''')

    def test_ball_collision_radius_tracks_verified_scale_marker(self):
        self.run_lua('''
ballRoot.Size=Vector3.new(1000,1000,1000)
local radius,verified=arena:ballRadius(ballRoot)
assert(not verified and radius==91.25,'Root part is a marker, not a hitbox')
local attachment=object('Attachment','TrailBodyA');attachment.Parent=ballRoot
attachment.Position=Vector3.new(-91.25*.1*.6*2,0,0)
radius,verified=arena:ballRadius(ballRoot)
assert(verified and math.abs(radius-182.5)<1e-6)
''',mock=True)

    def test_stuck_wall_escape_is_bounded_and_leaves_ball_control_alone(self):
        self.run_lua('''
local p={car={position={4079,0,300},forward={0,1,0},up={-1,0,0},velocity={0,0,0}},
 ball={position={0,0,100}},ground_estimate=true,ball_radius=91.25}
local previous={1,0,0,0,0,0,0,0}
assert(not arena:recovery(p,previous,0))
local action,reason=arena:recovery(p,previous,2.3)
assert(action and action[1]==-1 and action[8]==1 and reason=='reverse/turn')
assert(arena:recovery(p,previous,2.5))
assert(not arena:recovery(p,previous,3.1),'Override exceeded escape duration')
arena:resetRecovery();p.ball.position={4079,50,300}
assert(not arena:recovery(p,previous,0))
assert(not arena:recovery(p,previous,2.3),'Interfered with a close ball')
''')

    def test_upside_down_idle_car_can_recover_without_throttle(self):
        self.run_lua('''
local p={car={position={0,0,40},forward={1,0,0},up={0,0,-1},velocity={0,0,0}},
 ball={position={1000,0,100}},ground_estimate=false,ball_radius=91.25}
local previous=table.create(8,0)
assert(not arena:recovery(p,previous,0))
local action,reason=arena:recovery(p,previous,2.3)
assert(action and action[5]==1 and action[6]==1 and reason=='upright')
''')

    def test_pad_positions_type_and_activity_are_measured_live(self):
        self.run_lua('''
local folder=object('Folder','BoostPads');folder.Parent=scene
local function makePad(x,count,active)
 local halo=object('Part','PadHalo');halo.Parent=folder;halo.Position=Vector3.new(x,.48,12)
 folder.children['halo'..x]=halo -- retain duplicate Roblox names in this simple mock
 local rings={}
 for i=1,count do
  local ring=object('Part','PadRing');ring.Parent=folder
  ring.Position=Vector3.new(x+math.cos(i*2*math.pi/count)*7,.53,12+math.sin(i*2*math.pi/count)*7)
  ring.Transparency=0;ring.Color=active and {R=1,G=.83,B=.19}or {R=.5,G=.55,B=.63}
  folder.children['ring'..x..'_'..i]=ring;rings[i]=ring
 end
 return rings
end
local small=makePad(17,10,true);local big=makePad(60,16,false)
folder.children.PadHalo=nil;folder.children.PadRing=nil
local pads=Pads.new(profile)
local selected=pads:read(scene,{170,120,17},0)
assert(pads.total==2 and pads.known==2 and #selected==2)
assert(selected[1].position[1]==170 and selected[1].position[2]==120 and selected[1].position[3]==70)
assert(selected[1].is_big==false and selected[1].active==true)
assert(selected[2].is_big==true and selected[2].active==false)
for _,ring in ipairs(big)do ring.Color={R=1,G=.83,B=.19}end
selected=pads:read(scene,{170,120,17},.3)
assert(selected[2].active==true)
small[1].Color={R=.8,G=.1,B=.1} -- unverified tint must not become a fake pad state
selected=pads:read(scene,{170,120,17},.6)
assert(pads.known==1 and #selected==1)
''',mock=True)


if __name__=="__main__":unittest.main()
