import unittest
import test_game as h

class VehicleSystemTests(unittest.TestCase):
    run_lua=h.GameTests.run_lua

    def test_all_uploaded_profiles_use_the_same_stable_solver(self):
        self.run_lua(h.pure('''
assert(#C.Cars==15,'Missing uploaded vehicle profiles')
for _,car in ipairs(C.Cars)do
 assert(car.mass>0 and car.torque>0 and car.power>0 and car.rearShare>0 and car.rearShare<1)
 assert(car.suspension and car.tyres and car.steering and #car.ratios>0)
 local route=Route.new(41,0,C);local s=D.new(route)
 for i=1,900 do D.step(s,{throttle=1,steer=.01},route,car,C.Step)end
 assert(s.v==s.v and s.bodyY==s.bodyY and math.abs(s.bodyV)<100 and s.v>0,car.name)
end
'''))

    def test_axle_load_changes_contact_height(self):
        self.run_lua(h.pure('''
local route=Route.new(85,0,C);local s=D.new(route);s.z=840;s.x=route:point(s.z).x;s.yaw=route:point(s.z).heading
local a=table.clone(C.Cars[1]);local b=table.clone(a);a.rearShare=.2;b.rearShare=.8
local ya,pa=D.contactPose(s,route,a);local yb,pb=D.contactPose(s,route,b)
assert(ya~=yb or pa~=pb,'Axle balance is cosmetic')
'''))

    def test_bumps_and_climate_are_deterministic(self):
        self.run_lua(h.pure('''
local a,b=Route.new(3,0,C),Route.new(3,0,C);local dry=Route.new(4,0,C)
assert(a:conditions(300).wetness>dry:conditions(300).wetness)
local changes=0
for z=200,500,1 do
 local slope=a:point(z).dy-a:point(z-1).dy
 if math.abs(slope)>.0008 then changes+=1 end
 assert(a:point(z).y==b:point(z).y)
end
assert(changes>20,'Road has no short-wave bumps')
assert(string.find(a:call(300,30),'m',1,true),'Co-driver call has no distance')
'''))

    def test_suspension_pose_survives_replay(self):
        self.run_lua(h.pure('''
local route=Route.new(3,0,C);local car=C.Cars[1];local s=D.new(route)
for i=1,600 do D.step(s,{throttle=1},route,car,C.Step)end
local frames=Replay.decode(Replay.encode({Replay.frame(10,s)}));local state=Replay.sample(frames,10)
assert(math.abs(state.bodyY-s.bodyY)<.001 and math.abs(state.pitch-s.pitch)<.0001)
D.reset(s,route,768);assert(not s.bodyY,'Recovery kept old suspension motion')
'''))
