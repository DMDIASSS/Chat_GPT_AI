"""Contact geometry, changed physics, teammate filtering and bounded overrides."""
from pathlib import Path
import unittest
import sys
import test_performance as performance
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_standalone import literal,load_arena_profile

APP=Path(__file__).resolve().parents[1]


class ContactTests(unittest.TestCase):
    def run_case(self,body):
        profile=load_arena_profile(APP/'arena_profile.json')
        pre='local profile='+literal(profile)+'\n'
        # The runner places modules before the body; their functions accept the profile.
        return performance.PerformanceTests.run_lua(self,
            {'Arena':'local_arena.lua','Physics':'local_physics.lua','Contact':'local_contact.lua'},pre+'''
local arena=Arena.new(profile)
local physics=Physics.new(profile,arena)
local controller=Contact.new(profile,arena,physics)
controller:reset()
local action={1,0,0,0,0,0,1,0}
local function packet(x,y,speed,radius)
 radius=radius or 91.25
 return {team=0,boost=70,ground_estimate=true,ball_radius=radius,car_preset='standard',
  car_dimensions_verified=true,other_cars={},
  car={position={0,y or -600,17},velocity={0,speed or 1800,0},forward={0,1,0},up={0,0,1},angular_velocity={0,0,0}},
  ball={position={x or 200,0,radius*profile.physics.BALL_WORLD_RADIUS/profile.physics.BALL_RADIUS},
   velocity={0,0,0},angular_velocity={0,0,0}}}
end
'''+body)

    def test_exact_offset_box_face_corner_and_rotation_distances(self):
        self.run_case('''
local car={position={0,0,20},forward={1,0,0},up={0,0,1}}
local size,offset={100,80,40},{10,0,20}
assert(math.abs(controller:gap(car,{150,0,40},90,size,offset))<1e-8,'Front face ignores forward offset')
assert(math.abs(controller:gap(car,{10,0,160},90,size,offset)-10)<1e-8,'Roof height ignores up offset')
assert(math.abs(controller:gap(car,{63,44,40},5,size,offset))<1e-8,'3-4-5 corner contact differs')
car.forward={0,1,0}
assert(math.abs(controller:gap(car,{0,150,40},90,size,offset))<1e-8,'Rotated collider differs')
assert(controller:gap(car,{0,0,40},90,size,offset)<0,'Overlap was called a miss')
''')

    def test_crossing_ball_uses_future_position_and_mirrors_steer(self):
        self.run_case('''
for _,side in ipairs({-1,1})do
 controller:reset()
 local p=packet(side*260,-600,1800);p.ball.velocity={-side*150,0,0}
 local result=controller:step(p,action,0)
 assert(result and result[2]==-side,'Steering missed the moving ball side')
 assert(result[7]==0,'Boosted through a predicted miss')
 assert(math.abs(controller.last.target[1])<260,'Chased the current ball position')
 assert(controller.last.time>0 and controller.last.time<=.45)
 assert(action[2]==0 and action[7]==1,'Mutated the actor output')
end
''')

    def test_large_ball_and_each_car_preset_use_collision_geometry(self):
        self.run_case('''
local p=packet(150,-550,1800)
assert(controller:step(p,action,0),'Small ball miss was not detected')
assert(controller.last.radius==91.25)
controller:reset();p=packet(150,-550,1800,182.5)
assert(not controller:step(p,action,0),'Corrected a trajectory already inside the large ball hitbox')
for name,config in pairs(profile.car_presets)do
 controller:reset();p=packet(240,-600,1800);p.car_preset=name
 assert(controller:step(p,action,0),'No correction for '..name)
 for i=1,3 do
  assert(controller.last.size[i]==config.size[i]and controller.last.offset[i]==config.offset[i],'Wrong preset collider')
 end
end
''')

    def test_changed_gravity_changes_ground_reachability(self):
        self.run_case('''
local p=packet(210,-900,1800);p.ball.position[3]=300;p.ball.velocity[3]=-200
physics.gravity=-325
assert(not controller:step(p,action,0),'Drove at a ball above the reachable contact height')
controller:reset();physics.gravity=-1300
assert(controller:step(p,action,0),'Ignored a ball falling into ground reach under higher gravity')
assert(controller.last.gravity==-1300 and controller.last.target[3]<160)
''')

    def test_keeps_jumps_aerials_walls_contests_and_existing_touches(self):
        self.run_case('''
local cases={'jump','air','wall','touch','contested','mismatch','disabled'}
for _,kind in ipairs(cases)do
 controller:reset();controller.enabled=true;physics.mismatch=false
 local p=packet(240,-600,1800);local base=table.clone(action)
 if kind=='jump'then base[6]=1
 elseif kind=='air'then p.ground_estimate=false
 elseif kind=='wall'then p.car.position[1]=4050
 elseif kind=='touch'then p.ball.position={0,-480,93.15}
 elseif kind=='contested'then p.other_cars={{team=1,position={240,50,17},velocity={0,0,0}}}
 elseif kind=='mismatch'then physics.mismatch=true
 else controller.enabled=false end
 assert(not controller:step(p,base,0),'Overrode '..kind)
end
''')

    def test_teammates_stay_in_collision_checks_while_ignored_by_actor(self):
        self.run_case('''
for team=0,1 do
 local p=packet(240,-600,1800);p.team=team
 local ally={team=team,position={0,-400,17},velocity={0,0,0}}
 local enemy={team=1-team,position={900,900,17},velocity={0,0,0}}
 local unknown={position={1000,1000,17}}
 p.other_cars={ally,enemy,unknown}
 local view=Contact.policyPacket(p,true)
 assert(#view.other_cars==2 and view.other_cars[1]==enemy and view.other_cars[2]==unknown)
 assert(#p.other_cars==3 and p.other_cars[1]==ally,'Removed physical teammate from telemetry')
 assert(Contact.policyPacket(p,false)==p)
 local result,mode=controller:step(p,action,0)
 assert(result and mode=='contact obstacle brake'and result[1]==-1 and result[7]==0,'Ignored a real collision obstacle')
end
''')

    def test_straight_motion_estimate_uses_observed_acceleration_and_resets(self):
        self.run_case('''
local p=packet(240,-800,900)
for i=1,12 do p.car.velocity[2]=900+40*i;controller:observe(p,action,i/30)end
assert(controller.acceleration[2]>1100 and controller.acceleration[2]<1300)
p.car.velocity[2]+=1500;controller:observe(p,action,13/30)
assert(controller.acceleration[2]==0,'Fitted an impact as engine acceleration')
controller:reset();assert(controller.acceleration[2]==0 and not controller.history)
''')

    def test_light_mode_tracks_gravity_without_forecast_work(self):
        self.run_case('''
for _,gravity in ipairs({-32.5,-900,-1300})do
 local truth=Physics.new(profile,arena);truth.gravity=gravity
 local observer=Physics.new(profile,arena)
 local p=packet(0,-3000,0);p.ball.position={0,0,900};p.ball.velocity={220,0,200}
 for frame=1,42 do
  for tick=1,4 do truth:step(p.ball,p.ball_radius,1/120)end
  observer:observe(p,frame/30,true)
 end
 assert(observer.observedGravity and math.abs(observer.observedGravity-gravity)<12,'Light mode missed gravity '..gravity)
 assert(observer.forecast==nil and observer.totalFlightErrors==0,'Light mode ran forecast validation')
end
''')
