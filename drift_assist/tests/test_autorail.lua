local Rail=require("../autorail")
local Roads=require("../roads")
local p=Roads.path("Straight",{{x=0,z=0},{x=0,z=-100}},false,36)
local s=Rail.new(p,{s=0},1)
Rail.step(s,{angle=75,cruiseKmh=80},1/60,true)
assert(s.direction==1 and s.speed==0)
for _=1,180 do
    local pose=Rail.step(s,{angle=75,cruiseKmh=80},1/60,false)
    assert(pose.point.z<=0 and pose.point.z>=-100)
end
assert(math.abs(s.beta-math.rad(75))<1e-6)
s.s=99.99;s.speed=40;s.direction=1
assert(Rail.step(s,{angle=75,cruiseKmh=80},1/60,false).reversed)
assert(s.direction==-1)
for _=1,120 do Rail.step(s,{angle=75,cruiseKmh=80},1/60,true) end
assert(s.speed==0)
local loop=Roads.path("Loop",{{x=0,z=0},{x=100,z=0},{x=100,z=100}},true,36)
local l=Rail.new(loop,{s=loop.total-.001},1);l.speed=40
assert(not Rail.step(l,{angle=15,cruiseKmh=80},1/60,false).reversed and l.s<loop.total)
print("PASS rail 75-degree angle, braking, no false reversal, open-road turnaround and loop wrap")
