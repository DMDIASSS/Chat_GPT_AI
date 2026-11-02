import unittest
import test_game as h


FLAT = '''
local route={}
function route:point(z)return {x=0,y=8,z=z,heading=0,dx=0,dy=0,width=28,surface='tarmac',bridge=false,tunnel=false}end
function route:ground(x,z)return 8,x,self:point(z)end
function route:conditions(z)return {temperature=20,friction=1,wetness=0,wind=0}end
local car=C.Cars[1]
'''


class DamageDynamicsTests(unittest.TestCase):
    run_lua = h.GameTests.run_lua

    def test_impacts_have_directional_damage_and_damage_off_is_respected(self):
        self.run_lua(h.pure(FLAT + '''
local a,b=D.new(route),D.new(route)
D.configure(b,{damage=false})
local energy=D.impact(a,90,-1,car)
D.impact(b,90,-1,car)
assert(energy>.8 and a.damage>40 and a.health.engine<1 and a.health.suspension<1)
assert(a.alignment<0 and a.tyres[1].punctured and a.terminal)
assert(a.impactId==1 and a.impactSpeed==90 and a.impactSide==-1)
assert(b.damage==0 and b.health.engine==1 and not b.tyres[1].punctured and not b.terminal)
assert(b.impactId==1 and b.impact>0,'Damage off lost camera impact feedback')
D.repair(a,'all',car)
assert(a.damage==0 and a.health.engine==1 and a.alignment==0 and not a.terminal)
assert(not a.tyres[1].punctured and a.tyres[1].pressure==a.tyres[1].targetPressure)
'''))

    def test_punctures_deflate_and_reduce_grip_without_shared_state_aliases(self):
        self.run_lua(h.pure(FLAT + '''
local a,b=D.new(route),D.new(route);a.v=35;b.v=35
assert(D.puncture(a,1,car));assert(not D.puncture(a,1,car),'Repeated puncture counted as new')
for i=1,360 do D.step(a,{},route,car,C.Step);D.step(b,{},route,car,C.Step)end
assert(a.tyres[1].pressure<.4 and a.tyres[1].grip<b.tyres[1].grip*.5)
assert(a.v<b.v,'Flat tyre had no rolling resistance')
local flatY,_,flatRoll=D.contactPose(a,route,car);local goodY=D.contactPose(b,route,car)
assert(flatY<goodY and math.abs(flatRoll)>0,'Deflated contact did not tilt/lower chassis')
local clone=D.copy(a);clone.tyres[1].pressure=1;clone.health.engine=0
assert(a.tyres[1].pressure<.4 and a.health.engine==1,'Prediction mutated server state')
local t=D.telemetry(a);assert(t.punctures==1 and t.pressure<.4)
D.repair(a,'tyres',car);assert(not a.tyres[1].punctured and a.tyres[1].wear==0)
'''))

    def test_pressure_heat_wear_and_abs_are_live_state(self):
        self.run_lua(h.pure(FLAT + '''
local a=D.new(route);D.configure(a,{tyrePressure=.75,assists=false})
assert(a.tyres[1].targetPressure==.75 and not a.settings.abs and a.settings.steeringAssist==0)
assert(not D.setPressure(a,5,1,car)and not D.setPressure(a,'all',0/0,car))
a.v=100
for i=1,90 do D.step(a,{throttle=1,steer=.8,brake=.6},route,car,C.Step)end
assert(a.tyreTemperature>20 and a.tyres[1].wear>0 and a.brakeTemperature>20)
assert(a.tyres[1].pressure>.75,'Tyre heat did not alter pressure')
D.configure(a,{assists=true});assert(a.settings.abs and a.settings.tractionControl)
a.v=45;D.step(a,{brake=1},route,car,C.Step)
assert(a.absActive,'ABS did not intervene above tyre force limit')
'''))

    def test_weight_transfer_and_wheel_loads_follow_acceleration(self):
        self.run_lua(h.pure(FLAT + '''
local a=D.new(route)
a.v=45;a.acceleration=20;D.step(a,{},route,car,C.Step)
local accelerateFront=a.frontLoad
assert(a.tyres[1].load>0 and a.tyres[4].load>0)
a.acceleration=-20;D.step(a,{brake=1},route,car,C.Step)
assert(a.frontLoad>accelerateFront,'Braking did not shift load toward front axle')
local summed=0;for _,t in ipairs(a.tyres)do summed+=t.load end
assert(math.abs(summed-car.mass*9.81)<1,'Normal loads lost vehicle weight')
'''))

    def test_damage_changes_power_and_repair_restores_components(self):
        self.run_lua(h.pure(FLAT + '''
local a,b=D.new(route),D.new(route)
D.impact(a,65,0,car);a.v=0
for i=1,300 do D.step(a,{throttle=1},route,car,C.Step);D.step(b,{throttle=1},route,car,C.Step)end
assert(a.v<b.v and a.health.engine<1,'Engine damage did not reduce power')
D.repair(a,'service',car)
assert(a.damage==0 and a.health.engine==1 and a.health.brakes==1 and a.health.suspension==1)
'''))

    def test_barrier_impacts_are_debounced_and_step_is_deterministic(self):
        self.run_lua(h.pure(FLAT + '''
function route:point(z)return {x=0,y=8,z=z,heading=0,dx=0,dy=0,width=28,surface='tarmac',bridge=true,tunnel=false}end
local a,b=D.new(route),D.new(route);a.x=15;a.v=90;a.yaw=.8;b=D.copy(a)
for i=1,90 do D.step(a,{throttle=1,steer=-.1},route,car,C.Step);D.step(b,{throttle=1,steer=-.1},route,car,C.Step)end
assert(a.crashes>=1 and a.crashes<8,'Barrier impact fired every frame')
assert(a.x==b.x and a.v==b.v and a.damage==b.damage and a.tyres[1].pressure==b.tyres[1].pressure)
assert(D.impact(a,0/0,0,car)==0)
'''))


if __name__ == '__main__':
    unittest.main()
