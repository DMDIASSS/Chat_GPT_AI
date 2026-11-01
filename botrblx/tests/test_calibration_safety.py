"""Manual landmark fitting and conservative ground goal guards."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from export_standalone import literal
LUAU=os.environ.get('LUAU_BIN')or shutil.which('luau')

@unittest.skipUnless(LUAU,'Set LUAU_BIN for calibration/goal checks')
class CalibrationSafetyTests(unittest.TestCase):
    def run_lua(self,body):
        source='local profile='+literal(json.loads((ROOT/'arena_profile.json').read_text()))+'\n'
        for name,file in [('Arena','local_arena.lua'),('Physics','local_physics.lua'),('Calibration','local_calibration.lua'),('Safety','local_goal_safety.lua'),('Intercept','local_intercept.lua')]:
            source+='local '+name+'=(function()\n'+(ROOT/'templates'/file).read_text()+'\nend)()\n'
        source+='''
local arena=Arena.new(profile);local physics=Physics.new(profile,arena)
local calibration=Calibration.new(profile);local safety=Safety.new(profile,arena,physics,calibration)
local function packet(car,ball,velocity,team)
 return {team=team or 0,boost=50,ground_estimate=true,ball_radius=91.25,ball_size_verified=true,car_preset='standard',car_dimensions_verified=true,
 car={position=car,velocity={0,1200,0},forward={0,1,0},up={0,0,1},angular_velocity={0,0,0}},
 ball={position=ball,velocity=velocity or {0,0,0},angular_velocity={0,0,0}}}
end
local model={1,0,0,0,0,0,1,0}
local function landmarks()
 local points={center={point={100,50,17},root={100,50,17},forward={0,1,0},up={0,0,1},reference='center'}}
 for _,g in ipairs({{'orange',1},{'blue',-1}})do
  local name,s=g[1],g[2];local y=50+s*5120
  for _,p in ipairs({{'a',{-760,y,320},{-1,0,0}}, {'b',{960,y,320},{1,0,0}},
    {'top',{100,y,620},{0,0,1}}, {'back',{100,y+s*880,320},{0,s,0}}})do
   local cfg=profile.car_presets.standard;local up=p[1]=='top'and{0,-1,0}or{0,0,1};local root={}
   for j=1,3 do root[j]=p[2][j]-p[3][j]*(cfg.size[1]/2+cfg.offset[1])-up[j]*cfg.offset[3]end
   points[name..'_'..p[1]]={point=p[2],root=root,forward=p[3],up=up,reference='bumper',preset='standard'}
  end
 end
 return points
end
'''+body
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'calibration.luau';path.write_text(source)
            r=subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_fit_both_goals_preserves_raw_points_and_needs_explicit_apply(self):
        self.run_lua('''
calibration.points=landmarks()
local fitted=calibration:fit()
assert(math.abs(fitted.goals[1].half_width-860)<.01 and math.abs(fitted.goals[2].height-620)<.01)
assert(fitted.goals[1].normal[2]==-1 and fitted.goals[2].normal[2]==1)
assert(calibration.active==nil,'Fit silently changed live geometry')
calibration:apply()
assert(calibration:goal(0).origin[2]==-5070 and calibration:goal(1).origin[2]==5170)
assert(calibration.points.center.point[3]==17,'Modified the measured landmark')
local other=Calibration.new(profile);other:load(calibration:export())
assert(other.candidate and other.active==nil,'Loading silently applied calibration')
other:apply();assert(other:goal(1).half_width==860)
''')

    def test_bumper_capture_corrects_root_offset_and_rejects_motion(self):
        self.run_lua('''
local cfg=profile.car_presets.standard
local p=packet({100,50,17},{0,0,93.15});p.car.velocity={0,0,0}
for i=0,4 do calibration:observe(p,i*.1,{},physics)end
calibration:capture();assert(calibration.index==2)
p.car.position={-760+cfg.size[1]/2+cfg.offset[1],5170,320-cfg.offset[3]};p.car.forward={-1,0,0}
for i=10,14 do calibration:observe(p,i*.1,{},physics)end
calibration:capture()
assert(math.abs(calibration.points.orange_a.point[1]+760)<.001)
assert(math.abs(calibration.points.orange_a.point[3]-320)<.001,'Ignored hitbox face height')
p.car.velocity={100,0,0}
for i=20,24 do calibration:observe(p,i*.1,{},physics)end
assert(not pcall(function()calibration:capture()end),'Accepted a moving landmark')
assert(calibration.index==3)
''')

    def test_bad_geometry_and_invalid_files_do_not_replace_active_fit(self):
        self.run_lua('''
calibration.points=landmarks();calibration:apply()
local valid=calibration.active
calibration.points.blue_top.point[3]=2000
assert(not pcall(function()calibration:apply()end),'Accepted the stadium ceiling as crossbar')
assert(calibration.active==valid,'Bad fit replaced live calibration')
local points=calibration.points
assert(not pcall(function()calibration:load({version=1,place=101880234193261,points={center={point={0/0,0,0}}}})end))
assert(calibration.points==points)
''')

    def test_partial_file_can_resume_and_motion_fit_does_not_infer_mass(self):
        self.run_lua('''
local points=landmarks()
calibration:startMotion(0)
calibration:load({version=1,place=101880234193261,reference='center',points={center=points.center,orange_a=points.orange_a}})
assert(calibration.index==3 and calibration.active==nil)
assert(not calibration.recordingUntil,'Loading mixed an old active recording with restored measurements')
calibration:startMotion(0)
local p=packet({-3000,-3000,17},{0,0,800});p.car.velocity={0,0,0}
for i=0,25 do
 local t=i*.1;p.ball.position={0,0,800+1000*t-325*t*t};p.ball.velocity={0,0,1000-650*t}
 calibration:observe(p,t,{},physics)
end
calibration.recordingUntil=nil
local r=calibration:summarizeMotion()
assert(r.gravity_consistent and math.abs(r.gravity+650)<15,'Did not fit an isolated flight')
assert(r.verified_ball_radius==91.25 and not r.mass and not r.car_mass,'Invented masses from positions')
''')

    def test_own_goal_guard_stops_straight_push_and_preserves_clear_turns_and_jumps(self):
        self.run_lua('''
for _,team in ipairs({0,1})do
 local sign=team==0 and -1 or 1
 local p=packet({0,sign*4700,17},{0,sign*4900,93.15},{0,sign*200,0},team)
 p.car.velocity={0,sign*1200,0};p.car.forward={0,sign,0}
 local a,mode=safety:step(p,model,1)
 assert(a and a[1]==-1 and a[7]==0 and mode=='Own-goal push guard')
 p.car.velocity={0,0,0}
 a=safety:step(p,model,1);assert(a and a[1]==0 and a[7]==0,'Accelerated into an own-goal push from rest')
 p.car.velocity={0,sign*1200,0}
 local turn=table.clone(model);turn[2]=1
 assert(not safety:step(p,turn,1),'Suppressed a turning clear')
 turn[2]=0;turn[6]=1
 assert(not safety:step(p,turn,1),'Suppressed a jump save')
 p.ground_estimate=false
 assert(not safety:step(p,model,1),'Changed airborne controls')
end
''')

    def test_clear_roll_in_is_protected_but_defender_or_near_post_restores_actor(self):
        self.run_lua('''
local p=packet({0,4000,17},{0,4500,93.15},{0,1200,0})
p.car.velocity={0,2100,0}
local a,mode=safety:step(p,model,1)
assert(a and mode=='Leave clear shot'and a[7]==0,'Retouched an uncontested scoring ball')
p.other_cars={{team=1,position={0,4900,17},velocity={0,0,0}}}
assert(not safety:step(p,model,1),'Abandoned the shot with a defender in reach')
p.other_cars={};p.ball.position[1]=820;p.car.position[1]=820
assert(not safety:step(p,model,1),'Treated a post miss as a guaranteed goal')
p.ball.position={0,4500,500};p.car.position[1]=0
assert(not safety:step(p,model,1),'Changed a high shot')
''')

    def test_fitted_goal_bounds_are_used_by_safety(self):
        self.run_lua('''
local g=calibration:goal(1)
assert(safety:fits(g,{700,5200,93.15},93.15,35))
calibration.points=landmarks();calibration:apply()
g=calibration:goal(1)
assert(not safety:fits(g,{850,5200,93.15},93.15,35),'Ignored the measured narrower opening')
''')

    def test_optional_ground_aiming_targets_the_measured_goal_plane(self):
        self.run_lua('''
calibration.points=landmarks();calibration:apply()
local planner=Intercept.new(profile,arena,physics);planner.calibration=calibration
local p=packet({100,3000,17},{100,4300,93.15})
local action=planner:step(p,model,1)
assert(action and planner.last.goal_target[1]==100 and planner.last.goal_target[2]==5170,'Ignored measured goal centre/plane')
''')

    def test_ground_post_contact_uses_low_box_corner_not_bumper_centre_height(self):
        self.run_lua('''
calibration.points=landmarks()
local cfg=profile.car_presets.standard;local height=17+cfg.offset[3]
local low=height-cfg.size[3]/2;local r=profile.arena.MOUTH_FILLET
local boundary=896-r+math.sqrt(r*r-(r-low)^2)
for _,name in ipairs({'blue','orange'})do for _,id in ipairs({'a','b'})do
 local p=calibration.points[name..'_'..id];local sign=id=='a'and -1 or 1
 p.point[1]=100+sign*boundary;p.point[3]=height
 p.root={p.point[1]-sign*(cfg.size[1]/2+cfg.offset[1]),p.point[2],17}
end end
local fit=calibration:fit()
assert(math.abs(fit.goals[1].half_width-896)<.01 and math.abs(fit.goals[2].half_width-896)<.01,'Rounded post plus full car box produced a falsely narrow goal')
calibration.reference='center'
fit=calibration:fit();assert(math.abs(fit.goals[1].half_width-896)<.01,'Changing capture mode changed previously recorded references')
''')

    def test_motion_recording_finishes_at_twenty_seconds_without_invented_gravity(self):
        self.run_lua('''
local p=packet({-3000,-3000,17},{0,0,93.15});p.car.velocity={0,0,0}
calibration:startMotion(0)
for i=0,240 do calibration:observe(p,i*.1,{},physics)end
assert(not calibration.recordingUntil and #calibration.motion.samples<=210)
assert(calibration.motion.summary.samples>150 and not calibration.motion.summary.gravity_consistent,'Invented airborne gravity from a resting ball')
''')
