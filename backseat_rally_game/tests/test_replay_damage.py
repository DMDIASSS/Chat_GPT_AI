import unittest
import test_game as h


class ReplayDamageTests(unittest.TestCase):
    run_lua = h.GameTests.run_lua

    def test_condition_frame_round_trips_crash_drivetrain_and_tyres(self):
        self.run_lua(h.pure('''
local route=Route.new(89,0,C);local s=D.new(route)
D.step(s,{throttle=1},route,C.Cars[1],C.Step)
D.impact(s,91,-1,C.Cars[1]);s.gear=3;s.rpm=4321
s.tyres[1].pressure=.347;s.tyres[1].wear=.6473;s.tyreTemperature=76.4;s.brakeTemperature=316.2
local f=Replay.frame(6.15,s);assert(#f==35)
local r=Replay.state(Replay.decode(Replay.encode({f}))[1])
assert(r.tyres[1].pressure==.347 and r.tyres[1].wear==.6473 and r.tyres[1].punctured)
assert(not r.tyres[2].punctured and r.gear==3 and r.rpm==4321)
assert(math.abs(r.health.engine-s.health.engine)<.001 and math.abs(r.damage-s.damage)<.06)
assert(r.impactId==s.impactId and r.impactSide==-1 and r.impactSpeed==91 and r.terminal)
assert(r.tyreTemperature==76.4 and r.brakeTemperature==316.2)
assert(math.abs(r.bodyY-s.bodyY)<.001)
'''))

    def test_old_recordings_and_no_pose_initial_frame_remain_valid(self):
        self.run_lua(h.pure('''
local old=Replay.decode([[0,0,0,0,0,0,0,0,0,0,0\n100,20,40,100,20,0,10,0,1000,0,0,10000,500,200]])
local a,b=Replay.state(old[1]),Replay.state(old[2])
assert(not a.bodyY and b.bodyY==10 and b.pitch==.05)
assert(a.tyres[1].pressure==1 and not a.tyres[1].punctured and a.health.engine==1)
local route=Route.new(91,0,C);local initial=D.new(route)
local decoded=Replay.state(Replay.decode(Replay.encode({Replay.frame(0,initial)}))[1])
assert(not decoded.bodyY,'Initial replay frame invented a ground-level suspension pose')
assert(decoded.tyres[1].pressure==1 and decoded.health.engine==1)
'''))

    def test_puncture_and_repair_do_not_appear_before_recorded_event(self):
        self.run_lua(h.pure('''
local route=Route.new(6,0,C);local s=D.new(route);local frames={Replay.frame(0,s)}
D.puncture(s,1,C.Cars[1]);s.tyres[1].pressure=.6;s.tyres[1].wear=.5;frames[2]=Replay.frame(1,s)
s.tyres[1].pressure=.4;frames[3]=Replay.frame(2,s)
D.repair(s,'tyres',C.Cars[1]);frames[4]=Replay.frame(3,s)
local before=Replay.sample(frames,.999)
assert(not before.tyres[1].punctured and before.tyres[1].pressure==1 and before.tyres[1].wear==0)
local hit=Replay.sample(frames,1);assert(hit.tyres[1].punctured and hit.tyres[1].pressure==.6)
local leak=Replay.sample(frames,1.5);assert(leak.tyres[1].punctured and math.abs(leak.tyres[1].pressure-.5)<.0001)
local waiting=Replay.sample(frames,2.9);assert(waiting.tyres[1].punctured and waiting.tyres[1].pressure==.4)
local repaired=Replay.sample(frames,3);assert(not repaired.tyres[1].punctured and repaired.tyres[1].pressure==1)
'''))

    def test_crash_damage_arrives_at_impact_and_recovery_still_cuts(self):
        self.run_lua(h.pure('''
local route=Route.new(9,0,C);local s=D.new(route);local frames={Replay.frame(0,s)}
D.impact(s,70,1,C.Cars[1]);s.z=40;frames[2]=Replay.frame(1,s)
local before=Replay.sample(frames,.9);assert(before.damage==0 and before.health.engine==1 and before.impactId==0)
local hit=Replay.sample(frames,1);assert(hit.damage>0 and hit.health.engine<1 and hit.impactId==1)
s.z=768;frames[3]=Replay.frame(6,s,1)
assert(Replay.sample(frames,3).z==40 and Replay.sample(frames,6).z==768)
'''))

    def test_pages_stay_bounded_and_reject_malformed_conditions(self):
        self.run_lua(h.pure('''
local route=Route.new(42,0,C);local s=D.new(route);local frames={}
for i=1,500 do
 s.z=1000000+i;s.x=123.45;s.bodyY=139.45;s.pitch=.1;s.roll=.09;s.v=140;s.rpm=7000;s.gear=5
 frames[i]=Replay.frame(i*.1,s)
end
local text=Replay.encode(frames);assert(#text<100000 and #Replay.decode(text)==500)
frames[501]=frames[500];assert(not pcall(Replay.encode,frames))
local valid=Replay.frame(0,s)
for _,change in ipairs({{15,-1},{19,10001},{23,16},{26,1001},{33,1024},{35,16000}})do
 local bad=table.clone(valid);bad[change[1]]=change[2]
 assert(not pcall(Replay.decode,table.concat(bad,',')),'Invalid condition field accepted')
end
assert(not pcall(Replay.decode,'0,0,0,0,0,0,0,0,0,0,nope,0'))
assert(not pcall(Replay.decode,'0,0,0,0,0,0,0,0,0,,0,0'))
'''))


if __name__ == '__main__':
    unittest.main()
