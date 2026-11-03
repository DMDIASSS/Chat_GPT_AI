-- Short ground-contact corrections use the game's sphere and oriented car box.
-- The learned actor keeps jumps, aerials, walls and contested ball touches.
local Contact={}
Contact.__index=Contact
local abs,min,max,sqrt=math.abs,math.min,math.max,math.sqrt
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function cross(a,b)return {a[2]*b[3]-a[3]*b[2],a[3]*b[1]-a[1]*b[3],a[1]*b[2]-a[2]*b[1]}end
local function length(a)return sqrt(dot(a,a))end
local function distance(a,b)return sqrt((a[1]-b[1])^2+(a[2]-b[2])^2+(a[3]-b[3])^2)end
function Contact.new(profile,arena,physics)
    return setmetatable({profile=profile,arena=arena,physics=physics,enabled=true,corrections=0},Contact)
end
function Contact:reset()self.history=nil;self.acceleration={0,0,0};self.active=false;self.last=nil end
function Contact.policyPacket(packet,ignore)
    if not ignore then return packet end
    local out=table.clone(packet);out.other_cars={}
    for _,car in ipairs(packet.other_cars or {})do
        if car.team~=packet.team then out.other_cars[#out.other_cars+1]=car end
    end
    return out
end
function Contact:observe(packet,action,now)
    if not packet then self:reset();return end
    local car=packet.car
    local old=self.history
    local key=tostring(action[1])..':'..tostring(action[7])
    self.acceleration=self.acceleration or {0,0,0}
    local valid=old and now-old.at>=.015 and now-old.at<=.12 and old.key==key
        and packet.ground_estimate and old.ground and dot(car.up,old.up)>.99
        and length(car.angular_velocity)<.7 and self.lastTeam==packet.team
        and distance(car.position,packet.ball.position)>(packet.ball_radius or 91.25)+200
    if valid then
        local a={}
        for i=1,3 do a[i]=(car.velocity[i]-old.velocity[i])/(now-old.at)end
        -- Ignore collision impulses/corrections. A few stable straight samples
        -- estimate current acceleration without fitting an invented speed cap.
        if length(a)<4500 and abs(dot(a,cross(car.up,car.forward)))<450 then
            for i=1,3 do self.acceleration[i]=self.acceleration[i]*.5+a[i]*.5 end
        else self.acceleration={0,0,0}end
    else self.acceleration={0,0,0}end
    self.lastTeam=packet.team
    self.history={at=now,key=key,velocity=table.clone(car.velocity),up=table.clone(car.up),ground=packet.ground_estimate}
end
function Contact:box(packet)
    local config=self.profile.car_presets[packet.car_preset or 'standard']or self.profile.car_presets.standard
    return config.size,config.offset
end
-- Exact sphere-to-OBB distance, including the collider's forward/up offset.
function Contact:gap(car,ballPosition,radius,size,offset)
    local right=cross(car.up,car.forward)
    local delta={ballPosition[1]-car.position[1],ballPosition[2]-car.position[2],ballPosition[3]-car.position[3]}
    local localPoint={dot(delta,car.forward)-offset[1],dot(delta,right)-offset[2],dot(delta,car.up)-offset[3]}
    local sum=0
    for i=1,3 do sum+=max(abs(localPoint[i])-size[i]/2,0)^2 end
    return sqrt(sum)-radius,localPoint
end
function Contact:step(packet,base,now)
    self.last=nil
    local function skip()self.active=false;return nil end
    local car,ball=packet.car,packet.ball
    local cfg,arena=self.profile.physics,self.profile.arena
    if not self.enabled or self.physics.mismatch or not packet.ground_estimate or car.up[3]<.94
        or car.position[3]>85 or base[6]>0 or abs(car.position[1])>arena.EXTENT_X-350
        or abs(car.position[2])>arena.EXTENT_Y-350 then return skip()end
    local radius=packet.ball_radius or cfg.BALL_RADIUS
    local size,offset=self:box(packet)
    local currentGap,localBall=self:gap(car,ball.position,radius,size,offset)
    if currentGap<=0 or distance(car.position,ball.position)>1100 or localBall[1]<-size[1]/2 then return skip()end
    local speed=dot(car.velocity,car.forward)
    if speed<200 then return skip()end
    -- A nearby car may change the ball's trajectory. Avoid forcing a predicted
    -- touch through another car; keep physical players even in ignore mode.
    for _,other in ipairs(packet.other_cars or {})do
        local delta={other.position[1]-car.position[1],other.position[2]-car.position[2],other.position[3]-car.position[3]}
        local v=other.velocity or {0,0,0}
        local relative={v[1]-car.velocity[1],v[2]-car.velocity[2],v[3]-car.velocity[3]}
        local t=math.clamp(-dot(delta,relative)/max(dot(relative,relative),1),0,.22)
        local near={delta[1]+relative[1]*t,delta[2]+relative[2]*t,delta[3]+relative[3]*t}
        if t>0 and length(near)<max(size[1],size[2])+25 and dot(delta,car.forward)>0 then
            local action=table.clone(base);action[1]=-1;action[7]=0;action[8]=0
            self.last={mode='contact obstacle brake',time=t,action=action};self.active=true
            return action,self.last.mode
        end
        if distance(other.position,ball.position)<radius+200 then return skip()end
    end
    local trajectory=self.physics:predict(ball,radius,.45,4)
    local best,score=nil,math.huge
    local acceleration=self.acceleration or {0,0,0}
    for _,sample in ipairs(trajectory)do
        local t=sample.time
        if t>=1/30 and sample.obstructions==0 then
            local predicted=table.clone(car);predicted.position={}
            for i=1,3 do predicted.position[i]=car.position[i]+car.velocity[i]*t+acceleration[i]*t*t*.5 end
            -- Use measured angular motion, rather than assuming instant turns.
            local yaw=(car.angular_velocity[3]or 0)*t
            local c,s=math.cos(yaw),math.sin(yaw)
            predicted.forward={car.forward[1]*c-car.forward[2]*s,car.forward[1]*s+car.forward[2]*c,car.forward[3]}
            predicted.up={car.up[1]*c-car.up[2]*s,car.up[1]*s+car.up[2]*c,car.up[3]}
            local gap,localPoint=self:gap(predicted,sample.position,radius,size,offset)
            local vertical=max(abs(localPoint[3])-size[3]/2,0)
            if vertical<radius-5 then
                local reach=sqrt(radius*radius-vertical*vertical)
                local value=abs(localPoint[1]-size[1]/2-reach)
                if value<score then
                    score=value;best={sample=sample,localPoint=localPoint,gap=gap,reach=reach}
                end
            end
        end
    end
    if not best or score>max(70,speed/30)then return skip()end
    local lateral=best.localPoint[2]
    local corridor=size[2]/2+best.reach
    local miss=abs(lateral)>corridor-12
    local angularSpeed=car.angular_velocity[3]or 0
    if not miss and not self.active then return nil end
    local frontRange=max(localBall[1]-size[1]/2,60)
    local angle=math.atan2(lateral,frontRange)-angularSpeed*min(best.sample.time,.15)*.3
    if abs(angle)>.8 then return skip()end
    local action=table.clone(base)
    action[2]=abs(angle)>.025 and(angle>0 and 1 or -1)or 0
    action[4]=action[2];action[8]=0
    if miss or abs(angle)>.08 then action[7]=0 end
    if miss and best.sample.time<.2 and abs(angle)>.18 and speed>700 then action[1]=-1 end
    self.active=true;self.corrections+=1
    self.last={mode='ground contact correction',time=best.sample.time,target=table.clone(best.sample.position),
        gap=best.gap,lateral=lateral,corridor=corridor,radius=radius,size=table.clone(size),offset=table.clone(offset),
        geometry=packet.car_size_verified and 'verified collider'or(packet.car_dimensions_verified and 'verified preset dimensions'or 'source preset estimate'),
        gravity=self.physics.gravity,speed=speed,action=table.clone(action)}
    return action,self.last.mode
end
function Contact:report()
    return {enabled=self.enabled,corrections=self.corrections,last=self.last,
        scope='Short upright ground contacts; no learned weight changes, scripted jumps, aerial or wall overrides'}
end
return Contact
