local C = require("../controller")
local passed = 0
local function test(name, fn) fn(); passed+=1; print("PASS "..name) end
local function sample(changes)
    local s={vx=0,vz=-40,yaw=0,yawRate=0,grounded=4,upY=1}
    for k,v in pairs(changes or {}) do s[k]=v end
    return s
end
local function near(a,b,tolerance) assert(math.abs(a-b)<(tolerance or 1e-5),tostring(a).." ~= "..tostring(b)) end

test("Settings reject nonfinite values and clamp all numeric controls",function()
    local c=C.settings({angle=100,cruiseKmh=0/0,power=math.huge,speedMultiplier=-5,strength=9,mode="unsafe"})
    assert(c.angle==90 and c.cruiseKmh==65 and c.power==1.25 and c.speedMultiplier==0.5 and c.strength==1 and c.mode=="manual")
end)
test("Left / right drift angles use the game's velocity-relative convention",function()
    near(math.deg(C.measure(sample({yaw=math.rad(30)})).beta),30)
    near(math.deg(C.measure(sample({yaw=math.rad(-40)})).beta),-40)
    near(C.wrap(math.rad(359)),math.rad(-1))
end)
test("Manual controls keep throttle, brake and steering ownership in the game",function()
    local o=C.step(C.new(),C.settings(),sample(),{throttle=1,steer=-1},nil,1/60)
    assert(not o.override and o.ax==0 and o.az<0 and o.targetAngle>0)
end)
test("Braking, handbrake, coasting and reversing release manual angle / power assistance",function()
    for _, row in ipairs({{i={throttle=0}},{i={throttle=1,brake=1}},{i={throttle=1,handbrake=true}},
        {i={throttle=1},s={vz=20}}}) do
        local o=C.step(C.new(),C.settings({side="left"}),sample(row.s),row.i,nil,1/60)
        assert(o.yawRate==nil and o.ax==0 and o.az==0 and not o.override)
    end
end)
test("Airborne, overturned and paused samples never receive physics or input commands",function()
    for _, change in ipairs({{grounded=2},{upY=0.4},{paused="Garage"}}) do
        local o=C.step(C.new(),C.settings({mode="road"}),sample(change),{throttle=1},nil,1/60)
        assert(not o.override and o.yawRate==nil and o.ax==0 and o.az==0)
    end
end)
test("Invalid telemetry fails closed",function()
    local o=C.step(C.new(),C.settings(),sample({vx=0/0}),{throttle=1},nil,1/60)
    assert(o.yawRate==nil and o.ax==0 and not o.override)
end)
test("Shift boost changes speed cap and power while ordinary cap brakes overspeed",function()
    local settings=C.settings({power=1,cruiseKmh=65})
    local a=C.step(C.new(),settings,sample(),{throttle=1},nil,1/60)
    local b=C.step(C.new(),settings,sample(),{throttle=1,boost=true},nil,1/60)
    local fast=C.step(C.new(),settings,sample({vz=-100}),{throttle=1},nil,1/60)
    assert(a.targetKmh==65 and b.targetKmh>65 and b.az<a.az and fast.az>0)
end)
test("Auto brake override immediately restores native input and prevents assistance",function()
    local o=C.step(C.new(),C.settings({mode="road"}),sample(),{brake=1},{yaw=0,width=36},1/60)
    assert(not o.override and not o.yawRate and o.ax==0 and o.az==0)
end)
test("Missing road, obstacle, off-road and finish stop instead of accelerating blindly",function()
    for _, guide in ipairs({false, {blocked="Obstacle"}, {offRoad=true}, {remaining=1}}) do
        local g=if type(guide)=="table" then guide else nil
        if g then g.yaw=0 end
        local o=C.step(C.new(),C.settings({mode="road"}),sample(),{},g,1/60)
        assert(o.override and o.throttle==0 and o.brake==1 and not o.yawRate and o.ax==0 and o.az==0)
    end
end)
test("Stationary auto stop uses handbrake, not reverse-triggering brake",function()
    local o=C.step(C.new(),C.settings({mode="road"}),sample({vz=0}),{},nil,1/60)
    assert(o.handbrake and o.brake==0 and o.throttle==0)
end)
test("Corner speed limit remains binding even with high multipliers and Shift",function()
    local o=C.step(C.new(),C.settings({mode="road",cruiseKmh=180,speedMultiplier=2.5,power=4}),sample(),{boost=true},
        {yaw=0,curvature=0.02,width=40,speedLimit=25},1/60)
    near(o.targetKmh,30)
    assert(math.sqrt(o.ax^2+o.az^2)<=108.001)
end)
test("Yaw assistance and frame time are bounded",function()
    local o=C.step(C.new(),C.settings({side="left"}),sample({yaw=-0.5}),{throttle=1},nil,5)
    assert(math.abs(o.yawRate)<=0.500001)
    local weak=C.step(C.new(),C.settings({side="left",strength=0}),sample(),{throttle=1},nil,1/60)
    assert(weak.yawRate==nil)
end)

-- Closed-loop angle tracking with changing velocity headings, disturbances and variable frame rates.
test("Angle tracking converges for 15, 30 and 50 degrees in both directions",function()
    for _, angle in ipairs({15,30,50}) do
        for _, side in ipairs({"left","right"}) do
            for _, hz in ipairs({30,60,144}) do
                local state=C.new()
                local s=sample()
                local expected=math.rad(angle)*(if side=="left" then 1 else -1)
                local settings=C.settings({side=side,angle=angle,power=1,cruiseKmh=180})
                for i=1,hz*8 do
                    local dt=1/hz
                    local travel=0.25*math.sin(i*dt*0.7)
                    s.vx,s.vz=-math.sin(travel)*40,-math.cos(travel)*40
                    local o=C.step(state,settings,s,{throttle=1},nil,dt)
                    s.yawRate=(o.yawRate or s.yawRate)+0.06*dt
                    s.yaw=C.wrap(s.yaw+s.yawRate*dt)
                end
                local error=math.abs(C.wrap(C.measure(s).beta-expected))
                assert(error<math.rad(2),string.format("angle %d %s %d Hz: %.2f degree error",angle,side,hz,math.deg(error)))
            end
        end
    end
end)
print(string.format("Controller: %d scenarios passed",passed))
