local Rail=require("../autorail")
local Roads=require("../roads")
local function line(name,x,z1,z2) return Roads.path(name,{{x=x,z=z1},{x=x,z=z2}},false,30) end
local a=line("A",0,0,-100)
local b=line("B",0,-100,-250)
local farm={style="farm",cruiseKmh=500,farmTravel="loop"}
local s=Rail.new(a,{s=95},1)
local joined=false;local looped=false
for _=1,500 do
    local pose=Rail.step(s,farm,1/60,false,{a,b})
    assert(math.abs(pose.speed*1.2-500)<1e-6)
    assert(math.abs(pose.targetAngle-60)<1e-6)
    if pose.joined then joined=true end
    if pose.jumped then looped=true end
    assert(s.s>=0 and s.s<=s.path.total)
end
assert(joined and looped and s.loops>1)
print("PASS Farm connects segments then loops to start without slowing from 500 km/h")
local bad=Rail.new(a,{s=95},1)
Rail.rejectConnection(bad,b)
assert(not Roads.connection({a,b},a,1,bad.rejected[tostring(a)..":1"]))
assert(Rail.step(bad,farm,.1,false,{a,b}).jumped)
print("PASS unsupported connected exits can be rejected and replaced with a spawn loop")
local reversed=Rail.new(a,{s=50},1)
Rail.step(reversed,farm,1/60,false,{a})
Rail.reverse(reversed,false)
assert(math.abs(Rail.step(reversed,farm,1/60,false,{a}).targetAngle+60)<1e-6)
print("PASS Reverse flips drift side")
local area={style="farm",cruiseKmh=500,farmTravel="area",farmRange=40}
local sweep=Rail.new(a,{s=50},1)
local both={}
local previousBody
for _=1,600 do
    local pose=Rail.step(sweep,area,1/60,false,{a})
    both[sweep.direction]=true
    assert(sweep.s>=30 and sweep.s<=70 and pose.speed==500/1.2)
    if previousBody then
        local delta=(pose.bodyHeading-previousBody+math.pi)%(2*math.pi)-math.pi
        assert(math.abs(delta)<1e-5,"Back-and-forth should retain the car's facing direction")
    end
    previousBody=pose.bodyHeading
end
assert(both[1] and both[-1])
print("PASS Farm area sweeps remain local, maintain speed, reverse motion and mirror native drift angle")
local tiny=line("Tiny",0,0,-3)
local t=Rail.new(tiny,{s=1},1)
for _=1,100 do Rail.step(t,area,.1,false,{tiny});assert(t.s>=0 and t.s<=3) end
print("PASS very short area handles multiple reversals in one frame")
local long=line("Long",0,0,-10000)
local cool={style="cool",angle=45,cruiseKmh=110,halfWidth=3,halfLength=5}
local c=Rail.new(long,{s=100},1)
local low,high=0,0
for _=1,1200 do
    local pose=Rail.step(c,cool,1/60,false,{long})
    low=math.min(low,pose.lateral);high=math.max(high,pose.lateral)
    assert(math.abs(pose.lateral)+math.sqrt(3^2+5^2)+2<=long.width/2+1e-6)
end
assert(low<-1 and high>1)
print("PASS Cool moves side to side with the full angled car bounded inside the road")
local coolEnd=Rail.new(a,{s=90},1)
local hasReturned=false
for _=1,600 do if Rail.step(coolEnd,cool,1/60,false,{a}).jumped then hasReturned=true end end
assert(hasReturned)
print("PASS Cool brakes at a dead end and resumes its spawn loop")
