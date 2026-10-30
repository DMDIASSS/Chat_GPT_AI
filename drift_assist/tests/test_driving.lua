-- Closed-loop functional checks with a planar tyre / engine disturbance model.
-- This is not Roblox, its collision solver, networking, or a live-game performance claim.
local C=require("../controller")
local R=require("../roads")
local function run(path, angle, direction, hz, seconds)
    local p,h=R.point(path,0)
    if direction<0 then h+=math.pi end
    local sample={x=p.x,y=2,z=p.z,vx=-math.sin(h)*20,vz=-math.cos(h)*20,yaw=h,yawRate=0,grounded=4,upY=1}
    local settings=C.settings({mode="road",angle=angle,power=1.25,cruiseKmh=80})
    local state,previousS=C.new(),nil
    local maxCross,angleSum,scored=0,0,0
    local last
    for i=1,hz*seconds do
        local dt=1/hz
        local m=C.measure(sample)
        local guide=R.guide(path,direction,sample,m.speed,sample.yaw,previousS)
        assert(guide,"Lost path projection")
        previousS=guide.s
        local command=C.step(state,settings,sample,{},guide,dt)
        local fx,fz=-math.sin(sample.yaw),-math.cos(sample.yaw)
        local rx,rz=math.cos(sample.yaw),-math.sin(sample.yaw)
        local lateral=sample.vx*rx+sample.vz*rz
        local tyre=-math.clamp(lateral*2.4,-30,30)
        local engine=(command.throttle or 0)*24
        local brakeForce=if command.handbrake then math.min(25,m.speed/dt) else (command.brake or 0)*45
        local brake=if m.speed>0.01 then brakeForce/m.speed else 0
        sample.vx+=(engine*fx+tyre*rx-sample.vx*(0.07+brake)+command.ax)*dt
        sample.vz+=(engine*fz+tyre*rz-sample.vz*(0.07+brake)+command.az)*dt
        sample.yawRate=command.yawRate or sample.yawRate*0.95
        sample.yaw=C.wrap(sample.yaw+sample.yawRate*dt)
        sample.x+=sample.vx*dt;sample.z+=sample.vz*dt
        maxCross=math.max(maxCross,guide.crossTrack)
        if i>hz*5 then angleSum+=math.abs(math.deg(m.beta)-(command.targetAngle or 0));scored+=1 end
        last=command
        assert(not guide.offRoad,"Departed road corridor")
    end
    return maxCross,angleSum/math.max(scored,1),sample,last
end

local cases,worst=0,0
for _,radius in ipairs({40,80,140}) do
    local points={}
    for i=0,240 do local a=i/240*2*math.pi;table.insert(points,{x=radius*math.cos(a),z=radius*math.sin(a)}) end
    local path=R.path("Test circle",points,true,30)
    for _,angle in ipairs({15,30,50}) do
        for _,direction in ipairs({1,-1}) do
            for _,hz in ipairs({30,60}) do
                local cross,error=run(path,angle,direction,hz,20)
                assert(cross<12,string.format("Circle: %.2f cross-track",cross))
                assert(error<3,string.format("Circle: %.2f degree error",error))
                cases+=1;worst=math.max(worst,cross)
            end
        end
    end
end
print(string.format("PASS %d closed-loop road / angle combinations, max cross-track %.2f studs",cases,worst))

local path=R.parseMinimap("line|36|0,0;0,-180")[1]
local cross,_,s,last=run(path,30,1,60,18)
assert(cross<10 and s.z>=-180 and s.z<=-170 and C.measure(s).speed<3)
assert(last.throttle==0 and last.handbrake)
print("PASS Finite road brakes and parks before the end without reversing")
