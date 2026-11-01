-- Feedback driving follows geometry, never a wall-clock replay or car teleports.
local Driver={}
local abs,min,max,sqrt=math.abs,math.min,math.max,math.sqrt
function Driver.wrap(x)return (x+math.pi)%(2*math.pi)-math.pi end
function Driver.new()return {steer=0,throttle=0,brake=0,stuck=0,recoveryUntil=0}end
local function approach(a,b,rate,dt)return a+math.clamp(b-a,-rate*dt,rate*dt)end
function Driver.step(self,route,base,stage,state,cfg,dt,now)
    dt=math.clamp(dt,1/240,.1)
    local position={x=state.x,y=state.y,z=state.z}
    local on=route:nearest(position,self.hint);self.hint=on.index
    local road=base:nearest(position,self.baseHint);self.baseHint=road.index
    local speed=sqrt(state.vx^2+state.vz^2)
    local forward=state.vx*state.fx+state.vz*state.fz
    local entry=road.s<stage.StartAt and road.distance<350
    local width=stage.Width or 18
    local function stop(reason)
        self.throttle=0;self.brake=1
        return {Throttle=0,Brake=1,Steer=0,Handbrake=false,Analog=true,mode=reason,
            progress=road.s,targetSpeed=0,lateral=road.lateral,remaining=route.length-on.s}
    end
    if state.runState=="Countdown"then return stop("Countdown")end
    if state.runState=="Finished"or road.s>=(stage.StopAt or base.length)-2 then return stop("Stage complete")end
    if not entry and(road.distance>width*.5+14 or abs(road.height)>18)then return stop("Align car with the stage road")end
    local maxSpeed=cfg.maxKmh/1.008
    local lateralGrip=(state.grip or 42)*.82
    local braking=(state.braking or 26)*.82
    local desired=route:targetSpeed(on.s,maxSpeed,lateralGrip,braking,cfg.pace)
    if state.nativePreview then desired=min(desired,state.nativePreview)end
    local look=math.clamp(12+max(forward,0)*.5,12,58)
    local curvature=abs(route:at(min(route.length,on.s+look)).k)
    look=look*math.clamp(1-curvature*3.5,.72,1)
    for _,f in ipairs(stage.features or {})do
        if(f.Kind=="Bridge"or f.Kind=="Narrow")and f.From and f.To then
            if road.s+look>=f.From-6 and road.s<=f.To+6 then
                width=min(width,f.Width or width);desired=min(desired,65)
            end
        end
    end
    local target=route:at(on.s+look)
    if entry and road.distance>width then
        local p=base:at(stage.StartAt)
        target=p;desired=min(desired,16)
    end
    -- Keep the path inside the collision road; a loaded ghost can contain a cut.
    local targetRoad=base:nearest(target,road.index)
    local margin=max(1,width*.5-(state.halfWidth or 2.5)-1)
    if abs(targetRoad.lateral)>margin then
        local p=base:at(targetRoad.s)
        local side=math.clamp(targetRoad.lateral,-margin,margin)
        target={x=p.x-p.fz*side,y=p.y,z=p.z+p.fx*side}
    end
    for _,f in ipairs(stage.features or {})do
        local at=f.At or f.From
        if at and abs(at-road.s-look)<max(18,look*.5)then
            if f.Kind=="Hazard"and f.Side then
                local p=base:at(road.s+look)
                local side=f.Side=="Right"and -1 or 1
                target.x=target.x-p.fz*side*min(margin,3)
                target.z=target.z+p.fx*side*min(margin,3)
                desired=min(desired,55)
            elseif f.Kind=="Bridge"or f.Kind=="Narrow"then desired=min(desired,65)end
        end
    end
    targetRoad=base:nearest(target,road.index)
    if abs(targetRoad.lateral)>margin then
        local p=base:at(targetRoad.s);local side=math.clamp(targetRoad.lateral,-margin,margin)
        target={x=p.x-p.fz*side,y=p.y,z=p.z+p.fx*side}
    end
    local tangent=base:at(road.s)
    local lateralVelocity=state.vx*(-tangent.fz)+state.vz*tangent.fx
    local predictedLateral=road.lateral+lateralVelocity*.25
    local edge=max(0,abs(predictedLateral)-margin*.65)
    if edge>0 then
        local center=base:at(road.s+look)
        local blend=math.clamp(edge/3,0,.9)
        target.x=target.x+(center.x-target.x)*blend
        target.z=target.z+(center.z-target.z)*blend
        desired=desired*math.clamp(1-edge*.12,.45,1)
    end
    local dx,dz=target.x-state.x,target.z-state.z
    local rightX,rightZ=-state.fz,state.fx
    local heading=math.atan2(dx*rightX+dz*rightZ,dx*state.fx+dz*state.fz)
    local range=sqrt(dx*dx+dz*dz)
    local wheelbase=state.wheelbase or 7.5
    local wheelAngle=math.atan2(2*wheelbase*math.sin(heading),max(range,4))
    if abs(heading)>1.2 then wheelAngle=math.sign(heading)*math.rad(state.maxAngle or 28)end
    local steer=math.clamp((wheelAngle-(state.yawRate or 0)*.055)/math.rad(state.maxAngle or 28),-1,1)
    if abs(heading)>1 then desired=min(desired,18)end
    if abs(road.lateral)>margin then desired=min(desired,30)end
    if state.obstacle then desired=min(desired,sqrt(max(0,state.obstacle-6)*2*braking))end
    if road.s>stage.FinishAt then
        desired=min(desired,sqrt(max(0,(stage.StopAt or base.length)-road.s)*2*braking))
    end
    local error=desired-forward
    local throttle,brake=0,0
    if error>1 then throttle=math.clamp(error/12,.12,1)
    elseif error< -1.5 then brake=math.clamp(-error/12,.12,1)
    else throttle=.12 end
    if desired<1 then throttle=0;brake=1 end
    if state.grounded<2 then
        throttle=min(throttle,.25);brake=0;steer=self.steer
    end
    -- Short physical reverse to clear a barrier; it cannot repeat indefinitely.
    local trying=throttle>.5 or(state.obstacle and state.obstacle<7)
    if state.runState=="Running"and state.grounded>=3 and speed<1.5 and trying then
        self.stuck=self.stuck+dt
    else self.stuck=0 end
    local mode="Following "..(route.meta.source or "route")
    if self.stuck>2.5 and now>(self.recoveryCooldown or 0)then
        self.recoveryUntil=now+.7;self.recoveryCooldown=now+5;self.stuck=0
    end
    if now<self.recoveryUntil then throttle=0;brake=1;steer=-math.sign(steer);mode="Clearing obstruction"end
    self.steer=approach(self.steer,steer,2.4,dt)
    self.throttle=approach(self.throttle,throttle,4,dt)
    self.brake=approach(self.brake,brake,6,dt)
    if self.brake>.15 then self.throttle=0 end
    return {Throttle=self.throttle,Brake=self.brake,Steer=self.steer,Handbrake=false,Analog=true,
        mode=mode,progress=road.s,targetSpeed=desired,lateral=road.lateral,target=target,
        remaining=route.length-on.s,reference=route.meta.source}
end
return Driver
