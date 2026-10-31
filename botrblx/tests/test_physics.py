"""Saved-solver trajectories and scenarios that distinguish prediction from chase."""
import json
import copy
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


class PhysicsProfileTests(unittest.TestCase):
    def test_rejects_division_by_zero_invalid_drag_and_non_monotonic_drive_curve(self):
        for key,value in (("CAR_MASS",0),("BALL_RADIUS",-1),("TICK_RATE",0),
                          ("BALL_DRAG",1),("BALLWORLD_RESTITUTION",-1),
                          ("DRIVE_SPEED_TORQUE_FACTOR",[[0,1],[0,.1]])):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as directory:
                profile=copy.deepcopy(PROFILE);profile["physics"][key]=value
                path=Path(directory)/"invalid.json";path.write_text(json.dumps(profile))
                with self.assertRaises(ValueError):load_arena_profile(path)


@unittest.skipUnless(LUAU,"Set LUAU_BIN to exercise physics prediction")
class PhysicsTests(unittest.TestCase):
    def run_lua(self,body):
        source="local profile="+literal(PROFILE)+"\n"
        for name,file in (("Arena","local_arena.lua"),("Physics","local_physics.lua"),("Intercept","local_intercept.lua")):
            source+="local "+name+"=(function()\n"+(HERE.parent/"templates"/file).read_text()+"\nend)()\n"
        source+='''
local arena=Arena.new(profile)
local physics=Physics.new(profile,arena)
local planner=Intercept.new(profile,arena,physics)
local model={1,0,0,0,0,0,1,0}
local function packet(car,ball,velocity,team)
 return {team=team or 0,boost=50,ground_estimate=true,ball_radius=91.25,
  car={position=car,velocity={0,0,0},angular_velocity={0,0,0},forward={0,1,0},up={0,0,1}},
  ball={position=ball,velocity=velocity or {0,0,0},angular_velocity={0,0,0}}}
end
'''+body
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"physics.luau";path.write_text(source,encoding="utf-8")
            r=subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            return r.stdout

    def test_predictor_against_independent_saved_solver_trajectories(self):
        cases=json.loads((HERE/"fixtures/ball_reference.json").read_text())["cases"]
        self.run_lua("local cases="+literal(cases)+'''
for _,case in ipairs(cases)do
 local prediction=physics:predict(case.ball,case.radius,case.seconds,4)
 for _,point in ipairs(case.points)do
  local actual=prediction[point.index]
  assert(math.abs(actual.time-point.time)<1e-7,'Prediction time differs')
  local error=0
  for i,v in ipairs(actual.position)do error=error+(v-point.position[i])^2 end
  assert(math.sqrt(error)<case.tolerance,case.name..' reference trajectory differs: '..math.sqrt(error))
 end
end
''')

    def test_world_impulse_matches_saved_velocity_and_spin_and_never_mutates_input(self):
        cases=json.loads((HERE/"fixtures/ball_reference.json").read_text())["cases"]
        cases=[c for c in cases if c["tolerance"]<1 and c["name"]!="sleep"]
        self.run_lua("local cases="+literal(cases)+'''
for _,case in ipairs(cases)do
 local state={position=table.clone(case.ball.position),velocity=table.clone(case.ball.velocity),angular_velocity=table.clone(case.ball.angular_velocity)}
 for _=1,math.floor(case.seconds*120+.5)do physics:step(state,case.radius,1/120)end
 for i,v in ipairs(state.velocity)do assert(math.abs(v-case.final_velocity[i])<.004,case.name..' velocity differs')end
 for i,v in ipairs(state.angular_velocity)do assert(math.abs(v-case.final_angular_velocity[i])<.004,case.name..' spin differs')end
 local p,v,w=case.ball.position[1],case.ball.velocity[3],case.ball.angular_velocity[2]
 physics:predict(case.ball,case.radius,case.seconds)
 assert(case.ball.position[1]==p and case.ball.velocity[3]==v and case.ball.angular_velocity[2]==w,'Predictor mutated observation')
end
''')

    def test_intercept_leads_fast_lateral_ball_and_suppresses_turning_boost(self):
        self.run_lua('''
local p=packet({0,-2400,17},{0,0,93.15},{1200,0,0})
local a,mode=planner:step(p,model,0)
assert(a and mode=='ground intercept')
assert(planner.last.ball[1]>500,'Chased current ball instead of predicted intercept')
assert(planner.last.target[1]>300,'Approach target omitted lateral flight')
assert(planner.last.time>.4 and planner.last.time<=2.5)
p.car.forward={0,-1,0}
a=planner:step(p,model,.1)
assert(a and a[7]==0,'Boosted away from target while turning')
''')

    def test_wrong_side_circles_instead_of_pushing_toward_own_goal(self):
        self.run_lua('''
local p=packet({0,1400,17},{0,0,93.15})
p.car.forward={0,-1,0}
local a,mode=planner:step(p,model,0)
assert(a and mode=='circle behind ball')
local side=planner.side
assert(math.abs(planner.last.target[1])>300,'Drove through the ball from wrong side')
p.car.position[1]=1
planner:step(p,model,.1);assert(planner.side==side,'Approach side flapped')
p.car.position={0,-1400,17};p.car.forward={0,1,0}
planner:step(p,model,.2);assert(planner.side==nil,'Approach side never reset')
''')

    def test_team_mirror_and_steer_sign(self):
        self.run_lua('''
local p=packet({1500,-2400,17},{400,-300,93.15},{-300,0,0})
local a=planner:step(p,model,0);local target=table.clone(planner.last.target)
planner:reset()
p.team=1
for _,v in ipairs({p.car.position,p.car.forward,p.car.velocity,p.ball.position,p.ball.velocity})do
 v[1]=-v[1];v[2]=-v[2]
end
local b=planner:step(p,model,.1)
assert(a and b and a[2]==b[2]and a[7]==b[7],'Orange behavior differs under field mirror')
assert(math.abs(target[1]+planner.last.target[1])<1e-6 and math.abs(target[2]+planner.last.target[2])<1e-6)
local car={position={0,0,17},forward={1,0,0},up={0,0,1}}
assert(planner:heading(car,{0,100,17})>0 and planner:heading(car,{0,-100,17})<0,'Native positive steer basis reversed')
''')

    def test_defensive_intercept_and_field_safe_corner_target(self):
        self.run_lua('''
local p=packet({800,-4500,17},{0,-3400,93.15},{0,-1600,0})
local a,mode=planner:step(p,model,0)
assert(a and planner.last.danger and mode=='defend intercept','Ignored own-goal trajectory')
p=packet({2500,3500,17},{3300,4200,93.15},{0,0,0})
a=planner:step(p,model,.1)
assert(a,'No corner approach')
local t=planner.last.target
assert(math.abs(t[1])<profile.arena.EXTENT_X and math.abs(t[2])<profile.arena.EXTENT_Y)
assert(arena:distance({t[1],t[2],70})>0,'Planned through rounded corner wall')
''')

    def test_close_touch_jump_air_wall_and_profile_mismatch_remain_with_model(self):
        self.run_lua('''
local p=packet({0,-250,17},{0,0,93.15})
assert(not planner:step(p,model,0))
p.car.position={0,-800,17};local jump=table.clone(model);jump[6]=1
assert(not planner:step(p,jump,0),'Interrupted model jump')
p.car.position={0,-2000,400};p.ground_estimate=false
assert(not planner:step(p,model,0),'Overrode aerial')
p.ground_estimate=true;p.car.position={4000,0,200};p.car.up={-1,0,0}
assert(not planner:step(p,model,0),'Overrode wall play')
p=packet({0,-2000,17},{0,0,93.15});physics.mismatch=true
local a,reason=planner:step(p,model,0)
assert(not a and string.find(reason,'mismatch'))
''')

    def test_live_gravity_fit_ignores_touches_resets_and_ground(self):
        self.run_lua('''
-- Generate an isolated reference flight with a different gravity. Rendered
-- velocities are previous-frame averages, as in the actual pose reader.
local p=packet({-3000,-3000,17},{0,0,800},{200,0,900})
local truth=Physics.new(profile,arena);truth.gravity=-900
local state={position=table.clone(p.ball.position),velocity=table.clone(p.ball.velocity),angular_velocity={0,0,0}}
local old=table.clone(state.position)
for frame=1,60 do
 for _=1,4 do truth:step(state,91.25,1/120)end
 p.ball.position=table.clone(state.position)
 for i=1,3 do p.ball.velocity[i]=(state.position[i]-old[i])*30 end
 old=table.clone(state.position)
 physics:observe(p,frame/30)
end
assert(physics.observedGravity and math.abs(physics.observedGravity+900)<12,'Live gravity was not identified')
assert(physics.status=='live gravity adapted')
local samples=#physics.gravitySamples
-- Near-car bounces and flat ground must not masquerade as flight calibration.
p.car.position=table.clone(p.ball.position)
for i=61,80 do p.ball.position[3]=800+(i%2)*50;physics:observe(p,i/30)end
assert(#physics.gravitySamples==samples,'Fitted a car touch')
physics:observe(nil,3)
assert(#physics.history==0 and not physics.lastAt,'Reset retained flight window')
assert(physics:report().observed_gravity and physics:report().resets>0)
''')

    def test_report_trace_is_bounded_and_outside_arena_disables_assist(self):
        self.run_lua('''
local p=packet({0,-2000,17},{0,0,93.15})
for i=1,2000 do physics:observe(p,i/30)end
assert(#physics.trace<=150)
p.ball.position={9000,0,93.15};physics:observe(p,2001/30)
assert(physics.mismatch,'Outside geometry did not flag profile mismatch')
local report=physics:report()
assert(report.version=='local-6' and report.profile_mismatch and report.arena.EXTENT_X==4096)
assert(report.saved_physics.BALLWORLD_RESTITUTION==.6)
''')
