-- Conservative ground-touch guards. Does not simulate future car-ball impacts.
local Safety={}
Safety.__index=Safety
local sqrt,abs,min,max=math.sqrt,math.abs,math.min,math.max
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function sub(a,b)return {a[1]-b[1],a[2]-b[2],a[3]-b[3]}end
local function distance(a,b)local d=sub(a,b);return sqrt(dot(d,d))end
function Safety.new(profile,arena,physics,calibration)
    return setmetatable({profile=profile,arena=arena,physics=physics,calibration=calibration},Safety)
end
function Safety:fits(goal,p,radius,margin)
    local x=abs(dot(sub(p,goal.origin),goal.side))+margin
    local z=p[3]-goal.origin[3]
    if x+radius>goal.half_width or z+radius+margin>goal.height or z<radius-2 then return false end
    local r=goal.fillet
    local dx=x-(goal.half_width-r)
    local dz=abs(z-goal.height/2)-(goal.height/2-r)
    local inside=r-sqrt(max(dx,0)^2+max(dz,0)^2)-min(max(dx,dz),0)
    return inside>=radius-2
end
function Safety:crossing(goal,trajectory,radius)
    for i=2,#trajectory do
        local a,b=trajectory[i-1],trajectory[i]
        local da=dot(sub(a.position,goal.origin),goal.normal)
        local db=dot(sub(b.position,goal.origin),goal.normal)
        local plane=radius+10
        if da<plane and db>=plane then
            local f=(plane-da)/max(db-da,.00001);local p={}
            for j=1,3 do p[j]=a.position[j]+(b.position[j]-a.position[j])*f end
            if (b.obstructions or 0)==0 and self:fits(goal,p,radius,35)then return {position=p,time=a.time+(b.time-a.time)*f}end
        end
    end
end
function Safety:step(packet,action,now)
    self.last=nil
    local car,ball=packet.car,packet.ball
    if self.physics.mismatch or not packet.ground_estimate or car.up[3]<.9 or action[6]~=0 then return nil end
    local radius=packet.ball_radius or self.profile.physics.BALL_RADIUS
    local worldRadius=radius*self.profile.physics.BALL_WORLD_RADIUS/self.profile.physics.BALL_RADIUS
    if ball.position[3]>worldRadius+120 or abs(ball.velocity[3])>250 then return nil end
    local cfg=self.profile.car_presets[packet.car_preset or 'standard']or self.profile.car_presets.standard
    local own=self.calibration:goal(packet.team)
    local target=self.calibration:goal(1-packet.team)
    local forwardSpeed=dot(car.velocity,car.forward)
    local centre={}
    local f,u=car.forward,car.up
    local right={u[2]*f[3]-u[3]*f[2],u[3]*f[1]-u[1]*f[3],u[1]*f[2]-u[2]*f[1]}
    for i=1,3 do centre[i]=car.position[i]+f[i]*cfg.offset[1]+right[i]*cfg.offset[2]+u[i]*cfg.offset[3]end
    local delta=sub(ball.position,centre);local gap=sqrt(dot(delta,delta))
    -- A straight, close ground push through our own mouth is avoidable. Turns,
    -- jumps and aerial saves retain the actor's command.
    if gap<radius+cfg.size[1]/2+75 and gap>1 and abs(action[2])<.5
        and(action[1]>.5 or action[7]~=0)and forwardSpeed>-100
        and dot(sub(ball.position,own.origin),own.normal)>-1600 then
        local direction={delta[1]/gap,delta[2]/gap,delta[3]/gap}
        local towards=dot(direction,own.normal)
        if towards>.7 and dot(direction,car.forward)>.75 then
            local t=-dot(sub(ball.position,own.origin),own.normal)/towards
            local cross={ball.position[1]+direction[1]*t,ball.position[2]+direction[2]*t,ball.position[3]+direction[3]*t}
            if t>0 and self:fits(own,cross,worldRadius,0)then
                local a=table.clone(action);a[1]=forwardSpeed>150 and -1 or 0;a[7]=0;a[8]=0
                self.last={mode='Own-goal push guard',time=now,crossing=cross}
                return a,self.last.mode
            end
        end
    end
    if gap>850 or (packet.unknown_cars or 0)>0 or dot(ball.velocity,target.normal)<450
        or dot(sub(ball.position,target.origin),target.normal)<-1800
        or dot(sub(car.position,ball.position),target.normal)>-40 then return nil end
    local relative=sub(car.velocity,ball.velocity)
    local speed2=dot(relative,relative)
    if speed2<120^2 then return nil end
    local d=sub(ball.position,car.position)
    local nearTime=math.clamp(dot(d,relative)/speed2,0,.5)
    local separation={d[1]-relative[1]*nearTime,d[2]-relative[2]*nearTime,d[3]-relative[3]*nearTime}
    if sqrt(dot(separation,separation))>radius+cfg.size[1]/2+50 or dot(d,relative)<=0 then return nil end
    local trajectory=self.physics:predict(ball,radius,1.5)
    local cross=self:crossing(target,trajectory,worldRadius)
    if not cross then return nil end
    for _,other in ipairs(packet.other_cars or {})do
        for _,sample in ipairs(trajectory)do
                if sample.time>cross.time then break end
                local t=min(sample.time,.8);local v=other.velocity or {0,0,0}
                local p={other.position[1]+v[1]*t,other.position[2]+v[2]*t,other.position[3]+v[3]*t}
                if distance(p,sample.position)<450+radius+800*min(sample.time,.8)^2 then return nil end
        end
    end
    local a={forwardSpeed>200 and -1 or 0,0,0,0,0,0,0,0}
    self.last={mode='Leave clear shot',time=now,crossing=cross.position,crossing_seconds=cross.time,
        calibrated_geometry=self.calibration.active~=nil}
    return a,self.last.mode
end
return Safety
