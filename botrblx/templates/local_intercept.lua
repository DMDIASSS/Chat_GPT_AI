-- Ground approach controller. The trained policy retains close touches, jumps,
-- aerials, wall play and recovery. This is a bounded reach estimate, not a car sim.
local Intercept={}
Intercept.__index=Intercept
local abs,min,max,sqrt=math.abs,math.min,math.max,math.sqrt
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function distance(a,b)return sqrt((a[1]-b[1])^2+(a[2]-b[2])^2)end
local function unit(x,y)
    local d=sqrt(x*x+y*y);if d<1e-8 then return 0,1 end
    return x/d,y/d
end
local function sign(x)return x<0 and -1 or 1 end
local function curve(points,value)
    for i=2,#points do
        if value<=points[i][1]then
            local a,b=points[i-1],points[i]
            return a[2]+(b[2]-a[2])*math.clamp((value-a[1])/(b[1]-a[1]),0,1)
        end
    end
    return points[#points][2]
end
function Intercept.new(profile,arena,physics)
    return setmetatable({profile=profile,arena=arena,physics=physics},Intercept)
end
function Intercept:reset()self.side=nil;self.last=nil;self.padTarget=nil end

function Intercept:heading(car,target)
    local x,y=target[1]-car.position[1],target[2]-car.position[2]
    -- Native car right = up x forward (the Roblox/simulation swap reflects axes).
    local right={car.up[2]*car.forward[3]-car.up[3]*car.forward[2],
        car.up[3]*car.forward[1]-car.up[1]*car.forward[3],
        car.up[1]*car.forward[2]-car.up[2]*car.forward[1]}
    return math.atan2(x*right[1]+y*right[2],x*car.forward[1]+y*car.forward[2])
end

-- A small 60 Hz longitudinal integration uses throttle taper, measured cap and
-- finite boost. Turning consumes time; reachable balls must also be low enough.
function Intercept:reach(car,boost,seconds,angle)
    local speed=max(0,dot(car.velocity,car.forward))
    local delay=min(abs(angle)/2.5,.9)
    local travel=0
    local cfg=self.profile.physics
    for _=1,math.floor(max(0,seconds-delay)*60)do
        local throttle=4*cfg.THROTTLE_TORQUE_AMOUNT/cfg.CAR_MASS*curve(cfg.DRIVE_SPEED_TORQUE_FACTOR,speed)
        local acceleration=throttle
        if boost>0 then
            acceleration=acceleration+cfg.BOOST_ACCEL_GROUND
            boost=boost-cfg.BOOST_USED_PER_SECOND/60
        end
        speed=min(cfg.CAR_MAX_SPEED,speed+acceleration/60)
        travel=travel+speed/60
    end
    return travel
end

-- Use verified active pads on an existing approach, with a small detour budget.
-- A grounded override must not hide boost information that the actor receives.
function Intercept:routePad(packet,target,danger,behind,radius)
    if packet.boost>=20 or danger or behind> -radius*.5 then self.padTarget=nil;return end
    local car,ball=packet.car,packet.ball
    local attack=packet.team==0 and 1 or -1
    if distance(car.position,ball.position)<1500
        or(ball.position[2]*attack< -self.profile.arena.EXTENT_Y*.35 and ball.velocity[2]*attack< -250)then
        self.padTarget=nil;return
    end
    local direct=distance(car.position,target)
    local tx,ty=unit(target[1]-car.position[1],target[2]-car.position[2])
    local chosen,score=nil,math.huge
    for _,pad in ipairs(packet.boost_pads or {})do
        if pad.active==true then
            local d=distance(car.position,pad.position)
            local detour=d+distance(pad.position,target)-direct
            local ahead=(pad.position[1]-car.position[1])*tx+(pad.position[2]-car.position[2])*ty
            if d>80 and d<(pad.is_big and 1400 or 650)and ahead>d*.2 and detour<min(350,120+direct*.1)then
                local cost=d*.2+detour-(pad.is_big and 150 or 0)
                if self.padTarget and distance(self.padTarget,pad.position)<1 then cost=cost-80 end
                if cost<score then chosen,score=pad,cost end
            end
        end
    end
    self.padTarget=chosen and table.clone(chosen.position)or nil
    return chosen
end

function Intercept:step(packet,modelAction,now)
    local car,ball=packet.car,packet.ball
    local arena=self.profile.arena
    local radius=packet.ball_radius or self.profile.physics.BALL_RADIUS
    local ballDistance=distance(car.position,ball.position)
    if self.physics.mismatch then return nil,"physics mismatch: model"end
    if not packet.ground_estimate or car.up[3]<.85 or car.position[3]>130
        or abs(car.position[1])>arena.EXTENT_X-300 then return nil end
    -- Ground assistance only: never invent aerial/flip timing or interrupt the
    -- actor at contact. Goals and side switches reset the approach hysteresis.
    if ballDistance<radius+300 or(modelAction[6]>0 and ballDistance<1000)then return nil end
    local trajectory=self.physics:predict(ball,radius,2.5)
    local attack=packet.team==0 and 1 or -1
    local danger=false
    for _,sample in ipairs(trajectory)do
        local p=sample.position
        if p[2]*attack< -arena.EXTENT_Y+radius and abs(p[1])<arena.MOUTH_HALF_WIDTH-radius*.5
            and p[3]<arena.MOUTH_HEIGHT+radius then danger=true;break end
    end
    local chosen,bestGap=nil,math.huge
    for _,sample in ipairs(trajectory)do
        local p=sample.position
        if sample.time>=.15 and p[3]<radius+150 and abs(p[2])<arena.EXTENT_Y+200 then
            local gap=distance(car.position,p)-self:reach(car,packet.boost,sample.time,self:heading(car,p))-(radius+100)
            if gap<bestGap then bestGap=gap;chosen=sample end
            if gap<=0 then chosen=sample;break end
        end
    end
    if not chosen then return nil end -- keep learned high-ball/wall decisions
    local future=chosen.position
    local goalX=math.clamp(future[1]*.25,-arena.MOUTH_HALF_WIDTH*.55,arena.MOUTH_HALF_WIDTH*.55)
    local dx,dy=unit(goalX-future[1],attack*(arena.EXTENT_Y+250)-future[2])
    local speed=sqrt(car.velocity[1]^2+car.velocity[2]^2)
    local preset=self.profile.car_presets[packet.car_preset or "standard"]or self.profile.car_presets.standard
    local front=preset.size[1]/2+preset.offset[1]
    local standOff=math.clamp(radius+front+100+speed*.06,220,440)
    local target={future[1]-dx*standOff,future[2]-dy*standOff,17}
    local behind=(car.position[1]-future[1])*dx+(car.position[2]-future[2])*dy
    local mode=danger and "defend intercept"or "ground intercept"
    if behind> -radius*.5 and not danger then
        -- Going directly through the ball from the wrong side makes own goals.
        -- Pick one side and hold it until we have reached the approach side.
        if not self.side then
            local side=(car.position[1]-future[1])*(-dy)+(car.position[2]-future[2])*dx
            self.side=sign(side)
        end
        local clearance=radius+front+260
        target[1]=target[1]-dy*clearance*self.side
        target[2]=target[2]+dx*clearance*self.side
        mode="circle behind ball"
    else
        self.side=nil
        local alignment=car.forward[1]*dx+car.forward[2]*dy
        local lateral=abs((car.position[1]-future[1])*(-dy)+(car.position[2]-future[2])*dx)
        if alignment>.9 and behind<0 and lateral<radius+70 then
            target={future[1]+dx*(radius+200),future[2]+dy*(radius+200),17}
        end
    end
    target[1]=math.clamp(target[1],-arena.EXTENT_X+350,arena.EXTENT_X-350)
    target[2]=math.clamp(target[2],-arena.EXTENT_Y+180,arena.EXTENT_Y-180)
    -- Rounded corners have less driveable floor than a rectangular clamp.
    for _=1,4 do
        local gap,n=self.arena:query({target[1],target[2],70})
        if abs(n[3])>.7 or gap>=160 then break end
        target[1]=target[1]+n[1]*(160-gap);target[2]=target[2]+n[2]*(160-gap)
    end
    local pad=self:routePad(packet,target,danger,behind,radius)
    local driveTime=chosen.time
    if pad then
        target={pad.position[1],pad.position[2],17}
        mode="boost on approach"
        driveTime=max(.35,distance(car.position,target)/max(speed,1000))
    end
    local angle=self:heading(car,target)
    local remaining=distance(car.position,target)
    local headingError=angle-(car.angular_velocity and car.angular_velocity[3]or 0)*.16
    local steer=abs(headingError)>.055 and sign(headingError)or 0
    local forwardSpeed=dot(car.velocity,car.forward)
    local desired=min(self.profile.physics.CAR_MAX_SPEED,max(450,remaining/max(driveTime,.3)))
    desired=min(desired,500+1700*max(math.cos(angle),0)^2)
    if abs(angle)>1.1 then desired=min(desired,650)end
    local throttle=1
    if forwardSpeed>desired+180 then throttle=-1 end -- actual braking, no boost
    local boost=throttle==1 and abs(angle)<.12 and remaining>700
        and forwardSpeed<desired-150 and packet.boost>0 and 1 or 0
    local slide=abs(angle)>1.2 and speed>500 and speed<1400 and 1 or 0
    local action={throttle,steer,0,steer,0,0,boost,slide}
    self.last={mode=mode,target=target,ball=table.clone(future),time=chosen.time,
        reachable=bestGap<=0,danger=danger,heading=angle,desired_speed=desired,action=action,
        boost_pad=pad and {position=table.clone(pad.position),is_big=pad.is_big}or nil}
    self.physics.plan=self.last
    return action,mode
end
return Intercept
